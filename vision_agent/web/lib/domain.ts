export const MESSAGE_TYPES = [
  "supply_request", "supply_offer", "counteroffer", "logistics_check",
  "logistics_offer", "proposal", "acceptance", "rejection", "escalation",
  "cancellation",
] as const;

export type MessageType = (typeof MESSAGE_TYPES)[number];
export type ProposalStatus =
  | "draft" | "negotiating" | "awaiting_approvals" | "approved"
  | "reserved" | "dispatched" | "received" | "rejected" | "expired"
  | "cancelled" | "failed";

export type AgentMessage = {
  id: string;
  negotiationId: string;
  senderAgentId: string;
  recipientAgentId?: string;
  recipientScope?: string;
  messageType: MessageType;
  payload: Record<string, unknown>;
  parentMessageId?: string;
  agentRunId: string;
  explanation: string;
  status: "active" | "accepted" | "rejected" | "expired" | "cancelled";
  expiresAt: string;
  createdAt: string;
};

export type ForecastBreakdown = {
  baselineDemand: number;
  observedRecentDemand: number;
  weatherAdjustment: number;
  forecastDemand: number;
  onHandInventory: number;
  reservedInventory: number;
  inTransitInventory: number;
  safetyStock: number;
  calculatedShortage: number;
  requestedQuantity: number;
  optimizerRecommendedQuantity: number;
  humanApprovedQuantity: number | null;
  confidence: number;
};

export type AllocationInput = {
  sourceId: string;
  sourceType: "site" | "vendor";
  organizationId: string;
  availableQuantity: number;
  distanceMiles: number;
  capacityQuantity: number;
  earliestPickup: string;
  refrigerated: boolean;
};

export type Allocation = AllocationInput & { quantity: number; estimatedCost: number };
