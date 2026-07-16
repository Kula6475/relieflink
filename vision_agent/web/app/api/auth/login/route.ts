import { NextResponse } from "next/server";
import { z } from "zod";

import { authenticate, setSession } from "../../../../lib/auth";

const Login = z.object({ email: z.string().email(), password: z.string().min(8) });

export async function POST(request: Request) {
  try {
    const credentials = Login.parse(await request.json());
    const session = await authenticate(credentials.email, credentials.password);
    if (!session) return NextResponse.json({ error: "Invalid email or password" }, { status: 401 });
    await setSession(session);
    return NextResponse.json({ user: session });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to sign in" },
      { status: 400 },
    );
  }
}
