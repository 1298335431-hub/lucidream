import io

from PIL import Image
import numpy as np
import pytest

from app.services.image_quality import LocalImageQualityReviewer, has_flat_band, has_panel_seam


@pytest.mark.parametrize("grid", [False, True])
@pytest.mark.parametrize("rotation", [0, 90])
def test_detects_textured_split_panels_without_blank_bands(grid, rotation):
    noise = np.random.default_rng(14).integers(0, 35, (320, 240, 3), dtype=np.uint8)
    noise[:160] += 25
    noise[160:] += 155
    if grid:
        noise[:, 120:] = 255 - noise[:, 120:]
    image = Image.fromarray(noise).rotate(rotation, expand=True)
    assert has_panel_seam(image)
    reviewer = LocalImageQualityReviewer()
    reviewer._engine = FakeOCREngine([])
    content = io.BytesIO()
    image.save(content, format='PNG')
    result = reviewer.review_bytes(content.getvalue())
    assert result.contains_panels and not result.accepted
    assert result.detected_text_count == 0


def test_panel_check_does_not_flag_gradients_noise_or_small_objects():
    assert not has_panel_seam(scene())
    gradient = np.linspace(30, 210, 320, dtype=np.uint8)
    image = Image.fromarray(np.broadcast_to(gradient[:, None, None], (320, 240, 3)).copy())
    assert not has_panel_seam(image)
    image.paste('white', (80, 110, 140, 170))
    assert not has_panel_seam(image)
    # A sharp but flat sky/ground boundary is not itself two textured scenes.
    image = Image.new('RGB', (240, 320), 'navy')
    image.paste('gray', (0, 160, 240, 320))
    assert not has_panel_seam(image)


class FakeOCREngine:
    def __init__(self, results):
        self.results = results

    def __call__(self, _image):
        return self.results, [0.01]


def png_bytes() -> bytes:
    output = io.BytesIO()
    scene().save(output, format="PNG")
    return output.getvalue()


def test_reviewer_rejects_confident_generated_text():
    reviewer = LocalImageQualityReviewer()
    reviewer._engine = FakeOCREngine([
        ([[0, 0], [20, 0], [20, 10], [0, 10]], "203.2020", 0.99),
    ])
    result = reviewer.review_bytes(png_bytes())
    assert result.accepted is False
    assert result.detected_text_count == 1


def test_reviewer_ignores_short_low_confidence_shape_guess():
    reviewer = LocalImageQualityReviewer()
    reviewer._engine = FakeOCREngine([
        ([[0, 0], [5, 0], [5, 5], [0, 5]], "AI", 0.99),
        ([[0, 0], [20, 0], [20, 10], [0, 10]], "梦中的主要", 0.42),
    ])
    result = reviewer.review_bytes(png_bytes())
    assert result.accepted is True
    assert result.detected_text_count == 0


def scene():
    rng = np.random.default_rng(42)
    return Image.fromarray(rng.integers(40, 180, (320, 240, 3), dtype=np.uint8))


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("color", [(254, 254, 254), (80, 80, 80), (10, 30, 90)])
def test_rejects_flat_edge_panels(rotation, color):
    image = scene()
    image.paste(color, (175, 0, 240, 320))
    assert has_flat_band(image.rotate(rotation, expand=True))


def test_accepts_smooth_fog_and_textured_scene():
    assert not has_flat_band(scene())
    gradient = np.linspace(40, 230, 240, dtype=np.uint8)
    image = Image.fromarray(np.broadcast_to(gradient[None, :, None], (320, 240, 3)).copy())
    assert not has_flat_band(image)


def test_rejects_narrow_bottom_letterbox_seen_in_provider_output():
    image = Image.fromarray(
        np.random.default_rng(7).integers(35, 190, (1280, 960, 3), dtype=np.uint8)
    )
    # 70 / 1280 = 5.47%; this reproduces the strip that the old 6% gate missed.
    image.paste((254, 254, 254), (0, 1210, 960, 1280))
    assert has_flat_band(image)


def test_reviewer_rejects_band_without_ocr_text():
    image = scene()
    image.paste("white", (175, 0, 240, 320))
    output = io.BytesIO()
    image.save(output, format="PNG")
    reviewer = LocalImageQualityReviewer()
    reviewer._engine = FakeOCREngine([])
    result = reviewer.review_bytes(output.getvalue())
    assert not result.accepted
    assert result.contains_band
    assert result.detected_text_count == 0
