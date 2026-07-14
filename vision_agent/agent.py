"""ReliefLink vision agent: shelf photo -> Claude counts -> ledger.

Owner: Nehal. Your task checklist is in vision_agent/README.md.

Quick start (no camera, no API key):
    python -m vision_agent.agent --site-id 1 --fake

Count one photo with Claude (needs ANTHROPIC_API_KEY in .env):
    python -m vision_agent.agent --site-id 1 --image path/to/shelf.jpg

Watch a webcam, counting every 45 seconds:
    python -m vision_agent.agent --site-id 1 --camera 0 --loop 45
"""

import argparse
import base64
import json
import random
import sys
import time
from pathlib import Path

import requests

from shared.config import CATEGORIES, CLAUDE_MODEL, LEDGER_URL

COUNTING_PROMPT = f"""You are an inventory counter for a food bank.
Look at this photo of shelves/pallets and count the visible items in each category:

- canned_goods: cans and jars of food
- produce: fresh fruit and vegetables (count crates/boxes as 20 items each)
- dairy: milk cartons, cheese, yogurt, eggs
- dry_goods: bags/boxes of rice, pasta, cereal, flour, beans

Count only what you can actually see. If a category is not visible, count it as 0.
Set confidence between 0 and 1 based on how clearly you could see and count the items.
Note anything unusual (blocked view, blur, partial shelf) in notes.

Categories, exactly these keys: {", ".join(CATEGORIES)}"""

# Claude is forced to reply with JSON matching this schema, so no parsing surprises.
COUNT_SCHEMA = {
    "type": "object",
    "properties": {
        "counts": {
            "type": "object",
            "properties": {category: {"type": "integer"} for category in CATEGORIES},
            "required": list(CATEGORIES),
            "additionalProperties": False,
        },
        "confidence": {"type": "number"},
        "notes": {"type": "string"},
    },
    "required": ["counts", "confidence", "notes"],
    "additionalProperties": False,
}

MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def count_with_claude(image_path: str) -> dict:
    """Send one shelf photo to Claude and get category counts back."""
    import anthropic  # imported here so --fake works without the package configured

    path = Path(image_path)
    media_type = MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        sys.exit(f"Unsupported image type {path.suffix}, use jpg/png/webp")

    image_data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        output_config={"format": {"type": "json_schema", "schema": COUNT_SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": COUNTING_PROMPT},
                ],
            }
        ],
    )
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)


def fake_result() -> dict:
    """Plausible counts so teammates can demo without a camera or API key."""
    return {
        "counts": {category: random.randint(10, 300) for category in CATEGORIES},
        "confidence": round(random.uniform(0.75, 0.98), 2),
        "notes": "fake mode",
    }


def capture_frame(camera_index: int) -> str:
    """Grab one frame from a webcam and save it to captures/. Needs opencv-python."""
    try:
        import cv2
    except ImportError:
        sys.exit("Camera mode needs OpenCV: pip install opencv-python")

    camera = cv2.VideoCapture(camera_index)
    ok, frame = camera.read()
    camera.release()
    if not ok:
        sys.exit(f"Could not read from camera {camera_index}")

    Path("captures").mkdir(exist_ok=True)
    out_path = f"captures/frame_{int(time.time())}.jpg"
    cv2.imwrite(out_path, frame)
    return out_path


def post_counts(site_id: int, result: dict, source: str) -> None:
    """Post one snapshot per category to the ledger."""
    for category, count in result["counts"].items():
        response = requests.post(
            f"{LEDGER_URL}/snapshots",
            json={
                "site_id": site_id,
                "category": category,
                "count": count,
                "confidence": result["confidence"],
                "source": source,
            },
            timeout=10,
        )
        response.raise_for_status()
    print(
        f"site {site_id}: posted {result['counts']} "
        f"(confidence {result['confidence']}, source {source})"
    )


def run_once(args: argparse.Namespace) -> None:
    if args.fake:
        post_counts(args.site_id, fake_result(), source="fake")
    elif args.image:
        post_counts(args.site_id, count_with_claude(args.image), source="vision")
    elif args.camera is not None:
        frame_path = capture_frame(args.camera)
        post_counts(args.site_id, count_with_claude(frame_path), source="vision")
    else:
        sys.exit("Pick a mode: --fake, --image PATH, or --camera INDEX")


def main() -> None:
    parser = argparse.ArgumentParser(description="ReliefLink vision agent")
    parser.add_argument("--site-id", type=int, required=True, help="which site this camera watches")
    parser.add_argument("--image", help="count a single photo instead of using a camera")
    parser.add_argument("--camera", type=int, help="webcam index to capture from (usually 0)")
    parser.add_argument("--fake", action="store_true", help="post random counts, no Claude needed")
    parser.add_argument("--loop", type=int, help="repeat every N seconds (motion trigger: TODO)")
    args = parser.parse_args()

    if args.loop:
        print(f"Counting every {args.loop}s, Ctrl-C to stop")
        while True:
            run_once(args)
            time.sleep(args.loop)
    else:
        run_once(args)


if __name__ == "__main__":
    main()
