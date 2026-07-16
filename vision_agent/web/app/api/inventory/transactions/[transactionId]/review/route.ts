import { NextResponse } from "next/server";
import { z } from "zod";

import { getSession } from "../../../../../../lib/auth";
import { withTransaction } from "../../../../../../lib/db";

const Review = z.object({ decision: z.enum(["approved", "rejected"]) });

export async function POST(request: Request, context: { params: Promise<{ transactionId: string }> }) {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Authentication required" }, { status: 401 });
  try {
    const { transactionId } = await context.params;
    const input = Review.parse(await request.json());
    const result = await withTransaction(async (client) => {
      const locked = await client.query(
        "SELECT * FROM inventory_transactions WHERE id = $1 FOR UPDATE",
        [transactionId],
      );
      const transaction = locked.rows[0];
      if (!transaction) throw new Error("Inventory transaction not found");
      if (transaction.approval_status !== "pending") throw new Error("Transaction already reviewed");
      if (String(transaction.operator_id) === session.userId) throw new Error("Operators cannot review their own observation");
      const membership = await client.query(
        `SELECT 1 FROM organization_memberships WHERE user_id = $1
         AND organization_id = $2 AND (site_id = $3 OR site_id IS NULL)
         AND role IN ('reviewer','administrator') LIMIT 1`,
        [session.userId, transaction.organization_id, transaction.site_id],
      );
      if (session.globalRole !== "administrator" && membership.rowCount === 0) {
        throw new Error("A reviewer for this site must decide the transaction");
      }
      const updated = await client.query(
        `UPDATE inventory_transactions SET approval_status = $1, reviewer_id = $2,
         approved_at = CASE WHEN $1 = 'approved' THEN now() ELSE NULL END WHERE id = $3
         RETURNING id, approval_status, reviewer_id, approved_at`,
        [input.decision, session.userId, transactionId],
      );
      return updated.rows[0];
    });
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Invalid review" }, { status: 400 });
  }
}
