import { approvalOutcome } from "../approvals";
import { runSyntheticScenario } from "./orchestrator";
import type { AtlasDashboardState } from "./types";

const globalStore = globalThis as typeof globalThis & { reliefLinkDemo?: AtlasDashboardState };

export function getDemoState() {
  globalStore.reliefLinkDemo ??= runSyntheticScenario();
  return globalStore.reliefLinkDemo;
}

export function resetDemoState() {
  globalStore.reliefLinkDemo = runSyntheticScenario();
  return globalStore.reliefLinkDemo;
}

export function decideDemoApproval(approvalId: string, decision: "approved" | "rejected") {
  const state = getDemoState();
  const approval = state.proposal.approvals.find((item) => item.id === approvalId);
  if (!approval) throw new Error("Approval requirement not found");
  if (approval.status !== "pending") throw new Error("Approval has already been decided");
  approval.status = decision;
  approval.decidedBy = "Synthetic human reviewer";
  state.timeline.push({
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    actor: approval.organizationName,
    kind: "human",
    title: decision === "approved" ? "Commitment approved" : "Commitment rejected",
    detail: `${approval.approvalRole.replaceAll("_", " ")} recorded a human ${decision} decision.`,
  });
  const outcome = approvalOutcome(state.proposal.approvals);
  state.proposal.status = outcome;
  if (outcome === "approved") {
    state.proposal.calculation.humanApprovedQuantity = state.proposal.calculation.optimizerRecommendedQuantity;
    state.proposal.status = "reserved";
    state.timeline.push({
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      actor: "ATLAS orchestrator",
      kind: "system",
      title: "All approvals recorded; supply reserved",
      detail: "ATLAS rechecked availability and created reservations. Dispatch still requires the approved logistics plan and recorded shipment events.",
    });
  }
  return state;
}

export function updateDemoIntake(action: "submit" | "approve", detectionCount: number, confirmedCount: number) {
  const state = getDemoState();
  if (action === "submit") {
    if (state.inventoryIntake.status !== "draft") throw new Error("Observation has already been submitted");
    state.inventoryIntake = { status: "pending", site: "Oakland Food Bank", detectionCount, confirmedCount };
    state.timeline.unshift({
      id: crypto.randomUUID(), timestamp: new Date().toISOString(), actor: "Oakland operator", kind: "human",
      title: "Inventory observation submitted", detail: `Operator confirmed ${confirmedCount} visible canned-food packages; inventory has not changed yet.`,
    });
  } else {
    if (state.inventoryIntake.status !== "pending") throw new Error("No pending observation to approve");
    state.inventoryIntake.status = "approved";
    state.timeline.unshift({
      id: crypto.randomUUID(), timestamp: new Date().toISOString(), actor: "Oakland site reviewer", kind: "human",
      title: "Intake transaction approved", detail: `${state.inventoryIntake.confirmedCount} units were added to Oakland's immutable shared ledger.`,
    });
  }
  return state.inventoryIntake;
}
