"""Photo dates: when a Print's picture was taken, as precisely as it is known.

Ugreen Photos places photos by EXIF DateTimeOriginal only, which needs a full
date (ADR 0002). An approximate date is therefore written as the first day of
its period, while its real precision is kept alongside (XMP, records).
"""

import re
from dataclasses import dataclass
from datetime import date

_MONTHS = {
    # French, English, German; OCR may drop accents, so both spellings.
    **dict.fromkeys(["janvier", "january", "januar", "jan"], 1),
    **dict.fromkeys(["fevrier", "février", "february", "februar", "feb", "fév", "fev"], 2),
    **dict.fromkeys(["mars", "march", "märz", "marz", "mar"], 3),
    **dict.fromkeys(["avril", "april", "apr", "avr"], 4),
    **dict.fromkeys(["mai", "may"], 5),
    **dict.fromkeys(["juin", "june", "juni", "jun"], 6),
    **dict.fromkeys(["juillet", "july", "juli", "jul", "juil"], 7),
    **dict.fromkeys(["aout", "août", "august", "aug"], 8),
    **dict.fromkeys(["septembre", "september", "sep", "sept"], 9),
    **dict.fromkeys(["octobre", "october", "oktober", "oct", "okt"], 10),
    **dict.fromkeys(["novembre", "november", "nov"], 11),
    **dict.fromkeys(["decembre", "décembre", "december", "dezember", "dec", "dez", "déc"], 12),
}
_MONTH_WORDS = "|".join(sorted(_MONTHS, key=len, reverse=True))


@dataclass(frozen=True)
class PhotoDate:
    year: int
    month: int | None = None
    day: int | None = None
    decade: bool = False
    approximate: bool = False

    def __post_init__(self):
        if not 1850 <= self.year <= date.today().year:
            raise ValueError(f"implausible year {self.year}")
        if self.decade and (self.year % 10 or self.month):
            raise ValueError("a decade has no month and starts on a round year")
        if self.day and not self.month:
            raise ValueError("a day needs a month")
        date(self.year, self.month or 1, self.day or 1)  # raises on 31.02 and friends
        if self.first_day() > date.today():
            raise ValueError("date in the future")

    @property
    def precision(self) -> str:
        if self.decade:
            return "decade"
        return "day" if self.day else "month" if self.month else "year"

    def first_day(self) -> date:
        return date(self.year, self.month or 1, self.day or 1)

    def exif(self) -> str:
        """EXIF DateTimeOriginal: the first day of the period, at noon."""
        return self.first_day().strftime("%Y:%m:%d 12:00:00")

    def __str__(self) -> str:
        if self.decade:
            text = f"{self.year}s"
        else:
            text = "-".join(f"{v:02d}" for v in (self.year, self.month, self.day) if v)
        return f"ca. {text}" if self.approximate else text

    @classmethod
    def parse(cls, text: str) -> "PhotoDate | None":
        """A typed date; empty means unknown. Raises ValueError on anything else."""
        text = text.strip().lower()
        if not text:
            return None
        approximate = bool(re.match(r"(~|ca\.?\s*|circa\s+)", text))
        text = re.sub(r"^(~|ca\.?\s*|circa\s+)", "", text).strip()
        if m := re.fullmatch(r"(\d{4})s", text):
            return cls(int(m[1]), decade=True, approximate=approximate)
        if m := re.fullmatch(r"(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", text):
            return cls(*_ints(m[1], m[2], m[3]), approximate=approximate)
        if m := re.fullmatch(r"(?:(\d{1,2})\.)?(\d{1,2})\.(\d{4})", text):
            return cls(*_ints(m[3], m[2], m[1]), approximate=approximate)
        raise ValueError(f"not a date: {text!r} (try 1985-06-15, 1985-06, 1985, 1980s, ~1985)")


def find_dates(text: str) -> list[PhotoDate]:
    """Dates in text read off a Print (lab stamps, camera imprints, printed cards).

    Only shapes that are clearly dates: a lone number like "1985" or "2640" is
    too often something else (a weight, a lab code) to be trusted.
    """
    found = []
    t = text.lower()
    patterns = [
        # 1985-06-15
        (r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", lambda m: (m[1], m[2], m[3])),
        # 18.05.98, 12/03/2004, 18-05-1998 (day first: European prints)
        (r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})\b", lambda m: (m[3], m[2], m[1])),
        # camera imprints: '87 6 12 (year first) and 6 12 '87 (year last)
        (r"['’](\d{2})\s+(\d{1,2})\s+(\d{1,2})\b", lambda m: (m[1], m[2], m[3])),
        (r"\b(\d{1,2})\s+(\d{1,2})\s+['’](\d{2})\b", lambda m: (m[3], m[1], m[2])),
        # juin 1985, AUGUST 1979, März 1991
        (rf"\b({_MONTH_WORDS})\.?\s+(\d{{4}})\b", lambda m: (m[2], _MONTHS[m[1]], None)),
    ]
    for pattern, parts in patterns:
        for m in re.finditer(pattern, t):
            year, month, day = parts(m)
            try:
                candidate = PhotoDate(*_ints(_full_year(year), month, day))
            except ValueError:
                continue
            if candidate not in found:
                found.append(candidate)
    return found


def _full_year(year: str | int) -> int:
    year = int(year)
    if year >= 100:
        return year
    # Two-digit years: the most recent past one ('98 -> 1998, '05 -> 2005).
    this = date.today().year
    return 2000 + year if 2000 + year <= this else 1900 + year


def _ints(*values) -> tuple:
    return tuple(int(v) if v is not None else None for v in values)


def choose_date(
    typed: PhotoDate | None,
    back_text: list[str],
    front_text: list[str],
    estimate: PhotoDate | None,
) -> tuple[PhotoDate | None, str | None]:
    """The Photo date to use, and where it came from, most trusted first.

    A date typed in wins; then one read on the Back (lab stamps are dates by
    design), then on the front (camera imprints, but also any text in the
    picture); then the Source's estimate. Otherwise unknown: nothing invented.
    """
    if typed:
        return typed, "typed"
    for texts, source in ((back_text, "ocr-back"), (front_text, "ocr-front")):
        if found := [d for t in texts for d in find_dates(t)]:
            return found[0], source
    if estimate:
        return estimate, "source"
    return None, None
