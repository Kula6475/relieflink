"""Edge YOLO detector, Python flavor: for laptops, Raspberry Pi, Jetson, kiosk boxes.

Prefer the zero-install browser version at http://localhost:8000/camera (works on
phones too). This module is the same detector for devices where a browser is not
convenient. Everything runs locally; only category counts leave the device.

Needs the optional dependency:  pip install ultralytics

    python -m vision_agent.edge --site-id 1 --camera 0
"""

import argparse
import sys
import time

import requests

from shared.config import CATEGORIES, LEDGER_URL

# COCO class name -> ReliefLink category (demo stand-ins; fine-tune on shelf data later).
CLASS_MAP = {
    "bottle": "canned_goods",
    "cup": "canned_goods",
    "banana": "produce",
    "apple": "produce",
    "orange": "produce",
    "broccoli": "produce",
    "carrot": "produce",
    "bowl": "dairy",
    "wine glass": "dairy",
    "book": "dry_goods",
}

STABLE_FRAMES = 2
SCORE_THRESHOLD = 0.4


def count_frame(model, frame) -> tuple[dict, float]:
    """Run YOLO on one frame, return (counts per category, mean confidence)."""
    result = model.predict(frame, conf=SCORE_THRESHOLD, verbose=False)[0]
    counts = dict.fromkeys(CATEGORIES, 0)
    scores, mapped = 0.0, 0
    for box in result.boxes:
        name = result.names[int(box.cls)]
        category = CLASS_MAP.get(name)
        if category:
            counts[category] += 1
            scores += float(box.conf)
            mapped += 1
    return counts, (scores / mapped if mapped else 1.0)


def post_counts(site_id: int, counts: dict, confidence: float) -> None:
    for category, count in counts.items():
        requests.post(
            f"{LEDGER_URL}/snapshots",
            json={
                "site_id": site_id,
                "category": category,
                "count": count,
                "confidence": round(confidence, 2),
                "source": "vision",
            },
            timeout=10,
        ).raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(description="ReliefLink Python edge detector")
    parser.add_argument("--site-id", type=int, required=True)
    parser.add_argument("--camera", type=int, default=0, help="webcam index (usually 0)")
    parser.add_argument("--interval", type=float, default=1.2, help="seconds between frames")
    args = parser.parse_args()

    try:
        import cv2
        from ultralytics import YOLO
    except ImportError:
        sys.exit("Edge mode needs the optional dependency: pip install ultralytics")

    model = YOLO("yolov8n.pt")  # auto-downloads 6MB weights on first run
    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        sys.exit(f"Could not open camera {args.camera}")

    print(f"Edge YOLO watching camera {args.camera} for site {args.site_id}, Ctrl-C to stop")
    recent: list[dict] = []
    last_posted: dict | None = None

    while True:
        ok, frame = camera.read()
        if not ok:
            sys.exit("Camera stream ended")

        counts, confidence = count_frame(model, frame)
        recent.append(counts)
        if len(recent) > STABLE_FRAMES:
            recent.pop(0)

        stable = len(recent) == STABLE_FRAMES and all(c == recent[0] for c in recent)
        if stable and counts != last_posted:
            post_counts(args.site_id, counts, confidence)
            last_posted = dict(counts)
            print(f"shelf change posted: {counts} (confidence {confidence:.2f})")

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
