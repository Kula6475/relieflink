import OpenAI from "openai";

export type Detection = {
  x: number;
  y: number;
  width: number;
  height: number;
  confidence: number;
  className: string;
};

export type VisionResult = {
  imageDataUrl: string;
  imageWidth: number;
  imageHeight: number;
  yoloModel: string;
  detections: Detection[];
  visibleObjectCount: number;
  averageConfidence: number;
  classification: {
    product: string;
    category: string;
    packaging: string;
    source: "vision_llm" | "operator_required";
    confidence: number;
    uncertainty: string | null;
  };
  disagreement: string | null;
  mode: "cloud" | "synthetic";
};

function syntheticDetections(count = 100): Detection[] {
  return Array.from({ length: count }, (_, index) => {
    const column = index % 10;
    const row = Math.floor(index / 10);
    return {
      x: 45 + column * 90,
      y: 28 + row * 58,
      width: 50,
      height: 45,
      confidence: 0.88 + (index % 5) * 0.018,
      className: "package",
    };
  });
}

async function runRoboflow(base64: string): Promise<{ predictions: Detection[]; width: number; height: number }> {
  const apiKey = process.env.ROBOFLOW_API_KEY;
  const model = process.env.YOLO_MODEL_ID;
  if (!apiKey || !model) throw new Error("Roboflow is not configured");
  const response = await fetch(
    `https://detect.roboflow.com/${encodeURIComponent(model)}?api_key=${encodeURIComponent(apiKey)}&confidence=35&overlap=30`,
    { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: base64 },
  );
  if (!response.ok) throw new Error(`Roboflow inference failed (${response.status})`);
  const result = await response.json() as {
    image?: { width?: number; height?: number };
    predictions?: Array<{ x: number; y: number; width: number; height: number; confidence: number; class: string }>;
  };
  return {
    width: result.image?.width ?? 900,
    height: result.image?.height ?? 600,
    predictions: (result.predictions ?? []).map((item) => ({
      x: item.x,
      y: item.y,
      width: item.width,
      height: item.height,
      confidence: item.confidence,
      className: item.class,
    })),
  };
}

async function classifyWithVision(imageDataUrl: string) {
  if (!process.env.OPENAI_API_KEY) return null;
  const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
  const completion = await client.chat.completions.create({
    model: process.env.OPENAI_VISION_MODEL ?? "gpt-4.1-mini",
    messages: [{
      role: "user",
      content: [
        { type: "text", text: "Identify the food product and broad category. Do not count objects. Return JSON with product, category, packaging, confidence from 0 to 1, and uncertainty (string or null)." },
        { type: "image_url", image_url: { url: imageDataUrl } },
      ],
    }],
    response_format: { type: "json_object" },
  });
  return JSON.parse(completion.choices[0]?.message.content ?? "{}") as {
    product?: string;
    category?: string;
    packaging?: string;
    confidence?: number;
    uncertainty?: string | null;
  };
}

export async function analyzeStillImage(input: {
  bytes: Buffer;
  contentType: string;
  synthetic: boolean;
}): Promise<VisionResult> {
  const base64 = input.bytes.toString("base64");
  const imageDataUrl = `data:${input.contentType};base64,${base64}`;
  let detections: Detection[];
  let imageWidth = 900;
  let imageHeight = 600;
  let mode: "cloud" | "synthetic" = "cloud";
  if (input.synthetic || !process.env.ROBOFLOW_API_KEY || !process.env.YOLO_MODEL_ID) {
    detections = syntheticDetections();
    mode = "synthetic";
  } else {
    const result = await runRoboflow(base64);
    detections = result.predictions;
    imageWidth = result.width;
    imageHeight = result.height;
  }
  const llm = input.synthetic ? null : await classifyWithVision(imageDataUrl);
  const classification = llm ? {
    product: llm.product ?? "Unconfirmed food package",
    category: llm.category ?? "uncategorized",
    packaging: llm.packaging ?? "unknown",
    source: "vision_llm" as const,
    confidence: llm.confidence ?? 0.5,
    uncertainty: llm.uncertainty ?? null,
  } : {
    product: "Demo canned-food package",
    category: "canned_goods",
    packaging: "can",
    source: "operator_required" as const,
    confidence: 0.72,
    uncertainty: "Synthetic classification; an operator must confirm the category.",
  };
  const classSet = new Set(detections.map((item) => item.className.toLowerCase()));
  const disagreement = classSet.size > 1
    ? `Detector returned multiple package classes: ${[...classSet].join(", ")}`
    : null;
  return {
    imageDataUrl,
    imageWidth,
    imageHeight,
    yoloModel: process.env.YOLO_MODEL_ID ?? "synthetic-package-counter-v1",
    detections,
    visibleObjectCount: detections.length,
    averageConfidence: detections.length
      ? detections.reduce((sum, item) => sum + item.confidence, 0) / detections.length
      : 0,
    classification,
    disagreement,
    mode,
  };
}
