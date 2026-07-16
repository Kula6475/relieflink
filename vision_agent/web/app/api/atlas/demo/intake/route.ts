import { NextResponse } from "next/server";
import { z } from "zod";

import { updateDemoIntake } from "../../../../../lib/atlas/demo-store";

const Intake = z.object({
  action: z.enum(["submit", "approve"]),
  detectionCount: z.number().int().nonnegative(),
  confirmedCount: z.number().int().nonnegative(),
});

export async function POST(request: Request) {
  try {
    const input = Intake.parse(await request.json());
    return NextResponse.json(updateDemoIntake(input.action, input.detectionCount, input.confirmedCount));
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Invalid intake action" }, { status: 400 });
  }
}
