import { NextResponse } from "next/server";
import { z } from "zod";

import { getSession } from "../../../../lib/auth";
import { sql } from "../../../../lib/db";

const Observation = z.object({
  organizationId: z.string().uuid(),
  siteId: z.string().uuid(),
  category: z.enum(["canned_goods", "produce", "dairy", "dry_goods"]),
  productName: z.string().min(1).max(200).optional(),
  quantity: z.number().int().positive(),
  yoloModelVersion: z.string().max(200),
  detectionCount: z.number().int().nonnegative(),
  averageConfidence: z.number().min(0).max(1),
  sourceImageReference: z.string().max(1000).optional(),
  idempotencyKey: z.string().min(8).max(200),
});

export async function POST(request: Request) {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Authentication required" }, { status: 401 });
  try {
    const input = Observation.parse(await request.json());
    const membership = await sql()`SELECT 1 FROM organization_memberships
      WHERE user_id = ${session.userId} AND organization_id = ${input.organizationId}
      AND (site_id = ${input.siteId} OR site_id IS NULL)
      AND role IN ('contributor','administrator') LIMIT 1`;
    if (session.globalRole !== "administrator" && membership.length === 0) {
      return NextResponse.json({ error: "You cannot submit inventory for this site" }, { status: 403 });
    }
    const rows = await sql()`INSERT INTO inventory_transactions
      (organization_id, site_id, category, product_name, quantity, direction,
       transaction_type, source, yolo_model_version, detection_count,
       average_confidence, source_image_reference, operator_id, idempotency_key)
      VALUES (${input.organizationId}, ${input.siteId}, ${input.category},
       ${input.productName ?? null}, ${input.quantity}, 'in', 'intake', 'yolo_still_image',
       ${input.yoloModelVersion}, ${input.detectionCount}, ${input.averageConfidence},
       ${input.sourceImageReference ?? null}, ${session.userId}, ${input.idempotencyKey})
      ON CONFLICT (idempotency_key) DO UPDATE SET idempotency_key = EXCLUDED.idempotency_key
      RETURNING id, approval_status, created_at`;
    return NextResponse.json(rows[0], { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Invalid observation" }, { status: 400 });
  }
}
