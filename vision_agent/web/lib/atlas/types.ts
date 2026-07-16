import type { AgentMessage, Allocation, ForecastBreakdown, ProposalStatus } from "../domain";
import type { ApprovalRole } from "../approvals";

export type DashboardApproval = {
  id: string;
  organizationId: string;
  organizationName: string;
  approvalRole: ApprovalRole;
  status: "pending" | "approved" | "rejected";
  decidedBy?: string;
};

export type TimelineEvent = {
  id: string;
  timestamp: string;
  actor: string;
  kind: "trigger" | "agent" | "tool" | "human" | "system";
  title: string;
  detail: string;
};

export type AtlasProposal = {
  id: string;
  negotiationId: string;
  status: ProposalStatus;
  category: string;
  neededBy: string;
  requestingSite: string;
  explanation: string;
  calculation: ForecastBreakdown;
  allocations: Allocation[];
  approvals: DashboardApproval[];
};

export type AtlasDashboardState = {
  mode: "synthetic" | "persistent";
  inventoryIntake: {
    status: "draft" | "pending" | "approved";
    site: string;
    detectionCount: number;
    confirmedCount: number;
  };
  activeImpact: {
    title: string;
    severity: string;
    affectedSite: string;
    source: string;
  };
  network: Array<{
    name: string;
    type: "food_bank" | "vendor" | "logistics";
    status: string;
    detail: string;
  }>;
  proposal: AtlasProposal;
  messages: AgentMessage[];
  timeline: TimelineEvent[];
};
