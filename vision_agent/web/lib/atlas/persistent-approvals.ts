import type { PoolClient } from "@neondatabase/serverless";

import { approvalOutcome, mayDecideApproval, type ApprovalRequirement } from "../approvals";
import type { Session } from "../auth";
import { withTransaction } from "../db";
import { assertReservationIsSafe } from "../inventory";

type ApprovalRow = {
  id: string;
  transfer_proposal_id: string;
  organization_id: string;
  approval_role: ApprovalRequirement["approvalRole"];
  status: ApprovalRequirement["status"];
};

async function actorRoles(client: PoolClient, userId: string, organizationId: string) {
  const result = await client.query(
    `SELECT role FROM organization_memberships
     WHERE user_id = $1 AND organization_id = $2`,
    [userId, organizationId],
  );
  return result.rows.map((row) => String(row.role));
}

export async function decidePersistentApproval(input: {
  approvalId: string;
  decision: "approved" | "rejected";
  note?: string;
  session: Session;
}) {
  return withTransaction(async (client) => {
    const locked = await client.query(
      "SELECT * FROM required_approvals WHERE id = $1 FOR UPDATE",
      [input.approvalId],
    );
    const requirement = locked.rows[0] as ApprovalRow | undefined;
    if (!requirement) throw new Error("Approval requirement not found");
    if (requirement.status !== "pending") throw new Error("Approval has already been decided");
    const roles = await actorRoles(client, input.session.userId, requirement.organization_id);
    if (!mayDecideApproval({
      requirement: {
        organizationId: requirement.organization_id,
        approvalRole: requirement.approval_role,
        status: requirement.status,
      },
      actorOrganizationId: requirement.organization_id,
      actorRoles: roles,
      globalRole: input.session.globalRole,
    })) throw new Error("You cannot decide this organization's commitment");

    await client.query(
      `UPDATE required_approvals SET status = $1, decision_by = $2,
       decision_note = $3, decided_at = now() WHERE id = $4`,
      [input.decision, input.session.userId, input.note ?? null, input.approvalId],
    );
    const all = await client.query(
      `SELECT organization_id, approval_role, status FROM required_approvals
       WHERE transfer_proposal_id = $1`,
      [requirement.transfer_proposal_id],
    );
    const outcome = approvalOutcome(all.rows.map((row) => ({
      organizationId: String(row.organization_id),
      approvalRole: row.approval_role,
      status: row.status,
    })));
    await client.query(
      "UPDATE transfer_proposals SET status = $1, updated_at = now() WHERE id = $2",
      [outcome, requirement.transfer_proposal_id],
    );
    if (outcome === "approved") {
      await client.query(
        `UPDATE transfer_proposals SET human_approved_quantity = optimizer_recommended_quantity
         WHERE id = $1`,
        [requirement.transfer_proposal_id],
      );
      const proposalResult = await client.query(
        "SELECT * FROM transfer_proposals WHERE id = $1 FOR UPDATE",
        [requirement.transfer_proposal_id],
      );
      const proposal = proposalResult.rows[0];
      const plan = proposal.plan as {
        allocations: Array<{
          sourceId: string;
          sourceType: "site" | "vendor";
          organizationId: string;
          quantity: number;
        }>;
      };
      for (const allocation of plan.allocations) {
        if (allocation.sourceType === "site") {
          const site = await client.query(
            "SELECT safety_stock_policy FROM sites WHERE id = $1 FOR UPDATE",
            [allocation.sourceId],
          );
          if (!site.rows[0]) throw new Error("Allocation source site no longer exists");
          const position = await client.query(
            `SELECT
              COALESCE((SELECT SUM(CASE WHEN direction = 'in' THEN quantity WHEN direction = 'out' THEN -quantity ELSE 0 END)
                FROM inventory_transactions WHERE site_id = $1 AND category = $2 AND approval_status = 'approved'), 0) AS on_hand,
              COALESCE((SELECT SUM(quantity) FROM inventory_reservations WHERE site_id = $1
                AND category = $2 AND status IN ('provisional','active')), 0) AS reserved`,
            [allocation.sourceId, proposal.category],
          );
          const policy = site.rows[0].safety_stock_policy as Record<string, number>;
          assertReservationIsSafe({
            onHand: Number(position.rows[0].on_hand),
            alreadyReserved: Number(position.rows[0].reserved),
            requested: allocation.quantity,
            safetyStock: Number(policy[proposal.category] ?? 0),
          });
          await client.query(
            `INSERT INTO inventory_reservations
             (organization_id, site_id, category, quantity, status, transfer_proposal_id, expires_at)
             VALUES ($1, $2, $3, $4, 'active', $5, $6)
             ON CONFLICT (transfer_proposal_id, site_id, category) WHERE site_id IS NOT NULL DO NOTHING`,
            [allocation.organizationId, allocation.sourceId, proposal.category, allocation.quantity, proposal.id, proposal.expires_at],
          );
        } else {
          const supply = await client.query(
            `SELECT v.available_quantity,
              COALESCE((SELECT SUM(r.quantity) FROM inventory_reservations r WHERE r.vendor_supply_id = v.id
                AND r.status IN ('provisional','active')), 0) AS reserved
             FROM vendor_supply v WHERE v.id = $1 FOR UPDATE`,
            [allocation.sourceId],
          );
          if (!supply.rows[0] || Number(supply.rows[0].available_quantity) - Number(supply.rows[0].reserved) < allocation.quantity) {
            throw new Error("Vendor supply is no longer available");
          }
          await client.query(
            `INSERT INTO inventory_reservations
             (organization_id, vendor_supply_id, category, quantity, status, transfer_proposal_id, expires_at)
             VALUES ($1, $2, $3, $4, 'active', $5, $6)
             ON CONFLICT (transfer_proposal_id, vendor_supply_id, category) WHERE vendor_supply_id IS NOT NULL DO NOTHING`,
            [allocation.organizationId, allocation.sourceId, proposal.category, allocation.quantity, proposal.id, proposal.expires_at],
          );
        }
      }
      const logistics = await client.query(
        `SELECT organization_id FROM required_approvals
         WHERE transfer_proposal_id = $1 AND approval_role = 'logistics_coordinator'`,
        [proposal.id],
      );
      await client.query(
        `INSERT INTO shipments
         (transfer_proposal_id, status, logistics_organization_id, pickup_window_start,
          pickup_window_end, delivery_window_start, delivery_window_end, manifest)
         VALUES ($1, 'reserved', $2, now(), now() + interval '4 hours', now() + interval '4 hours',
          $3, $4) ON CONFLICT (transfer_proposal_id) DO NOTHING`,
        [proposal.id, logistics.rows[0].organization_id, proposal.needed_by, JSON.stringify(plan)],
      );
      await client.query(
        "UPDATE transfer_proposals SET status = 'reserved', updated_at = now() WHERE id = $1",
        [proposal.id],
      );
      await client.query(
        "UPDATE negotiations SET status = 'reserved', updated_at = now() WHERE id = $1",
        [proposal.negotiation_id],
      );
      return { proposalId: requirement.transfer_proposal_id, status: "reserved" as const };
    }
    return { proposalId: requirement.transfer_proposal_id, status: outcome };
  });
}
