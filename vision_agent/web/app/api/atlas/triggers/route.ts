import { NextResponse } from "next/server";
import { z } from "zod";

import { getSession } from "../../../../lib/auth";
import { sql } from "../../../../lib/db";

const Trigger = z.object({
  triggerType: z.enum(["weather_alert", "fema_declaration", "shortage_threshold", "inventory_change", "vendor_availability", "proposal_rejected", "proposal_expired"]),
  reference: z.string().min(1).max(300),
  siteId: z.string().uuid().optional(),
  payload: z.record(z.string(), z.unknown()).default({}),
});

export async function POST(request: Request) {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Authentication required" }, { status: 401 });
  try {
    const input = Trigger.parse(await request.json());
    const orchestrators = await sql()`SELECT id FROM agents WHERE agent_type = 'orchestrator' AND active = true LIMIT 1`;
    if (!orchestrators[0]) throw new Error("No active ATLAS orchestrator is configured");
    const runs = await sql()`INSERT INTO agent_runs
      (agent_id, trigger_type, trigger_reference, status, input)
      VALUES (${orchestrators[0].id}, ${input.triggerType}, ${input.reference}, 'running',
        ${JSON.stringify({ siteId: input.siteId, ...input.payload })})
      RETURNING id, status, started_at`;
    return NextResponse.json({ run: runs[0], next: "site_assessment" }, { status: 202 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Invalid trigger" }, { status: 400 });
  }
}
