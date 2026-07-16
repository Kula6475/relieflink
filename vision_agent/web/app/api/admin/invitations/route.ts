import { createHash, randomBytes } from "node:crypto";

import { NextResponse } from "next/server";
import { z } from "zod";

import { getSession } from "../../../../lib/auth";
import { sql } from "../../../../lib/db";

const Invitation = z.object({
  organizationId: z.string().uuid(),
  email: z.string().email(),
  role: z.enum(["contributor", "reviewer", "vendor_representative", "logistics_coordinator", "administrator"]),
  siteId: z.string().uuid().optional(),
});

export async function POST(request: Request) {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Authentication required" }, { status: 401 });
  try {
    const input = Invitation.parse(await request.json());
    if (session.globalRole !== "administrator") {
      const allowed = await sql()`SELECT 1 FROM organization_memberships WHERE user_id = ${session.userId}
        AND organization_id = ${input.organizationId} AND role = 'administrator' LIMIT 1`;
      if (allowed.length === 0) return NextResponse.json({ error: "Administrator role required" }, { status: 403 });
    }
    const token = randomBytes(32).toString("base64url");
    const tokenHash = createHash("sha256").update(token).digest("hex");
    const rows = await sql()`INSERT INTO invitations
      (organization_id, email, role, site_id, token_hash, expires_at, invited_by)
      VALUES (${input.organizationId}, ${input.email}, ${input.role}, ${input.siteId ?? null},
       ${tokenHash}, now() + interval '7 days', ${session.userId}) RETURNING id, email, role, expires_at`;
    return NextResponse.json({ invitation: rows[0], token }, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Invalid invitation" }, { status: 400 });
  }
}
