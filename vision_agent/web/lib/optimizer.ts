import type { Allocation, AllocationInput } from "./domain";

/** Deterministic minimum-cost allocation fallback for the hosted MVP.
 * Sources are sorted by distance and feasible capacity. The same validated payload can
 * be sent to the Python OR-Tools service; this fallback keeps synthetic demos available.
 */
export function allocateMinimumCost(
  requestedQuantity: number,
  sources: AllocationInput[],
): { allocations: Allocation[]; unfilledQuantity: number } {
  let remaining = Math.max(0, Math.floor(requestedQuantity));
  const ordered = [...sources].sort(
    (a, b) => a.distanceMiles - b.distanceMiles || a.sourceId.localeCompare(b.sourceId),
  );
  const allocations: Allocation[] = [];
  for (const source of ordered) {
    const feasible = Math.max(0, Math.min(source.availableQuantity, source.capacityQuantity));
    const quantity = Math.min(remaining, Math.floor(feasible));
    if (quantity === 0) continue;
    allocations.push({ ...source, quantity, estimatedCost: quantity * source.distanceMiles });
    remaining -= quantity;
    if (remaining === 0) break;
  }
  return { allocations, unfilledQuantity: remaining };
}
