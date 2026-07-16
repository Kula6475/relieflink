import { NextResponse } from "next/server";

import { resetDemoState } from "../../../../lib/atlas/demo-store";

export async function POST() {
  return NextResponse.json(resetDemoState());
}
