"""Replacement ReliefLink vision agent entrypoint.

This small adapter is intentionally separate from the legacy ``agent.py`` so a
camera owner can run a fresh, documented agent even if the old script is removed.
It captures one still image, delegates food counting to the existing safe helpers,
and posts only category counts to the ledger. It never commits inventory on its own.

Examples (run from the repository root)::

    python -m vision_agent.vision_agent --site-id 1 --fake
    python -m vision_agent.vision_agent --site-id 1 --image shelf.jpg
    python -m vision_agent.vision_agent --site-id 1 --camera 0
"""

from __future__ import annotations

import argparse
import sys

from .agent import capture_frame, count_with_claude, fake_result, post_counts


class VisionAgent:
    """Run one reviewable inventory observation for a food-bank site."""

    def __init__(self, site_id: int) -> None:
        self.site_id = site_id

    def run_fake(self) -> dict:
        """Post a deterministic-schema fake result for key-free demos."""
        result = fake_result()
        post_counts(self.site_id, result, source="fake")
        return result

    def run_image(self, image_path: str) -> dict:
        """Count one still image with the configured vision model."""
        result = count_with_claude(image_path)
        post_counts(self.site_id, result, source="vision")
        return result

    def run_camera(self, camera_index: int) -> dict:
        """Capture one camera frame, then process it as a still image."""
        return self.run_image(capture_frame(camera_index))


def main() -> None:
    parser = argparse.ArgumentParser(description="ReliefLink replacement vision agent")
    parser.add_argument("--site-id", type=int, required=True, help="food-bank site watched by this agent")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--fake", action="store_true", help="run without a camera or API key")
    modes.add_argument("--image", help="count one JPEG, PNG, or WebP shelf photo")
    modes.add_argument("--camera", type=int, metavar="INDEX", help="capture one frame from webcam INDEX")
    args = parser.parse_args()

    agent = VisionAgent(args.site_id)
    if args.fake:
        agent.run_fake()
    elif args.image:
        agent.run_image(args.image)
    elif args.camera is not None:
        agent.run_camera(args.camera)
    else:  # pragma: no cover - argparse's required group handles this
        sys.exit("Choose --fake, --image PATH, or --camera INDEX")


if __name__ == "__main__":
    main()
