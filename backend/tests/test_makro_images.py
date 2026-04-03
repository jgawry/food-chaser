"""
Tests for Makro PDF image extraction helpers.
No real PDF is needed — page/doc objects are mocked.
"""
import os
import pytest
from unittest.mock import MagicMock, patch, call
import fitz

from app.scraper.makro_leaflet import (
    _extract_image_blocks,
    _find_product_image,
    _save_image,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _rect(x0, y0, x1, y1):
    return fitz.Rect(x0, y0, x1, y1)


def _mock_page(images):
    """Build a mock page whose get_images() returns the given list.

    Each entry in images is (xref, width, height, rects) where rects is a
    list of fitz.Rect objects returned by get_image_rects(xref).
    """
    page = MagicMock()
    page.get_images.return_value = [
        (xref, 0, width, height, 8, "DeviceRGB", "", f"img{xref}", "DCTDecode", 0)
        for xref, width, height, _ in images
    ]

    def _get_image_rects(xref):
        for ix, _w, _h, rects in images:
            if ix == xref:
                return rects
        return []

    page.get_image_rects.side_effect = _get_image_rects
    return page


# ── _extract_image_blocks ─────────────────────────────────────────────────────

def test_extract_image_blocks_returns_rect_and_xref():
    page = _mock_page([(1, 120, 120, [_rect(10, 10, 130, 130)])])
    blocks = _extract_image_blocks(page)
    assert len(blocks) == 1
    assert blocks[0][1] == 1  # xref
    assert isinstance(blocks[0][0], fitz.Rect)


def test_extract_image_blocks_filters_small_images():
    page = _mock_page([
        (1, 40, 40, [_rect(0, 0, 40, 40)]),   # too small
        (2, 100, 100, [_rect(0, 0, 100, 100)]),  # ok
    ])
    blocks = _extract_image_blocks(page)
    assert len(blocks) == 1
    assert blocks[0][1] == 2


def test_extract_image_blocks_expands_multiple_rects_per_image():
    page = _mock_page([(1, 100, 100, [_rect(0, 0, 100, 100), _rect(200, 0, 300, 100)])])
    blocks = _extract_image_blocks(page)
    assert len(blocks) == 2


def test_extract_image_blocks_skips_on_rect_error():
    page = MagicMock()
    page.get_images.return_value = [(1, 0, 100, 100, 8, "", "", "img1", "", 0)]
    page.get_image_rects.side_effect = Exception("xref not found")
    blocks = _extract_image_blocks(page)
    assert blocks == []


# ── _find_product_image ───────────────────────────────────────────────────────

def test_find_product_image_returns_image_above_price():
    price_rect = _rect(50, 200, 150, 215)
    image_blocks = [(_rect(50, 50, 150, 180), 42)]
    assert _find_product_image(price_rect, image_blocks) == 42


def test_find_product_image_ignores_images_below_price():
    price_rect = _rect(50, 100, 150, 115)
    image_blocks = [(_rect(50, 120, 150, 250), 42)]   # below
    assert _find_product_image(price_rect, image_blocks) is None


def test_find_product_image_picks_horizontally_closest():
    price_rect = _rect(100, 300, 200, 315)
    # Two images above: one directly above (cx=150), one far left (cx=20)
    image_blocks = [
        (_rect(110, 50, 190, 180), 1),   # cx=150, close
        (_rect(0, 50, 40, 180), 2),      # cx=20, far
    ]
    assert _find_product_image(price_rect, image_blocks) == 1


def test_find_product_image_returns_none_when_no_images():
    assert _find_product_image(_rect(50, 200, 150, 215), []) is None


# ── _save_image ───────────────────────────────────────────────────────────────

def test_save_image_writes_file_and_returns_url(tmp_path):
    doc = MagicMock()
    doc.extract_image.return_value = {"ext": "jpeg", "image": b"\xff\xd8\xff\xe0"}

    url = _save_image(doc, xref=5, images_dir=str(tmp_path), product_id="leaflet-makro-raffaello-pak-po")

    assert url == "/api/images/leaflet-makro-raffaello-pak-po.jpeg"
    saved_file = tmp_path / "leaflet-makro-raffaello-pak-po.jpeg"
    assert saved_file.exists()
    assert saved_file.read_bytes() == b"\xff\xd8\xff\xe0"


def test_save_image_creates_images_dir(tmp_path):
    images_dir = str(tmp_path / "new_subdir")
    doc = MagicMock()
    doc.extract_image.return_value = {"ext": "png", "image": b"\x89PNG"}

    _save_image(doc, xref=1, images_dir=images_dir, product_id="prod1")
    assert os.path.isdir(images_dir)


def test_save_image_defaults_ext_to_png(tmp_path):
    doc = MagicMock()
    doc.extract_image.return_value = {"image": b"data"}  # no "ext" key

    url = _save_image(doc, xref=1, images_dir=str(tmp_path), product_id="prod1")
    assert url.endswith(".png")
