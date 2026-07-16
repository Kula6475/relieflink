import type { ForecastBreakdown } from "./domain";

export type BullwhipPolicy = {
  smoothingAlpha: number;
  maximumOrderChangeRatio: number;
  confidenceThreshold: number;
  safetyStock: number;
  cooldownHours: number;
  unusualChangeRatio: number;
};

export function smoothDemand(previous: number, observed: number, alpha: number) {
  if (alpha < 0 || alpha > 1) throw new Error("smoothing alpha must be between 0 and 1");
  return previous * (1 - alpha) + observed * alpha;
}

export function calculateRequest(input: {
  previousForecast: number;
  observedDemand: number;
  weatherMultiplier: number;
  onHand: number;
  reserved: number;
  inTransit: number;
  previousRequestedQuantity: number;
  confidence: number;
  policy: BullwhipPolicy;
}): { breakdown: ForecastBreakdown; requiresHumanReview: boolean; suppressed: boolean } {
  const smoothed = smoothDemand(
    input.previousForecast,
    input.observedDemand,
    input.policy.smoothingAlpha,
  );
  const forecastDemand = Math.max(0, Math.ceil(smoothed * input.weatherMultiplier));
  const available = Math.max(0, input.onHand - input.reserved + input.inTransit);
  const shortage = Math.max(0, forecastDemand + input.policy.safetyStock - available);
  const upperBound = input.previousRequestedQuantity > 0
    ? Math.ceil(input.previousRequestedQuantity * (1 + input.policy.maximumOrderChangeRatio))
    : shortage;
  const requested = Math.min(shortage, upperBound);
  const changeRatio = input.previousRequestedQuantity > 0
    ? Math.abs(requested - input.previousRequestedQuantity) / input.previousRequestedQuantity
    : requested > 0 ? 1 : 0;
  const suppressed = input.confidence < input.policy.confidenceThreshold;
  return {
    breakdown: {
      baselineDemand: input.previousForecast,
      observedRecentDemand: input.observedDemand,
      weatherAdjustment: input.weatherMultiplier,
      forecastDemand,
      onHandInventory: input.onHand,
      reservedInventory: input.reserved,
      inTransitInventory: input.inTransit,
      safetyStock: input.policy.safetyStock,
      calculatedShortage: shortage,
      requestedQuantity: suppressed ? 0 : requested,
      optimizerRecommendedQuantity: 0,
      humanApprovedQuantity: null,
      confidence: input.confidence,
    },
    requiresHumanReview: changeRatio >= input.policy.unusualChangeRatio,
    suppressed,
  };
}

export function isWithinCooldown(lastRequestAt: Date | null, now: Date, cooldownHours: number) {
  if (!lastRequestAt) return false;
  return now.getTime() - lastRequestAt.getTime() < cooldownHours * 3_600_000;
}
