import { NextResponse } from "next/server";
import { z } from "zod";

import { decideDemoApproval } from "../../../../../lib/atlas/demo-store";
import { decidePersistentApproval } from "../../../../../lib/atlas/persistent-approvals";
import { getSession } from "../../../../../lib/auth";

const Decision = z.object({ decision: z.enum(["approved", "rejected"]) });

export async function POST(
  request: Request,
  context: { params: Promise<{ approvalId: string }> },
) {
  try {
    const body = Decision.parse(await request.json());
    const { approvalId } = await context.params;
    if (process.env.ATLAS_SYNTHETIC_MODE !== "true" && process.env.DATABASE_URL) {
      const session = await getSession();
      if (!session) return NextResponse.json({ error: "Authentication required" }, { status: 401 });
      const result = await decidePersistentApproval({ approvalId, decision: body.decision, session });
      return NextResponse.json(result);
    }
    return NextResponse.json(decideDemoApproval(approvalId, body.decision));
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Invalid decision" },
      { status: 400 },
    );
  }
}
