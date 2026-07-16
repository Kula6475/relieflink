export type ApprovalRole =
  | "site_reviewer"
  | "vendor_representative"
  | "logistics_coordinator"
  | "administrator";

export type ApprovalRequirement = {
  organizationId: string;
  approvalRole: ApprovalRole;
  status: "pending" | "approved" | "rejected" | "expired";
};

const MEMBERSHIP_FOR_APPROVAL: Record<ApprovalRole, string[]> = {
  site_reviewer: ["reviewer", "administrator"],
  vendor_representative: ["vendor_representative", "administrator"],
  logistics_coordinator: ["logistics_coordinator", "administrator"],
  administrator: ["administrator"],
};

export function mayDecideApproval(input: {
  requirement: ApprovalRequirement;
  actorOrganizationId: string;
  actorRoles: string[];
  globalRole?: string;
}) {
  if (input.globalRole === "administrator") return true;
  return input.requirement.organizationId === input.actorOrganizationId
    && MEMBERSHIP_FOR_APPROVAL[input.requirement.approvalRole]
      .some((role) => input.actorRoles.includes(role));
}

export function approvalOutcome(requirements: ApprovalRequirement[]) {
  if (requirements.some((requirement) => requirement.status === "rejected")) return "rejected";
  if (requirements.some((requirement) => requirement.status === "expired")) return "expired";
  if (requirements.length > 0 && requirements.every((requirement) => requirement.status === "approved")) {
    return "approved";
  }
  return "awaiting_approvals";
}
