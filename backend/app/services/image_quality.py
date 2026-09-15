"""Local quality gate for provider-generated dream artwork."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from threading import Lock
from urllib.parse import urlparse

import httpx
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from app.services.aliyun import ModelServiceError


@dataclass(frozen=True)
class ImageQualityResult:
    accepted: bool
    detected_text_count: int = 0
    contains_band: bool = False
    contains_panels: bool = False


def has_panel_seam(image: Image.Image) -> bool:
    """Flag probable split panels, not a semantic guarantee of a storyboard.

    Look for an unusually abrupt, straight interior seam across most of the
    image, with textured imagery on both sides. Smooth fog/gradients, flat
    letterboxing and small object edges are handled elsewhere or ignored.
    This is advisory: candidates stay available even when flagged.
    """
    sample = image.convert("RGB")
    sample.thumbnail((768, 768))
    pixels = np.asarray(sample, dtype=np.float32)
    for axis in (pixels, pixels.transpose(1, 0, 2)):
        if min(axis.shape[:2]) < 64:
            continue
        jumps = np.abs(np.diff(axis, axis=0)).mean(axis=2)
        scores = np.quantile(jumps, 0.25, axis=1)
        start, end = int(len(scores) * 0.18), int(len(scores) * 0.82)
        for i in np.flatnonzero(scores[start:end] > 15) + start:
            neighborhood = np.r_[scores[max(0, i - 20):i - 3], scores[i + 4:i + 21]]
            if not len(neighborhood) or scores[i] < max(1, float(np.median(neighborhood))) * 5:
                continue
            if float((jumps[i] > 12).mean()) < 0.75:
                continue
            before, after = axis[i - 12:i - 2], axis[i + 3:i + 13]
            if all(float(region.std(axis=(0, 1)).max()) > 6 for region in (before, after)):
                return True
    return False


def has_flat_band(image: Image.Image) -> bool:
    """Detect broad flat panels separated by a straight, full-span hard edge.

    Require both flatness and a strong boundary: smooth sky/fog alone is valid.
    Check both axes so side panels and top/bottom letterboxing are covered.
    """
    pixels = np.asarray(image.convert("RGB"), dtype=np.float32)
    if float(pixels.std(axis=(0, 1)).max()) < 2:
        return True
    for axis_pixels in (pixels, pixels.transpose(1, 0, 2)):
        width = axis_pixels.shape[1]
        if width < 32:
            continue
        # Flat along the entire column, independent of color or brightness.
        flat = axis_pixels.std(axis=0).max(axis=1) < 4
        edges = np.diff(np.r_[False, flat, False].astype(int))
        starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
        for start, end in zip(starts, ends):
            # Provider letterboxing can be quite narrow.  A recent 960x1280
            # result contained a 70px bottom strip (5.5% of the image), which
            # slipped under the old 6% threshold and remained visible after
            # the card's small cover crop.  Two percent still ignores ordinary
            # one-pixel borders while catching bands that are visible in the
            # final 3:4 export.
            if end - start < max(8, int(width * 0.02)):
                continue
            for boundary in (start, end):
                margin = max(2, int(width * 0.01))
                if boundary < margin or boundary + margin > width:
                    continue
                left = axis_pixels[:, boundary - margin:boundary].mean(axis=1)
                right = axis_pixels[:, boundary:boundary + margin].mean(axis=1)
                jump = np.abs(left - right).mean(axis=1)
                if float(np.quantile(jump, 0.2)) > 15:
                    return True
    return False


class AllowAllImageReviewer:
    """Test double used when a model adapter is injected into the app."""

    def review_url(self, _image_url: str) -> ImageQualityResult:
        return ImageQualityResult(accepted=True)


class LocalImageQualityReviewer:
    """Reject generated artwork containing confident OCR text."""

    def __init__(self, timeout_seconds: float = 20) -> None:
        self.timeout_seconds = timeout_seconds
        self._engine: RapidOCR | None = None
        self._lock = Lock()

    def _get_engine(self) -> RapidOCR:
        with self._lock:
            if self._engine is None:
                self._engine = RapidOCR()
            return self._engine

    def review_url(self, image_url: str) -> ImageQualityResult:
        parsed = urlparse(image_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ModelServiceError("image_review_invalid_url")
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
                response = client.get(image_url)
        except httpx.HTTPError:
            raise ModelServiceError("image_review_unavailable") from None
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if (
            response.status_code != 200
            or not content_type.startswith("image/")
            or len(response.content) > 12 * 1024 * 1024
        ):
            raise ModelServiceError("image_review_unavailable")
        return self.review_bytes(response.content)

    def review_bytes(self, content: bytes) -> ImageQualityResult:
        try:
            with Image.open(io.BytesIO(content)) as source:
                image = source.convert("RGB")
            results, _ = self._get_engine()(image)
        except Exception:
            raise ModelServiceError("image_review_failed") from None

        detected = 0
        for _box, text, confidence in results or []:
            compact = re.sub(r"[^0-9A-Za-z\u3400-\u9fff]", "", str(text))
            if float(confidence) >= 0.75 and len(compact) >= 3:
                detected += 1
        contains_band = has_flat_band(image)
        contains_panels = has_panel_seam(image)
        return ImageQualityResult(
            accepted=detected == 0 and not contains_band and not contains_panels,
            detected_text_count=detected,
            contains_band=contains_band,
            contains_panels=contains_panels,
        )
