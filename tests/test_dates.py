import pytest

from photoscan.dates import PhotoDate, choose_date, find_dates


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("1985-06-15", PhotoDate(1985, 6, 15)),
        ("1985-06", PhotoDate(1985, 6)),
        ("1985", PhotoDate(1985)),
        ("1980s", PhotoDate(1980, decade=True)),
        ("~1985", PhotoDate(1985, approximate=True)),
        ("ca 1985", PhotoDate(1985, approximate=True)),
        ("ca. 1985-06", PhotoDate(1985, 6, approximate=True)),
        ("~1970s", PhotoDate(1970, decade=True, approximate=True)),
        ("15.06.1985", PhotoDate(1985, 6, 15)),
        ("06.1985", PhotoDate(1985, 6)),
        ("  1985  ", PhotoDate(1985)),
    ],
)
def test_parse_typed_dates(typed, expected):
    assert PhotoDate.parse(typed) == expected


def test_empty_means_unknown():
    assert PhotoDate.parse("") is None
    assert PhotoDate.parse("   ") is None


@pytest.mark.parametrize("bad", ["yesterday", "1985-13", "31.02.1985", "1985s", "3000"])
def test_nonsense_is_refused(bad):
    with pytest.raises(ValueError):
        PhotoDate.parse(bad)


@pytest.mark.parametrize(
    ("date", "exif", "text"),
    [
        # Approximate dates become the first day of their period (Ugreen needs a full date).
        (PhotoDate(1985, 6, 15), "1985:06:15 12:00:00", "1985-06-15"),
        (PhotoDate(1985, 6), "1985:06:01 12:00:00", "1985-06"),
        (PhotoDate(1985), "1985:01:01 12:00:00", "1985"),
        (PhotoDate(1980, decade=True), "1980:01:01 12:00:00", "1980s"),
        (PhotoDate(1985, approximate=True), "1985:01:01 12:00:00", "ca. 1985"),
    ],
)
def test_exif_and_text_forms(date, exif, text):
    assert date.exif() == exif
    assert str(date) == text
    assert PhotoDate.parse(text) == date


@pytest.mark.parametrize(
    ("ocr", "expected"),
    [
        # Real OCR output from a LiDE 400 Scan (baby name card, 2026-09-24).
        ("Je suis née 18.05.98 à", [PhotoDate(1998, 5, 18)]),
        ("'87 6 12", [PhotoDate(1987, 6, 12)]),  # camera date imprint, year first
        ("6 12 '87", [PhotoDate(1987, 6, 12)]),  # camera date imprint, year last
        ("Développé en juin 1985", [PhotoDate(1985, 6)]),
        ("AUGUST 1979", [PhotoDate(1979, 8)]),
        ("März 1991", [PhotoDate(1991, 3)]),
        ("1985-06-15", [PhotoDate(1985, 6, 15)]),
        ("12/03/2004", [PhotoDate(2004, 3, 12)]),
    ],
)
def test_find_dates_in_recognised_text(ocr, expected):
    assert find_dates(ocr) == expected


@pytest.mark.parametrize(
    "ocr",
    [
        "2640",  # birth weight in grams, from the same real card
        "Mon poids a la naissance",
        "Doras 20 ENS",  # misread handwriting
        "31.02.98",  # not a real day
        "18.05.2098",  # in the future
        "1234 5678",
    ],
)
def test_no_date_found_where_there_is_none(ocr):
    assert find_dates(ocr) == []


def test_date_priority_typed_then_back_then_front_then_source():
    typed, estimate = PhotoDate(1984), PhotoDate(1980, decade=True)
    back, front = ["KODAK 18.05.98"], ["'87 6 12"]
    assert choose_date(typed, back, front, estimate) == (typed, "typed")
    assert choose_date(None, back, front, estimate) == (PhotoDate(1998, 5, 18), "ocr-back")
    assert choose_date(None, [], front, estimate) == (PhotoDate(1987, 6, 12), "ocr-front")
    assert choose_date(None, ["no date here"], [], estimate) == (estimate, "source")
    assert choose_date(None, [], [], None) == (None, None)
