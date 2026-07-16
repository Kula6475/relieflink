/* ReliefLink edge detector: YOLOv8n running fully in the browser via onnxruntime-web.
 *
 * Loop: camera frame -> letterbox 640x640 -> YOLO -> per-category counts.
 * When counts are stable for STABLE_FRAMES consecutive frames AND differ from what we
 * last posted, one snapshot per category goes to the ledger. Take a can off the shelf
 * and the shared ledger updates itself a couple of seconds later.
 */

const MODEL_URL = "/models/yolov8n.onnx";
const SIZE = 640;
const SCORE_THRESHOLD = 0.4;
const IOU_THRESHOLD = 0.45;
const FRAME_INTERVAL_MS = 1200;
const STABLE_FRAMES = 2;

const CATEGORIES = ["canned_goods", "produce", "dairy", "dry_goods"];

// COCO class id -> ReliefLink category (demo stand-ins; fine-tune on shelf data later).
const CLASS_MAP = {
  39: "canned_goods", 41: "canned_goods",            // bottle, cup
  46: "produce", 47: "produce", 49: "produce",       // banana, apple, orange
  50: "produce", 51: "produce",                      // broccoli, carrot
  45: "dairy", 40: "dairy",                          // bowl, wine glass
  73: "dry_goods",                                   // book (box-shaped goods)
};

const COCO_NAMES = { 39: "bottle", 40: "wine glass", 41: "cup", 45: "bowl", 46: "banana",
  47: "apple", 49: "orange", 50: "broccoli", 51: "carrot", 73: "book" };

const video = document.getElementById("video");
const overlay = document.getElementById("overlay");
const logBox = document.getElementById("log");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");

let session = null;
let running = false;
let recentCounts = [];
let lastPosted = null;
let lastPostedAt = {};

function log(message) {
  const line = document.createElement("div");
  line.textContent = `${new Date().toLocaleTimeString()}  ${message}`;
  logBox.prepend(line);
  while (logBox.childElementCount > 60) logBox.lastChild.remove();
}

function setStatus(text, live) {
  statusText.textContent = text;
  statusDot.className = "status-dot" + (live ? " live" : "");
}

async function loadSites() {
  const select = document.getElementById("siteSelect");
  const sites = await (await fetch("/sites")).json();
  select.innerHTML = sites
    .map((site) => `<option value="${site.id}">${site.name}</option>`)
    .join("");
}

async function loadModel() {
  session = await ort.InferenceSession.create(MODEL_URL, {
    executionProviders: ["wasm"],
  });
  document.getElementById("modelStatus").textContent = "YOLOv8n loaded (on-device)";
}

function preprocess() {
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const context = canvas.getContext("2d");

  const scale = Math.min(SIZE / video.videoWidth, SIZE / video.videoHeight);
  const width = video.videoWidth * scale;
  const height = video.videoHeight * scale;
  const dx = (SIZE - width) / 2;
  const dy = (SIZE - height) / 2;

  context.fillStyle = "#727272"; // letterbox padding
  context.fillRect(0, 0, SIZE, SIZE);
  context.drawImage(video, dx, dy, width, height);

  const { data } = context.getImageData(0, 0, SIZE, SIZE);
  const tensor = new Float32Array(3 * SIZE * SIZE);
  let luminance = 0;
  for (let i = 0; i < SIZE * SIZE; i++) {
    tensor[i] = data[i * 4] / 255;                     // R
    tensor[SIZE * SIZE + i] = data[i * 4 + 1] / 255;   // G
    tensor[2 * SIZE * SIZE + i] = data[i * 4 + 2] / 255; // B
    luminance += data[i * 4] + data[i * 4 + 1] + data[i * 4 + 2];
  }
  // Mean brightness of the VIDEO region only (exclude the gray letterbox padding).
  const videoShare = (width * height) / (SIZE * SIZE);
  const paddingShare = 1 - videoShare;
  const meanBrightness =
    luminance / (SIZE * SIZE * 3 * 255) - 0.447 * paddingShare; // 0.447 = padding gray
  return { tensor, scale, dx, dy, meanBrightness: meanBrightness / Math.max(videoShare, 0.01) };
}

function iou(a, b) {
  const x1 = Math.max(a.x1, b.x1), y1 = Math.max(a.y1, b.y1);
  const x2 = Math.min(a.x2, b.x2), y2 = Math.min(a.y2, b.y2);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  const areaA = (a.x2 - a.x1) * (a.y2 - a.y1);
  const areaB = (b.x2 - b.x1) * (b.y2 - b.y1);
  return inter / (areaA + areaB - inter);
}

function decode(output, scale, dx, dy) {
  // YOLOv8 ONNX output: [1, 84, 8400] planar (4 box coords + 80 class scores).
  const data = output.data;
  const anchors = output.dims[2];
  const candidates = [];

  for (let i = 0; i < anchors; i++) {
    let best = 0, bestClass = -1;
    for (let c = 0; c < 80; c++) {
      const score = data[(4 + c) * anchors + i];
      if (score > best) { best = score; bestClass = c; }
    }
    if (best < SCORE_THRESHOLD) continue;

    const cx = data[i], cy = data[anchors + i];
    const w = data[2 * anchors + i], h = data[3 * anchors + i];
    candidates.push({
      classId: bestClass,
      score: best,
      x1: (cx - w / 2 - dx) / scale,
      y1: (cy - h / 2 - dy) / scale,
      x2: (cx + w / 2 - dx) / scale,
      y2: (cy + h / 2 - dy) / scale,
    });
  }

  // Greedy per-class NMS.
  candidates.sort((a, b) => b.score - a.score);
  const kept = [];
  for (const box of candidates) {
    if (!kept.some((k) => k.classId === box.classId && iou(k, box) > IOU_THRESHOLD)) {
      kept.push(box);
    }
  }
  return kept;
}

