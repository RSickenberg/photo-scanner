from datetime import datetime

import numpy as np
import pytest
import tifffile
from PIL import ExifTags, Image

from photoscan.dates import PhotoDate
from photoscan.imagefiles import Meta, read_meta, read_tiff, write_jpeg, write_tiff

SCANNED = datetime(2026, 9, 24, 20, 15, 0)
IMAGE = np.full((40, 60, 3), 128, np.uint8)


def _meta(**kwargs):
    return Meta(**{"title": "Album Grand-mère", "scanned": SCANNED, "dpi": 600, **kwargs})


def _exif(path):
    with Image.open(path) as img:
        exif = img.getexif()
        return exif, exif.get_ifd(ExifTags.IFD.Exif)


def test_known_date_goes_to_datetimeoriginal_the_field_ugreen_reads(tmp_path):
    path = tmp_path / "x.jpg"
    write_jpeg(path, IMAGE, _meta(photo_date=PhotoDate(1985, 6), date_source="typed"))

    exif, sub = _exif(path)
    assert sub[0x9003] == "1985:06:01 12:00:00"  # DateTimeOriginal
    assert exif[0x0132] == "2026:09:24 20:15:00"  # DateTime: the scan, for the record


def test_unknown_date_writes_no_datetimeoriginal(tmp_path):
    path = tmp_path / "x.jpg"
    write_jpeg(path, IMAGE, _meta())

    _, sub = _exif(path)
    assert 0x9003 not in sub


def test_title_and_descriptions_that_ugreen_shows(tmp_path):
    path = tmp_path / "x.jpg"
    meta = _meta(photo_date=PhotoDate(1975, approximate=True), date_source="source")
    write_jpeg(path, IMAGE, meta)

    exif, _ = _exif(path)
    back = read_meta(path)
    assert back.title == "Album Grand-mère"
    assert "ca. 1975" in back.description
    # EXIF ImageDescription is ASCII only: accents are folded, not mangled.
    assert exif[0x010E] == "Album Grand-mere - ca. 1975 (estimated for the Source)"


def test_precision_and_date_source_survive_a_round_trip(tmp_path):
    meta = _meta(photo_date=PhotoDate(1980, decade=True), date_source="ocr-back")
    for name, write in (("x.jpg", write_jpeg), ("x.tif", write_tiff)):
        write(tmp_path / name, IMAGE, meta)

        back = read_meta(tmp_path / name)

        assert back.photo_date == PhotoDate(1980, decade=True)
        assert back.date_source == "ocr-back"
        assert back.title == "Album Grand-mère"
        assert back.scanned == SCANNED
        assert back.dpi == 600


def test_tiff_master_is_lossless_and_keeps_16_bits(tmp_path):
    path = tmp_path / "x.tif"
    deep = IMAGE.astype(np.uint16) * 257

    write_tiff(path, deep, _meta())

    image, _ = read_tiff(path)
    np.testing.assert_array_equal(image, deep)
    with tifffile.TiffFile(path) as t:
        assert t.pages[0].compression != 1


def test_jpeg_from_16_bit_is_8_bit(tmp_path):
    path = tmp_path / "x.jpg"
    write_jpeg(path, IMAGE.astype(np.uint16) * 257, _meta())
    assert Image.open(path).mode == "RGB"
    assert Image.open(path).info["dpi"] == pytest.approx((600, 600))
