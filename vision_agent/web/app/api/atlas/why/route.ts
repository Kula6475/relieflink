import { NextResponse } from "next/server";
import { z } from "zod";

const Why = z.object({ question: z.string().min(2).max(500), evidence: z.record(z.string(), z.unknown()) });

export async function POST(request: Request) {
  try {
    const input = Why.parse(await request.json());
    const serviceUrl = process.env.OPTIMIZER_URL ?? "http://localhost:8000";
    try {
      const response = await fetch(`${serviceUrl}/atlas/advisor`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      });
      if (response.ok) return NextResponse.json(await response.json());
    } catch {
      // The hosted UI remains useful when the optional Python service is offline.
    }
    const calculation = input.evidence.calculation as Record<string, unknown> | undefined;
    return NextResponse.json({
      answer: `ATLAS separated the ${calculation?.forecastDemand ?? "forecast"}-unit forecast from the ${calculation?.requestedQuantity ?? "calculated"}-unit request, then validated offers and logistics. Every affected organization must still approve its own commitment.`,
      mode: "fallback",
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Invalid question" }, { status: 400 });
  }
}