function drawBoxes(boxes) {
  overlay.width = video.videoWidth;
  overlay.height = video.videoHeight;
  const context = overlay.getContext("2d");
  context.clearRect(0, 0, overlay.width, overlay.height);
  context.font = "13px sans-serif";
  for (const box of boxes) {
    const mapped = CLASS_MAP[box.classId];
    context.strokeStyle = mapped ? "#2e844a" : "#706e6b";
    context.lineWidth = 2;
    context.strokeRect(box.x1, box.y1, box.x2 - box.x1, box.y2 - box.y1);
    const label = `${COCO_NAMES[box.classId] || "obj " + box.classId} ${(box.score * 100) | 0}%`;
    context.fillStyle = mapped ? "#2e844a" : "#706e6b";
    context.fillRect(box.x1, box.y1 - 16, context.measureText(label).width + 8, 16);
    context.fillStyle = "#fff";
    context.fillText(label, box.x1 + 4, box.y1 - 4);
  }
}

function countByCategory(boxes) {
  const counts = Object.fromEntries(CATEGORIES.map((c) => [c, 0]));
  let scoreSum = 0, mapped = 0;
  for (const box of boxes) {
    const category = CLASS_MAP[box.classId];
    if (category) { counts[category] += 1; scoreSum += box.score; mapped += 1; }
  }
  return { counts, confidence: mapped ? scoreSum / mapped : 1.0 };
}

function renderCounts(counts) {
  document.getElementById("countRows").innerHTML = CATEGORIES.map(
    (category) => `<tr><td>${category}</td><td class="num">${counts[category]}</td>
      <td class="num">${lastPostedAt[category] || "-"}</td></tr>`
  ).join("");
}

function countsEqual(a, b) {
  return a && b && CATEGORIES.every((c) => a[c] === b[c]);
}

async function maybePost(counts, confidence) {
  recentCounts.push(counts);
  if (recentCounts.length > STABLE_FRAMES) recentCounts.shift();
  const stable =
    recentCounts.length === STABLE_FRAMES &&
    recentCounts.every((c) => countsEqual(c, recentCounts[0]));

  if (!stable || countsEqual(counts, lastPosted)) return;

  const siteId = parseInt(document.getElementById("siteSelect").value, 10);
  for (const category of CATEGORIES) {
    await fetch("/snapshots", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        site_id: siteId,
        category,
        count: counts[category],
        confidence: Number(confidence.toFixed(2)),
        source: "vision",
      }),
    });
    lastPostedAt[category] = new Date().toLocaleTimeString();
  }
  const changes = lastPosted
    ? CATEGORIES.filter((c) => counts[c] !== lastPosted[c])
        .map((c) => `${c} ${lastPosted[c]} -> ${counts[c]}`)
        .join(", ")
    : "initial counts";
  lastPosted = { ...counts };
  log(`shelf change posted to ledger: ${changes}`);
}

const MIN_BRIGHTNESS = 0.02; // below this the feed is black/covered, not an empty shelf
let warnedNoSignal = false;

async function detectLoop() {
  if (!running) return;
  try {
    const { tensor, scale, dx, dy, meanBrightness } = preprocess();
    if (meanBrightness < MIN_BRIGHTNESS) {
      // A blocked or covered camera must never be reported as an empty shelf.
      recentCounts = [];
      setStatus("no video signal - not posting", false);
      if (!warnedNoSignal) {
        warnedNoSignal = true;
        log("video feed is black (camera blocked or covered), holding all posts");
      }
    } else {
      warnedNoSignal = false;
      setStatus("live - detecting on-device", true);
      const input = new ort.Tensor("float32", tensor, [1, 3, SIZE, SIZE]);
      const results = await session.run({ images: input });
      const boxes = decode(results[session.outputNames[0]], scale, dx, dy);
      drawBoxes(boxes);
      const { counts, confidence } = countByCategory(boxes);
      renderCounts(counts);
      await maybePost(counts, confidence);
    }
  } catch (error) {
    log(`detect error: ${error.message || error}`);
  }
  setTimeout(detectLoop, FRAME_INTERVAL_MS);
}

document.getElementById("startBtn").addEventListener("click", async () => {
  if (running) {
    running = false;
    setStatus("stopped", false);
    document.getElementById("startBtn").textContent = "Start camera";
    return;
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: "environment", width: { ideal: 1280 } },
    audio: false,
  });
  video.srcObject = stream;
  await video.play();
  running = true;
  setStatus("live - detecting on-device", true);
  document.getElementById("startBtn").textContent = "Stop";
  log("camera started, YOLO running locally in this tab");
  detectLoop();
});

(async () => {
  try {
    await Promise.all([loadSites(), loadModel()]);
    setStatus("ready", false);
    renderCounts(Object.fromEntries(CATEGORIES.map((c) => [c, 0])));
  } catch (error) {
    setStatus("setup failed", false);
    log(`setup error: ${error.message || error}`);
  }
})();
