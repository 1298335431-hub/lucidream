"""Run local RapidOCR on vertical traditional-Chinese scan sample pages.

The output is raw evidence for manual correction, not production knowledge-base text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from PIL import Image
from rapidocr_onnxruntime import RapidOCR


def page_number(path: Path) -> int:
    match = re.search(r"(\d+)$", path.stem)
    if not match:
        raise ValueError(f"Cannot infer page from {path.name}")
    return int(match.group(1))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    pages = sorted(
        (path for path in args.input_dir.iterdir() if path.suffix.lower() == ".png"),
        key=page_number,
    )
    if not pages:
        raise SystemExit("No PNG pages found")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    engine = RapidOCR()
    with args.output.open("w", encoding="utf-8") as output:
        for page_path in pages:
            # Rotate counter-clockwise so columns become horizontal OCR lines.
            with Image.open(page_path) as source:
                rotated = source.transpose(Image.Transpose.ROTATE_90)
                results, timings = engine(rotated)

            observations = [
                {
                    "text": str(text),
                    "confidence": round(float(confidence), 6),
                    "box": [[round(float(value), 3) for value in point] for point in box],
                }
                for box, text, confidence in (results or [])
            ]
            raw_text = "\n".join(item["text"] for item in observations)
            record = {
                "pdf_page": page_number(page_path),
                "rendered_image": page_path.name,
                "rendered_image_sha256": sha256(page_path),
                "engine": "rapidocr-onnxruntime 1.4.4",
                "rotation": "counterclockwise_90",
                "reading_order": "provider_detection_order_unverified",
                "raw_text": raw_text,
                "observations": observations,
                "metrics": {
                    "observation_count": len(observations),
                    "character_count": len(raw_text),
                    "mean_confidence": round(
                        sum(item["confidence"] for item in observations) / len(observations), 6
                    ) if observations else 0,
                    "engine_seconds": round(sum(float(value) for value in timings), 6),
                },
            }
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()


if __name__ == "__main__":
    main()
