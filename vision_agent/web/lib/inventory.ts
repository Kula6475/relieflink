export type InventoryTransaction = {
  quantity: number;
  direction: "in" | "out" | "hold" | "release";
  approvalStatus: "pending" | "approved" | "rejected";
};

export type InventoryPosition = {
  onHand: number;
  reserved: number;
  inTransit: number;
  available: number;
};

export function deriveInventoryPosition(
  transactions: InventoryTransaction[],
  activeReservations: number,
  inTransit: number,
): InventoryPosition {
  const onHand = transactions
    .filter((transaction) => transaction.approvalStatus === "approved")
    .reduce((total, transaction) => {
      if (transaction.direction === "in") return total + transaction.quantity;
      if (transaction.direction === "out") return total - transaction.quantity;
      return total;
    }, 0);
  const reserved = Math.max(0, activeReservations);
  return {
    onHand,
    reserved,
    inTransit: Math.max(0, inTransit),
    available: Math.max(0, onHand - reserved),
  };
}

export function assertReservationIsSafe(input: {
  onHand: number;
  alreadyReserved: number;
  requested: number;
  safetyStock: number;
}) {
  const reservable = Math.max(0, input.onHand - input.alreadyReserved - input.safetyStock);
  if (input.requested > reservable) {
    throw new Error(`Reservation exceeds safely available inventory (${reservable})`);
  }
}
