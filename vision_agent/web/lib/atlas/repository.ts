import { sql } from "../db";
import type { AgentMessage, Allocation, ForecastBreakdown, MessageType, ProposalStatus } from "../domain";
import type { ApprovalRole } from "../approvals";
import type { Session } from "../auth";
import type { AtlasDashboardState, TimelineEvent } from "./types";

export async function loadPersistentDashboardState(session: Session): Promise<AtlasDashboardState> {
  const proposals = await sql()`SELECT p.*, n.id AS negotiation_id
    FROM transfer_proposals p JOIN negotiations n ON n.id = p.negotiation_id
    ORDER BY p.created_at DESC LIMIT 1`;
  const proposal = proposals[0];
  if (!proposal) throw new Error("No ATLAS proposal exists. Run npm run db:seed first.");
  if (session.globalRole !== "administrator") {
    const allowed = await sql()`SELECT 1 FROM organization_memberships m
      JOIN proposal_participants p ON p.organization_id = m.organization_id
      WHERE m.user_id = ${session.userId} AND p.transfer_proposal_id = ${proposal.id} LIMIT 1`;
    if (allowed.length === 0) throw new Error("You are not a participant in this proposal");
  }
  const approvalRows = await sql()`SELECT a.*, o.name AS organization_name, u.display_name AS decided_by_name
    FROM required_approvals a JOIN organizations o ON o.id = a.organization_id
    LEFT JOIN users u ON u.id = a.decision_by
    WHERE a.transfer_proposal_id = ${proposal.id} ORDER BY a.created_at`;
  const messageRows = await sql()`SELECT m.* FROM agent_messages m
    WHERE m.negotiation_id = ${proposal.negotiation_id} ORDER BY m.created_at`;
  const plan = proposal.plan as { allocations: Allocation[]; explanation: string };
  const messages: AgentMessage[] = messageRows.map((row) => ({
    id: String(row.id),
    negotiationId: String(row.negotiation_id),
    senderAgentId: String(row.sender_agent_id),
    recipientAgentId: row.recipient_agent_id ? String(row.recipient_agent_id) : undefined,
    recipientScope: row.recipient_scope ? String(row.recipient_scope) : undefined,
    messageType: row.message_type as MessageType,
    payload: row.payload as Record<string, unknown>,
    parentMessageId: row.parent_message_id ? String(row.parent_message_id) : undefined,
    agentRunId: String(row.agent_run_id),
    explanation: String(row.explanation),
    status: row.status as AgentMessage["status"],
    expiresAt: new Date(String(row.expires_at)).toISOString(),
    createdAt: new Date(String(row.created_at)).toISOString(),
  }));
  const timeline: TimelineEvent[] = [
    {
      id: "persistent-trigger",
      timestamp: messages[0]?.createdAt ?? new Date().toISOString(),
      actor: "Disruption agent",
      kind: "trigger" as const,
      title: "Disruption assessment started",
      detail: "A severe alert matched a registered site and started the ATLAS run.",
    },
    ...messages.map((message) => ({
      id: `timeline-${message.id}`,
      timestamp: message.createdAt,
      actor: message.senderAgentId,
      kind: "agent" as const,
      title: message.messageType.replaceAll("_", " "),
      detail: message.explanation,
    })),
    ...approvalRows.filter((row) => row.decided_at).map((row) => ({
      id: `timeline-approval-${row.id}`,
      timestamp: new Date(String(row.decided_at)).toISOString(),
      actor: String(row.organization_name),
      kind: "human" as const,
      title: `Commitment ${row.status}`,
      detail: `${row.decided_by_name ?? "Authorized representative"} recorded the decision.`,
    })),
  ].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  return {
    mode: "persistent",
    inventoryIntake: { status: "approved", site: "Oakland Food Bank", detectionCount: 100, confirmedCount: 100 },
    activeImpact: {
      title: "Flood Watch — Alameda County",
      severity: "Severe",
      affectedSite: "Fremont Food Bank",
      source: "National Weather Service",
    },
    network: [
      { name: "Fremont Food Bank", type: "food_bank", status: "Shortage", detail: "150 canned goods needed" },
      { name: "Oakland Food Bank", type: "food_bank", status: "Offer", detail: "100 units available" },
      { name: "Bay Fresh Foods", type: "vendor", status: "Offer", detail: "50 units available" },
      { name: "Bay Relief Logistics", type: "logistics", status: "Feasible", detail: "180-unit vehicle available" },
    ],
    proposal: {
      id: String(proposal.id),
      negotiationId: String(proposal.negotiation_id),
      status: proposal.status as ProposalStatus,
      category: String(proposal.category),
      neededBy: new Date(String(proposal.needed_by)).toISOString(),
      requestingSite: "Fremont Food Bank",
      explanation: plan.explanation,
      calculation: proposal.calculation as ForecastBreakdown,
      allocations: plan.allocations,
      approvals: approvalRows.map((row) => ({
        id: String(row.id),
        organizationId: String(row.organization_id),
        organizationName: String(row.organization_name),
        approvalRole: row.approval_role as ApprovalRole,
        status: row.status as "pending" | "approved" | "rejected",
        decidedBy: row.decided_by_name ? String(row.decided_by_name) : undefined,
      })),
    },
    messages,
    timeline,
  };
}
