import OpenAI from "openai";
import { config } from "dotenv";
import { resolve } from "node:path";
import sharp from "sharp";

const localEnvironment = {
  ...(config({ path: resolve(process.cwd(), "../../.env"), override: false, quiet: true }).parsed ?? {}),
  ...(config({ path: resolve(process.cwd(), ".env"), override: false, quiet: true }).parsed ?? {}),
};

function setting(name: string) {
  return process.env[name] || localEnvironment[name];
}

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
  countMethod: "tiled_package_detection" | "synthetic_demo";
  countNote: string;
  mode: "cloud" | "synthetic";
};

export function shouldUseSyntheticMode(requestedMode: string | null, defaultSynthetic: boolean) {
  if (requestedMode === "true") return true;
  if (requestedMode === "false") return false;
  return defaultSynthetic;
}

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

type RoboflowResponse = {
  image?: { width?: number; height?: number };
  predictions?: Array<{ x: number; y: number; width: number; height: number; confidence: number; class: string }>;
};

async function runRoboflowRequest(base64: string, apiKey: string, model: string) {
  const response = await fetch(
    `https://serverless.roboflow.com/${model.split("/").map((part) => encodeURIComponent(part)).join("/")}?api_key=${encodeURIComponent(apiKey)}&confidence=${encodeURIComponent(setting("YOLO_CONFIDENCE") ?? "20")}&overlap=30`,
    { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: base64 },
  );
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 300);
    throw new Error(`Roboflow inference for ${model} failed (${response.status}): ${detail}`);
  }
  return await response.json() as RoboflowResponse;
}

function filterPredictions(result: RoboflowResponse): Detection[] {
  const countClasses = (setting("YOLO_COUNT_CLASSES") ?? "")
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
  return (result.predictions ?? []).map((item) => ({
    x: item.x,
    y: item.y,
    width: item.width,
    height: item.height,
    confidence: item.confidence,
    className: item.class,
  })).filter((item) => countClasses.length === 0 || countClasses.includes(item.className.toLowerCase()));
}

function intersectionOverUnion(first: Detection, second: Detection) {
  const firstLeft = first.x - first.width / 2;
  const firstTop = first.y - first.height / 2;
  const secondLeft = second.x - second.width / 2;
  const secondTop = second.y - second.height / 2;
  const intersectionWidth = Math.max(0, Math.min(firstLeft + first.width, secondLeft + second.width) - Math.max(firstLeft, secondLeft));
  const intersectionHeight = Math.max(0, Math.min(firstTop + first.height, secondTop + second.height) - Math.max(firstTop, secondTop));
  const intersection = intersectionWidth * intersectionHeight;
  const union = first.width * first.height + second.width * second.height - intersection;
  return union ? intersection / union : 0;
}

function suppressDuplicateDetections(detections: Detection[]) {
  const threshold = Number(setting("YOLO_NMS_IOU") ?? "0.45");
  const kept: Detection[] = [];
  for (const detection of [...detections].sort((a, b) => b.confidence - a.confidence)) {
    if (!kept.some((existing) => existing.className === detection.className && intersectionOverUnion(existing, detection) >= threshold)) {
      kept.push(detection);
    }
  }
  return kept;
}

