import { describe, expect, it } from "vitest";

import { allocateMinimumCost } from "./optimizer";

describe("allocation fallback", () => {
  it("fills nearest feasible sources first", () => {
    const result = allocateMinimumCost(150, [
      { sourceId: "vendor", sourceType: "vendor", organizationId: "v", availableQuantity: 80, capacityQuantity: 80, distanceMiles: 35, earliestPickup: "now", refrigerated: false },
      { sourceId: "oakland", sourceType: "site", organizationId: "o", availableQuantity: 100, capacityQuantity: 100, distanceMiles: 28, earliestPickup: "now", refrigerated: false },
    ]);
    expect(result.allocations.map((item) => [item.sourceId, item.quantity])).toEqual([["oakland", 100], ["vendor", 50]]);
    expect(result.unfilledQuantity).toBe(0);
  });
});
