import { createHash } from "node:crypto";

import { hash } from "bcryptjs";
import { NextResponse } from "next/server";
import { z } from "zod";

import { setSession } from "../../../../lib/auth";
import { withTransaction } from "../../../../lib/db";

const Acceptance = z.object({
  token: z.string().min(20),
  displayName: z.string().min(2).max(100),
  password: z.string().min(12).max(200),
});

export async function POST(request: Request) {
  try {
    const input = Acceptance.parse(await request.json());
    const tokenHash = createHash("sha256").update(input.token).digest("hex");
    const passwordHash = await hash(input.password, 12);
    const user = await withTransaction(async (client) => {
      const found = await client.query(
        `SELECT * FROM invitations WHERE token_hash = $1 AND accepted_at IS NULL
         AND expires_at > now() FOR UPDATE`,
        [tokenHash],
      );
      const invitation = found.rows[0];
      if (!invitation) throw new Error("Invitation is invalid or expired");
      const existing = await client.query("SELECT id FROM users WHERE email = $1", [invitation.email]);
      if (existing.rowCount) throw new Error("This email already has an account; sign in before accepting another membership");
      const users = await client.query(
        "INSERT INTO users (email, password_hash, display_name) VALUES ($1, $2, $3) RETURNING *",
        [invitation.email, passwordHash, input.displayName],
      );
      const created = users.rows[0];
      await client.query(
        `INSERT INTO organization_memberships (organization_id, user_id, role, site_id)
         VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING`,
        [invitation.organization_id, created.id, invitation.role, invitation.site_id],
      );
      await client.query("UPDATE invitations SET accepted_at = now() WHERE id = $1", [invitation.id]);
      return created;
    });
    await setSession({
      userId: String(user.id), email: String(user.email), displayName: String(user.display_name),
      globalRole: user.global_role === "administrator" ? "administrator" : "member",
    });
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Unable to accept invitation" }, { status: 400 });
  }
}
