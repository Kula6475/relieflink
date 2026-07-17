# Vision (edge YOLO -> ledger)

**Owner: Nehal** | Status: **edge pipeline live**

## Replacement agent

`vision_agent/vision_agent.py` is the standalone replacement entrypoint for a
camera owner. It is deliberately a still-image workflow: capture one frame, count
visible packages, post category observations, and leave approval to a human reviewer.

```bash
python -m vision_agent.vision_agent --site-id 1 --fake
python -m vision_agent.vision_agent --site-id 1 --image shelf.jpg
python -m vision_agent.vision_agent --site-id 1 --camera 0
```

The fake path is key-free. The image and camera paths use the configured Claude
vision model and the same ledger contract as the original agent.

Shelf counting happens **on the edge**: a YOLOv8n model runs locally on whatever device
is pointing at the shelf. No frames leave the device, only category counts are posted to
the ledger, and only when a stable count actually changes (someone took a can off the
shelf).

## Two ways to run it

### 1. Browser (any device with a camera, nothing to install)

Open **http://localhost:8000/camera**, pick a site, hit Start. YOLOv8n runs in the tab
via onnxruntime-web using the committed `models/yolov8n.onnx`. Works on laptops and
phones (phones need a secure context: localhost, an https tunnel, or `--ssl-keyfile`).

### 2. Python (headless devices: Raspberry Pi, Jetson, kiosk box)

```bash
pip install ultralytics       # optional dep, not in requirements.txt
python -m vision_agent.edge --site-id 1 --camera 0
```

Same logic: detect every ~1.2s, post to the ledger only when stable counts change.

## Fallbacks

- `python -m vision_agent.agent --site-id 1 --fake` posts random counts (demo insurance).
- `python -m vision_agent.agent --site-id 1 --image shelf.jpg` counts one photo with
  Claude vision (needs `ANTHROPIC_API_KEY`), useful to sanity-check YOLO's counts.

## How the auto-update works

1. A frame is detected every ~1.2 seconds.
2. Detections map from COCO classes to our categories (demo stand-ins):
   bottle/cup -> canned_goods, banana/apple/orange/broccoli/carrot -> produce,
   bowl/wine glass -> dairy, book -> dry_goods.
3. Counts must be identical for 2 consecutive frames (kills flicker), and only a change
   vs the last posted state triggers a POST. Take a can off the shelf: one clean ledger
   update a couple of seconds later, visible on the dashboard within 5s.

## Remaining ideas

- [ ] Fine-tune YOLOv8n on real shelf photos (cans, cartons, boxes) and re-export with
      `python -m vision_agent.export_model`, this replaces the COCO stand-in mapping.
- [ ] Per-shelf zones: only count detections inside a user-drawn region.
- [ ] WebGPU execution provider in `camera.js` for faster in-browser inference.
