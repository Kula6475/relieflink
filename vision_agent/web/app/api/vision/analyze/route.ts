import { NextResponse } from "next/server";

import { analyzeStillImage, shouldUseSyntheticMode } from "../../../../lib/vision";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const form = await request.formData();
    const image = form.get("image");
    if (!(image instanceof File)) {
      return NextResponse.json({ error: "A still image is required" }, { status: 400 });
    }
    if (!image.type.startsWith("image/")) {
      return NextResponse.json({ error: "Only image uploads are accepted" }, { status: 415 });
    }
    if (image.size > 8 * 1024 * 1024) {
      return NextResponse.json({ error: "Image must be 8 MB or smaller" }, { status: 413 });
    }
    const requestedMode = form.get("synthetic");
    const synthetic = shouldUseSyntheticMode(
      typeof requestedMode === "string" ? requestedMode : null,
      process.env.ATLAS_SYNTHETIC_MODE === "true",
    );
    const result = await analyzeStillImage({
      bytes: Buffer.from(await image.arrayBuffer()),
      contentType: image.type,
      synthetic,
    });
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Vision analysis failed" },
      { status: 500 },
    );
  }
}
