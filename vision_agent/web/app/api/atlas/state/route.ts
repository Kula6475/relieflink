import { NextResponse } from "next/server";

import { getDemoState } from "../../../../lib/atlas/demo-store";
import { loadPersistentDashboardState } from "../../../../lib/atlas/repository";
import { getSession } from "../../../../lib/auth";

export const dynamic = "force-dynamic";

export async function GET() {
  if (process.env.ATLAS_SYNTHETIC_MODE !== "true" && process.env.DATABASE_URL) {
    try {
      const session = await getSession();
      if (!session) return NextResponse.json({ error: "Authentication required" }, { status: 401 });
      return NextResponse.json(await loadPersistentDashboardState(session));
    } catch (error) {
      return NextResponse.json(
        { error: error instanceof Error ? error.message : "Unable to load ATLAS state" },
        { status: 500 },
      );
    }
  }
  return NextResponse.json(getDemoState());
}
