import cv2
import numpy as np
import pytest

from photoscan import ocr
from photoscan.dates import PhotoDate, find_dates

pytestmark = pytest.mark.skipif(not ocr.available(), reason="Apple Vision is macOS-only")


def test_reads_a_printed_lab_stamp_even_upside_down():
    back = np.full((260, 900, 3), 245, np.uint8)
    cv2.putText(back, "KODAK 18.05.98", (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 2.4, (30, 30, 30), 5)

    text = ocr.read_text(np.rot90(back, 2))

    assert [d for t in text for d in find_dates(t)] == [PhotoDate(1998, 5, 18)]


def test_blank_back_has_no_text():
    assert ocr.read_text(np.full((200, 300, 3), 245, np.uint8)) == []
