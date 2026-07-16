import { hash } from "bcryptjs";

import { sql } from "../lib/db";
import { runSyntheticScenario } from "../lib/atlas/orchestrator";

async function main() {
  const password = process.env.ATLAS_DEMO_ADMIN_PASSWORD ?? "relief-demo";
  const email = process.env.ATLAS_DEMO_ADMIN_EMAIL ?? "admin@relieflink.demo";
  const passwordHash = await hash(password, 12);
  const db = sql();
  const organizations = [
    ["11111111-1111-4111-8111-111111111111", "Oakland Food Bank", "food_bank"],
    ["22222222-2222-4222-8222-222222222222", "Fremont Food Bank", "food_bank"],
    ["33333333-3333-4333-8333-333333333333", "Bay Fresh Foods", "vendor"],
    ["44444444-4444-4444-8444-444444444444", "Bay Relief Logistics", "logistics"],
    ["55555555-5555-4555-8555-555555555555", "ReliefLink", "platform"],
  ] as const;
  for (const [id, name, type] of organizations) {
    await db`INSERT INTO organizations (id, name, organization_type)
      VALUES (${id}, ${name}, ${type}) ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name`;
  }
  const userId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  await db`INSERT INTO users (id, email, password_hash, display_name, global_role)
    VALUES (${userId}, ${email}, ${passwordHash}, 'Demo Administrator', 'administrator')
    ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash`;
  await db`INSERT INTO sites (id, organization_id, name, county, latitude, longitude, safety_stock_policy)
    VALUES
      ('aaaaaaaa-1111-4111-8111-111111111111', '11111111-1111-4111-8111-111111111111', 'Oakland Food Bank', 'Alameda', 37.8044, -122.2712, '{"canned_goods":50}'),
      ('bbbbbbbb-2222-4222-8222-222222222222', '22222222-2222-4222-8222-222222222222', 'Fremont Food Bank', 'Alameda', 37.5485, -121.9886, '{"canned_goods":25}')
    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name`;
  await db`INSERT INTO inventory_transactions
    (id, organization_id, site_id, category, product_name, quantity, direction,
     transaction_type, source, operator_id, approval_status, reviewer_id,
     idempotency_key, approved_at)
    VALUES ('70000000-0000-4000-8000-000000000001', ${organizations[0][0]},
      'aaaaaaaa-1111-4111-8111-111111111111', 'canned_goods', 'Assorted canned goods',
      150, 'in', 'intake', 'synthetic_seed', ${userId}, 'approved', ${userId},
      'atlas-seed-oakland-cans-v1', now()) ON CONFLICT (id) DO NOTHING`;
  const vendorSupplyId = "80000000-0000-4000-8000-000000000001";
  await db`INSERT INTO vendor_supply
    (id, organization_id, category, product_name, available_quantity, pickup_start,
     pickup_end, published_by)
    VALUES (${vendorSupplyId}, ${organizations[2][0]}, 'canned_goods', 'Assorted canned goods',
      80, '2026-07-17T16:00:00Z', '2026-07-17T19:00:00Z', ${userId})
    ON CONFLICT (id) DO UPDATE SET available_quantity = 80`;
  const state = runSyntheticScenario();
  const agents = [
    ["10000000-0000-4000-8000-000000000001", "11111111-1111-4111-8111-111111111111", "aaaaaaaa-1111-4111-8111-111111111111", "site", "Oakland site agent"],
    ["10000000-0000-4000-8000-000000000002", "22222222-2222-4222-8222-222222222222", "bbbbbbbb-2222-4222-8222-222222222222", "site", "Fremont site agent"],
    ["10000000-0000-4000-8000-000000000003", "33333333-3333-4333-8333-333333333333", null, "vendor", "Bay Fresh supplier agent"],
    ["10000000-0000-4000-8000-000000000004", "44444444-4444-4444-8444-444444444444", null, "logistics", "Bay Relief logistics agent"],
    ["10000000-0000-4000-8000-000000000005", "55555555-5555-4555-8555-555555555555", null, "orchestrator", "ATLAS orchestrator"],
  ] as const;
  for (const [id, organizationId, siteId, type, name] of agents) {
    await db`INSERT INTO agents (id, organization_id, site_id, agent_type, name)
      VALUES (${id}, ${organizationId}, ${siteId}, ${type}, ${name})
      ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name`;
  }
  const runIds = [
    ["20000000-0000-4000-8000-000000000001", agents[1][0], "weather_alert"],
    ["20000000-0000-4000-8000-000000000002", agents[0][0], "supply_request"],
    ["20000000-0000-4000-8000-000000000003", agents[2][0], "supply_request"],
    ["20000000-0000-4000-8000-000000000004", agents[3][0], "logistics_check"],
    ["20000000-0000-4000-8000-000000000005", agents[4][0], "offers_validated"],
  ] as const;
  for (const [id, agentId, trigger] of runIds) {
    await db`INSERT INTO agent_runs (id, agent_id, trigger_type, status, input, output, completed_at)
      VALUES (${id}, ${agentId}, ${trigger}, 'awaiting_human', '{}', '{}', now())
      ON CONFLICT (id) DO NOTHING`;
  }
  const negotiationId = "30000000-0000-4000-8000-000000000001";
  await db`INSERT INTO negotiations (id, trigger_type, status, region, expires_at, created_by_agent_run_id)
    VALUES (${negotiationId}, 'weather_alert', 'awaiting_approvals', 'Alameda County', ${state.proposal.neededBy}, ${runIds[0][0]})
    ON CONFLICT (id) DO UPDATE SET status = 'awaiting_approvals'`;
  const proposalId = "40000000-0000-4000-8000-000000000001";
  const persistentAllocations = state.proposal.allocations.map((allocation) => allocation.sourceType === "site"
    ? { ...allocation, sourceId: "aaaaaaaa-1111-4111-8111-111111111111", organizationId: organizations[0][0] }
    : { ...allocation, sourceId: vendorSupplyId, organizationId: organizations[2][0] });
  await db`INSERT INTO transfer_proposals
    (id, negotiation_id, status, category, requested_quantity, optimizer_recommended_quantity,
     needed_by, calculation, plan, expires_at)
    VALUES (${proposalId}, ${negotiationId}, 'awaiting_approvals', 'canned_goods', 150, 150,
      ${state.proposal.neededBy}, ${JSON.stringify(state.proposal.calculation)},
      ${JSON.stringify({ allocations: persistentAllocations, explanation: state.proposal.explanation })},
      '2026-07-17T20:00:00Z')
    ON CONFLICT (id) DO UPDATE SET calculation = EXCLUDED.calculation, plan = EXCLUDED.plan`;
  const approvalRows = [
    ["50000000-0000-4000-8000-000000000001", organizations[0][0], "site_reviewer"],
    ["50000000-0000-4000-8000-000000000002", organizations[2][0], "vendor_representative"],
    ["50000000-0000-4000-8000-000000000003", organizations[3][0], "logistics_coordinator"],
    ["50000000-0000-4000-8000-000000000004", organizations[1][0], "site_reviewer"],
  ] as const;
  for (const [id, organizationId, role] of approvalRows) {
    await db`INSERT INTO required_approvals (id, transfer_proposal_id, organization_id, approval_role)
      VALUES (${id}, ${proposalId}, ${organizationId}, ${role}) ON CONFLICT (id) DO NOTHING`;
  }
  const participants = [
    [organizations[1][0], "requester", { quantity: 150 }],
    [organizations[0][0], "donor", { quantity: 100 }],
    [organizations[2][0], "vendor", { quantity: 50 }],
    [organizations[3][0], "logistics", { capacity: 180 }],
  ] as const;
  for (const [organizationId, role, commitment] of participants) {
    await db`INSERT INTO proposal_participants
      (transfer_proposal_id, organization_id, participant_role, commitment)
      VALUES (${proposalId}, ${organizationId}, ${role}, ${JSON.stringify(commitment)})
      ON CONFLICT (transfer_proposal_id, organization_id, participant_role) DO NOTHING`;
  }
  await db`INSERT INTO agent_tool_calls (id, agent_run_id, tool_name, input, output, status)
    VALUES
      ('90000000-0000-4000-8000-000000000001', ${runIds[0][0]}, 'calculate_shortage', '{"category":"canned_goods"}', '{"shortage":150}', 'completed'),
      ('90000000-0000-4000-8000-000000000002', ${runIds[3][0]}, 'validate_route', '{"pickups":2}', '{"feasible":true,"capacity":180}', 'completed'),
      ('90000000-0000-4000-8000-000000000003', ${runIds[4][0]}, 'ortools_optimize', '{"requested":150}', '{"allocated":150}', 'completed')
    ON CONFLICT (id) DO NOTHING`;
  const agentByDemoId: Record<string, string> = {
    agent_oakland: agents[0][0], agent_fremont: agents[1][0], agent_bay_fresh: agents[2][0],
    agent_logistics: agents[3][0], agent_atlas: agents[4][0],
  };
  const runByDemoId: Record<string, string> = {
    run_weather_fremont_001: runIds[0][0], run_oakland_001: runIds[1][0],
    run_vendor_001: runIds[2][0], run_logistics_001: runIds[3][0], run_atlas_001: runIds[4][0],
  };
  const messageIdByDemoId: Record<string, string> = Object.fromEntries(
    state.messages.map((message, index) => [message.id, `60000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`]),
  );
  for (const message of state.messages) {
    await db`INSERT INTO agent_messages
      (id, negotiation_id, sender_agent_id, recipient_agent_id, recipient_scope, message_type,
       payload, parent_message_id, agent_run_id, explanation, expires_at, created_at)
      VALUES (${messageIdByDemoId[message.id]}, ${negotiationId}, ${agentByDemoId[message.senderAgentId]},
       ${message.recipientAgentId ? agentByDemoId[message.recipientAgentId] : null}, ${message.recipientScope ?? null},
       ${message.messageType}, ${JSON.stringify(message.payload)},
       ${message.parentMessageId ? messageIdByDemoId[message.parentMessageId] : null},
       ${runByDemoId[message.agentRunId]}, ${message.explanation}, ${message.expiresAt}, ${message.createdAt})
      ON CONFLICT (id) DO NOTHING`;
  }
  console.log(`Seeded hosted demo. Sign in as ${email}`);
}

void main();
