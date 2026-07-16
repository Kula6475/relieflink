import { describe, expect, it } from "vitest";

import { approvalOutcome, mayDecideApproval } from "./approvals";

describe("organization approvals", () => {
  it("does not approve until every organization approves", () => {
    expect(approvalOutcome([
      { organizationId: "foodbank", approvalRole: "site_reviewer", status: "approved" },
      { organizationId: "vendor", approvalRole: "vendor_representative", status: "pending" },
    ])).toBe("awaiting_approvals");
  });

  it("prevents one organization from approving another", () => {
    expect(mayDecideApproval({
      requirement: { organizationId: "vendor", approvalRole: "vendor_representative", status: "pending" },
      actorOrganizationId: "foodbank",
      actorRoles: ["reviewer"],
    })).toBe(false);
  });
});
