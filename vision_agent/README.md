# Vision Agent (camera -> counts)

**Owner: Nehal**

A camera (or phone photo) pointed at shelves, a Claude vision call that counts items per
category, and a POST to the ledger. No model training, no YOLO, just a well-crafted
counting prompt with a forced JSON schema so the output is always parseable.

## Run it

```bash
# from the repo root, with the ledger running (uvicorn ledger.main:app --reload)

# 1. Fake mode: works instantly, no camera, no API key. Use this to test the pipeline.
python -m vision_agent.agent --site-id 1 --fake

# 2. Real mode: put ANTHROPIC_API_KEY in .env, then point it at any shelf photo.
python -m vision_agent.agent --site-id 1 --image my_shelf.jpg

# 3. Webcam mode (pip install opencv-python first):
python -m vision_agent.agent --site-id 1 --camera 0 --loop 45
```

After any of these, `curl http://localhost:8000/inventory` (or the dashboard) shows
your counts.

## Files you own

- `agent.py` - everything: the prompt, the Claude call, the capture loop, the posting.

## Your tasks

- [ ] Get `--fake` working end to end (ledger running, counts appear on the dashboard).
- [ ] Get an `ANTHROPIC_API_KEY` (ask Pranav) into your `.env`, take a photo of any
      pantry/shelf with your phone, and run `--image`. Sanity-check the counts.
- [ ] Tune `COUNTING_PROMPT`: try 5 different shelf photos, note where counts are off,
      and iterate on the prompt wording until category-level counts look reasonable.
- [ ] Test `--camera --loop` with your laptop webcam pointed at a shelf.
- [ ] **Motion trigger** (the interesting part): in loop mode, only call Claude when the
      frame actually changed. Simplest approach: compare consecutive frames with OpenCV
      (`cv2.absdiff` + mean threshold) and skip the API call when nothing moved. This
      saves API cost and makes the demo story better.
- [ ] Stretch: crop/downscale frames before sending (smaller + faster + cheaper), and
      log `notes` from Claude somewhere visible.

## Definition of done

A laptop webcam pointed at a shelf posts believable category counts to the ledger every
45-60 seconds, skipping Claude calls when nothing moved, and the dashboard reflects a
change within a minute of you adding/removing items from the shelf.

## Tips

- The JSON schema (`COUNT_SCHEMA`) guarantees Claude's reply parses. If counts are
  *wrong*, fix the prompt, not the parsing.
- Demo insurance: `--fake` always works. If wifi or the API dies during the demo,
  fall back to it.
- Ask Claude/Cursor: "read vision_agent/agent.py and add a motion-detection gate to
  the loop using cv2.absdiff".
