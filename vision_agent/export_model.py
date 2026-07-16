"""Regenerate models/yolov8n.onnx for the browser detector.

The exported model is already committed, so you only need this if you want a
different size/model. Needs:  pip install ultralytics onnx

    python -m vision_agent.export_model
"""

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models"


def main() -> None:
    try:
        from ultralytics import YOLO
    except ImportError:
        sys.exit("Needs: pip install ultralytics onnx")

    model = YOLO(str(MODELS_DIR / "yolov8n.pt"))  # downloads weights if missing
    exported = model.export(format="onnx", imgsz=640, opset=12)
    target = MODELS_DIR / "yolov8n.onnx"
    if Path(exported).resolve() != target.resolve():
        shutil.move(exported, target)
    print(f"Exported {target} ({target.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
