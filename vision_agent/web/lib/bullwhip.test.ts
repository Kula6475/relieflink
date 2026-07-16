import { describe, expect, it } from "vitest";

import { calculateRequest, isWithinCooldown } from "./bullwhip";

const policy = {
  smoothingAlpha: 0.5,
  maximumOrderChangeRatio: 0.25,
  confidenceThreshold: 0.7,
  safetyStock: 20,
  cooldownHours: 6,
  unusualChangeRatio: 0.5,
};

describe("bullwhip controls", () => {
  it("caps request changes and keeps forecast separate", () => {
    const result = calculateRequest({ previousForecast: 100, observedDemand: 300, weatherMultiplier: 1.5, onHand: 0, reserved: 0, inTransit: 0, previousRequestedQuantity: 100, confidence: 0.9, policy });
    expect(result.breakdown.forecastDemand).toBe(300);
    expect(result.breakdown.requestedQuantity).toBe(125);
  });

  it("suppresses low-confidence requests", () => {
    const result = calculateRequest({ previousForecast: 100, observedDemand: 120, weatherMultiplier: 1, onHand: 0, reserved: 0, inTransit: 0, previousRequestedQuantity: 100, confidence: 0.4, policy });
    expect(result.suppressed).toBe(true);
    expect(result.breakdown.requestedQuantity).toBe(0);
  });

  it("enforces request cooldowns", () => {
    expect(isWithinCooldown(new Date("2026-01-01T10:00:00Z"), new Date("2026-01-01T12:00:00Z"), 6)).toBe(true);
  });
});
