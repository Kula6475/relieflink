import { describe, expect, it } from "vitest";

import { assertReservationIsSafe, deriveInventoryPosition } from "./inventory";

describe("immutable inventory", () => {
  it("ignores unapproved transactions", () => {
    const position = deriveInventoryPosition([
      { quantity: 100, direction: "in", approvalStatus: "approved" },
      { quantity: 900, direction: "in", approvalStatus: "pending" },
      { quantity: 20, direction: "out", approvalStatus: "approved" },
    ], 10, 15);
    expect(position).toEqual({ onHand: 80, reserved: 10, inTransit: 15, available: 70 });
  });

  it("preserves safety stock when reserving", () => {
    expect(() => assertReservationIsSafe({ onHand: 100, alreadyReserved: 10, requested: 50, safetyStock: 50 })).toThrow(/40/);
  });
});
