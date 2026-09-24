import cv2
import numpy as np
import pytest

from photoscan import ocr
from photoscan.dates import PhotoDate, find_dates

needs_vision = pytest.mark.skipif(not ocr.available(), reason="Apple Vision is macOS-only")


@needs_vision
def test_reads_a_printed_lab_stamp_even_upside_down():
    back = np.full((260, 900, 3), 245, np.uint8)
    cv2.putText(back, "KODAK 18.05.98", (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 2.4, (30, 30, 30), 5)

    text = ocr.read_text(np.rot90(back, 2))

    assert [d for t in text for d in find_dates(t)] == [PhotoDate(1998, 5, 18)]


@needs_vision
def test_blank_back_has_no_text():
    assert ocr.read_text(np.full((200, 300, 3), 245, np.uint8)) == []


def test_only_confident_lines_are_kept():
    # Real misread (2026-09-24): Vision gave "18.05.38" (for 18.05.98) confidence 0.5,
    # while its correct readings of the same card scored 1.0.
    lines = [("18.05.38 à 718", 0.5), ("18.05.98 à", 1.0), ("0622", 0.3)]
    assert ocr.confident(lines) == ["18.05.98 à"]
