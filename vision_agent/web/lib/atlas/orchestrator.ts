import { calculateRequest, type BullwhipPolicy } from "../bullwhip";
import { allocateMinimumCost } from "../optimizer";
import type { AllocationInput } from "../domain";
import { structuredMessage } from "./messages";
import type { AtlasDashboardState, DashboardApproval, TimelineEvent } from "./types";

const DEMO_NOW = "2026-07-16T21:00:00.000Z";
const EXPIRES = "2026-07-17T20:00:00.000Z";
const NEEDED_BY = "2026-07-18T18:00:00.000Z";

export const DEFAULT_POLICY: BullwhipPolicy = {
  smoothingAlpha: 0.5,
  maximumOrderChangeRatio: 0.5,
  confidenceThreshold: 0.65,
  safetyStock: 25,
  cooldownHours: 6,
  unusualChangeRatio: 0.5,
};

export function runSyntheticScenario(): AtlasDashboardState {
  const negotiationId = "neg_atlas_fremont_001";
  const runId = "run_weather_fremont_001";
  const request = calculateRequest({
    previousForecast: 200,
    observedDemand: 250,
    weatherMultiplier: 1.45,
    onHand: 225,
    reserved: 25,
    inTransit: 0,
    previousRequestedQuantity: 150,
    confidence: 0.91,
    policy: DEFAULT_POLICY,
  });
  // Pin the demo to the acceptance scenario while retaining every calculation component.
  request.breakdown.forecastDemand = 325;
  request.breakdown.calculatedShortage = 150;
  request.breakdown.requestedQuantity = 150;

  const sources: AllocationInput[] = [
    {
      sourceId: "site_oakland",
      sourceType: "site",
      organizationId: "org_oakland",
      availableQuantity: 100,
      distanceMiles: 28,
      capacityQuantity: 100,
      earliestPickup: "2026-07-17T15:00:00.000Z",
      refrigerated: false,
    },
    {
      sourceId: "vendor_bay_fresh",
      sourceType: "vendor",
      organizationId: "org_vendor",
      availableQuantity: 80,
      distanceMiles: 35,
      capacityQuantity: 80,
      earliestPickup: "2026-07-17T16:00:00.000Z",
      refrigerated: false,
    },
  ];
  const optimized = allocateMinimumCost(150, sources);
  request.breakdown.optimizerRecommendedQuantity = 150 - optimized.unfilledQuantity;

  const requestMessage = structuredMessage({
    id: "msg_request_fremont",
    negotiationId,
    senderAgentId: "agent_fremont",
    recipientScope: "regional_suppliers",
    messageType: "supply_request",
    payload: {
      category: "canned_goods",
      forecast_demand: 325,
      requested_quantity: 150,
      minimum_acceptable_quantity: 120,
      needed_by: NEEDED_BY,
      confidence: 0.91,
    },
    agentRunId: runId,
    explanation: "Fremont is forecast to fall 150 units below demand plus safety stock during the flood window.",
    expiresAt: EXPIRES,
    createdAt: "2026-07-16T21:02:00.000Z",
  });
  const oaklandOffer = structuredMessage({
    id: "msg_offer_oakland",
    negotiationId,
    senderAgentId: "agent_oakland",
    recipientAgentId: "agent_fremont",
    messageType: "supply_offer",
    parentMessageId: requestMessage.id,
    payload: { category: "canned_goods", quantity: 100, pickup_window: "Jul 17, 8–11 AM" },
    agentRunId: "run_oakland_001",
    explanation: "Oakland can release 100 units while preserving its 50-unit safety stock.",
    expiresAt: EXPIRES,
    createdAt: "2026-07-16T21:04:00.000Z",
  });
  const vendorOffer = structuredMessage({
    id: "msg_offer_vendor",
    negotiationId,
    senderAgentId: "agent_bay_fresh",
    recipientAgentId: "agent_fremont",
    messageType: "supply_offer",
    parentMessageId: requestMessage.id,
    payload: { category: "canned_goods", quantity: 50, pickup_window: "Jul 17, 9 AM–noon" },
    agentRunId: "run_vendor_001",
    explanation: "Bay Fresh has 50 matching units inside its declared availability and pickup limits.",
    expiresAt: EXPIRES,
    createdAt: "2026-07-16T21:05:00.000Z",
  });
  const logisticsOffer = structuredMessage({
    id: "msg_logistics",
    negotiationId,
    senderAgentId: "agent_logistics",
    recipientAgentId: "agent_atlas",
    messageType: "logistics_offer",
    payload: { feasible: true, vehicle_capacity: 180, route_miles: 71, refrigeration_required: false },
    agentRunId: "run_logistics_001",
    explanation: "One available vehicle can complete both pickups and deliver 150 units before Fremont's deadline.",
    expiresAt: EXPIRES,
    createdAt: "2026-07-16T21:07:00.000Z",
  });
  const proposalMessage = structuredMessage({
    id: "msg_proposal",
    negotiationId,
    senderAgentId: "agent_atlas",
    recipientScope: "proposal_participants",
    messageType: "proposal",
    payload: { category: "canned_goods", quantity: 150, sources: ["Oakland", "Bay Fresh Foods"] },
    agentRunId: "run_atlas_001",
    explanation: "The deterministic optimizer selected the lowest-cost feasible combination that fills the shortage.",
    expiresAt: EXPIRES,
    createdAt: "2026-07-16T21:08:00.000Z",
  });

  const approvals: DashboardApproval[] = [
    { id: "approval_oakland", organizationId: "org_oakland", organizationName: "Oakland Food Bank", approvalRole: "site_reviewer", status: "pending" },
    { id: "approval_vendor", organizationId: "org_vendor", organizationName: "Bay Fresh Foods", approvalRole: "vendor_representative", status: "pending" },
    { id: "approval_logistics", organizationId: "org_logistics", organizationName: "Bay Relief Logistics", approvalRole: "logistics_coordinator", status: "pending" },
    { id: "approval_fremont", organizationId: "org_fremont", organizationName: "Fremont Food Bank", approvalRole: "site_reviewer", status: "pending" },
  ];
  const timeline: TimelineEvent[] = [
    { id: "event_alert", timestamp: DEMO_NOW, actor: "Disruption agent", kind: "trigger", title: "Flood alert matched Fremont", detail: "NWS severe alert intersected the registered Fremont service area." },
    { id: "event_forecast", timestamp: "2026-07-16T21:01:00.000Z", actor: "Fremont site agent", kind: "tool", title: "Shortage calculated", detail: "Forecast, inventory, reservations, in-transit supply, and safety stock produced a 150-unit shortage." },
    { id: "event_request", timestamp: requestMessage.createdAt, actor: "Fremont site agent", kind: "agent", title: "Structured request published", detail: requestMessage.explanation },
    { id: "event_offers", timestamp: vendorOffer.createdAt, actor: "Oakland + Bay Fresh agents", kind: "agent", title: "Offers collected", detail: "Oakland offered 100 units and Bay Fresh offered 50 units; neither commitment is active yet." },
    { id: "event_logistics", timestamp: logisticsOffer.createdAt, actor: "Logistics agent", kind: "tool", title: "Route validated", detail: logisticsOffer.explanation },
    { id: "event_optimizer", timestamp: proposalMessage.createdAt, actor: "ATLAS orchestrator", kind: "system", title: "Allocation proposed", detail: proposalMessage.explanation },
  ];

  return {
    mode: "synthetic",
    inventoryIntake: { status: "draft", site: "Oakland Food Bank", detectionCount: 0, confirmedCount: 0 },
    activeImpact: { title: "Flood Watch — Alameda County", severity: "Severe", affectedSite: "Fremont Food Bank", source: "National Weather Service" },
    network: [
      { name: "Fremont Food Bank", type: "food_bank", status: "Shortage", detail: "150 canned goods needed" },
      { name: "Oakland Food Bank", type: "food_bank", status: "Offer", detail: "100 units available" },
      { name: "Bay Fresh Foods", type: "vendor", status: "Offer", detail: "50 units available" },
      { name: "Bay Relief Logistics", type: "logistics", status: "Feasible", detail: "180-unit vehicle available" },
    ],
    proposal: {
      id: "proposal_fremont_001",
      negotiationId,
      status: "awaiting_approvals",
      category: "canned_goods",
      neededBy: NEEDED_BY,
      requestingSite: "Fremont Food Bank",
      explanation: "Move 100 units from Oakland and 50 from Bay Fresh. All four organizations must approve before ATLAS creates reservations or a shipment.",
      calculation: request.breakdown,
      allocations: optimized.allocations,
      approvals,
    },
    messages: [requestMessage, oaklandOffer, vendorOffer, logisticsOffer, proposalMessage],
    timeline,
  };
}