async function runRoboflow(bytes: Buffer): Promise<{ predictions: Detection[]; width: number; height: number }> {
  const apiKey = setting("ROBOFLOW_API_KEY");
  const model = setting("YOLO_MODEL_ID");
  if (!apiKey || !model) throw new Error("Roboflow is not configured");
  const metadata = await sharp(bytes).metadata();
  const width = metadata.width ?? 900;
  const height = metadata.height ?? 600;
  const grid = Math.max(1, Math.min(3, Math.round(Number(setting("YOLO_TILE_GRID") ?? "3"))));
  if (grid === 1) {
    const result = await runRoboflowRequest(bytes.toString("base64"), apiKey, model);
    return { width, height, predictions: filterPredictions(result) };
  }

  const overlap = Math.min(0.45, Math.max(0.1, Number(setting("YOLO_TILE_OVERLAP") ?? "0.25")));
  const tileWidth = Math.min(width, Math.ceil((width * (1 + overlap)) / (grid + overlap)));
  const tileHeight = Math.min(height, Math.ceil((height * (1 + overlap)) / (grid + overlap)));
  const tiles = Array.from({ length: grid * grid }, (_, index) => {
    const column = index % grid;
    const row = Math.floor(index / grid);
    const left = grid === 1 ? 0 : Math.round((width - tileWidth) * column / (grid - 1));
    const top = grid === 1 ? 0 : Math.round((height - tileHeight) * row / (grid - 1));
    return { left, top };
  });
  const tileResults = await Promise.all(tiles.map(async ({ left, top }) => {
    const tileBytes = await sharp(bytes).extract({ left, top, width: tileWidth, height: tileHeight }).jpeg({ quality: 90 }).toBuffer();
    const result = await runRoboflowRequest(tileBytes.toString("base64"), apiKey, model);
    const resultWidth = result.image?.width ?? tileWidth;
    const resultHeight = result.image?.height ?? tileHeight;
    return filterPredictions(result).map((detection) => ({
      ...detection,
      x: left + detection.x * tileWidth / resultWidth,
      y: top + detection.y * tileHeight / resultHeight,
      width: detection.width * tileWidth / resultWidth,
      height: detection.height * tileHeight / resultHeight,
    }));
  }));
  return {
    width,
    height,
    predictions: suppressDuplicateDetections(tileResults.flat()),
  };
}

async function classifyWithVision(imageDataUrl: string) {
  const apiKey = setting("OPENAI_API_KEY");
  if (!apiKey) return null;
  const client = new OpenAI({ apiKey });
  const completion = await client.chat.completions.create({
    model: setting("OPENAI_VISION_MODEL") ?? "gpt-4.1-mini",
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
  if (input.synthetic) {
    detections = syntheticDetections();
    mode = "synthetic";
  } else {
    const missing = [
      !setting("ROBOFLOW_API_KEY") ? "ROBOFLOW_API_KEY" : null,
      !setting("YOLO_MODEL_ID") ? "YOLO_MODEL_ID" : null,
    ].filter(Boolean);
    if (missing.length) {
      throw new Error(
        `Cloud detection was selected, but ${missing.join(" and ")} is missing. Add it to the repository .env or vision_agent/web/.env.local, then restart Next.js.`,
      );
    }
    const result = await runRoboflow(input.bytes);
    detections = result.predictions;
    imageWidth = result.width;
    imageHeight = result.height;
  }
  const llm = mode === "cloud" ? await classifyWithVision(imageDataUrl) : null;
  const classification = llm ? {
    product: llm.product ?? "Unconfirmed food package",
    category: llm.category ?? "uncategorized",
    packaging: llm.packaging ?? "unknown",
    source: "vision_llm" as const,
    confidence: llm.confidence ?? 0.5,
    uncertainty: llm.uncertainty ?? null,
  } : mode === "synthetic" ? {
    product: "Demo canned-food package",
    category: "canned_goods",
    packaging: "can",
    source: "operator_required" as const,
    confidence: 0.72,
    uncertainty: "Synthetic classification; an operator must confirm the category.",
  } : {
    product: "Unclassified detected package",
    category: "operator_review",
    packaging: "unknown",
    source: "operator_required" as const,
    confidence: 0,
    uncertainty: "Roboflow counted visible packages, but OPENAI_API_KEY is not configured for product/category classification. An operator must classify them.",
  };
  const classSet = new Set(detections.map((item) => item.className.toLowerCase()));
  const disagreement = classSet.size > 1
    ? `Detector returned multiple package classes: ${[...classSet].join(", ")}`
    : null;
  return {
    imageDataUrl,
    imageWidth,
    imageHeight,
    yoloModel: mode === "cloud"
      ? String(setting("YOLO_MODEL_ID"))
      : "synthetic-package-counter-v1",
    detections,
    visibleObjectCount: detections.length,
    averageConfidence: detections.length
      ? detections.reduce((sum, item) => sum + item.confidence, 0) / detections.length
      : 0,
    classification,
    disagreement,
    countMethod: mode === "cloud" ? "tiled_package_detection" : "synthetic_demo",
    countNote: mode === "cloud"
      ? "Visible package count from overlapping camera tiles. Closed cartons and hidden items require a label, packing slip, or human confirmation."
      : "Synthetic count for UI testing; replace with a real still-image analysis before recording inventory.",
    mode,
  };
}
