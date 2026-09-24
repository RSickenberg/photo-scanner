"""Reading and writing images with their metadata.

What Ugreen Photos uses (tested 2026-09-24, ADR 0002): EXIF DateTimeOriginal
to place a photo in time, and it shows XMP dc:title / dc:description and EXIF
ImageDescription. So:

- the Photo date, when known, goes to DateTimeOriginal (first day of its
  period); its real precision and where it came from go to XMP;
- the Source name is the title; the description spells out the date;
- EXIF DateTime keeps the scan time, for the record.
"""

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import tifffile
from PIL import ExifTags, Image

from photoscan import __version__
from photoscan.dates import PhotoDate

_XMP_TAG = 700
_EXIF_DESCRIPTION, _EXIF_DATETIME, _EXIF_SOFTWARE = 0x010E, 0x0132, 0x0131
_EXIF_DATETIME_ORIGINAL = 0x9003
_NS = {
    "x": "adobe:ns:meta/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "photoshop": "http://ns.adobe.com/photoshop/1.0/",
    "photoscan": "https://github.com/RSickenberg/photo-scanner/ns/1.0/",
}
_SOFTWARE = f"photoscan {__version__}"
_DATE_SOURCES = {
    "typed": "typed in",
    "ocr-back": "read on the back",
    "ocr-front": "read on the front",
    "source": "estimated for the Source",
}


@dataclass(frozen=True)
class Meta:
    title: str  # the Source's name
    scanned: datetime
    dpi: int
    photo_date: PhotoDate | None = None
    date_source: str | None = None  # typed | ocr-back | ocr-front | source

    @property
    def description(self) -> str:
        if self.photo_date is None:
            return f"{self.title} - date unknown"
        how = _DATE_SOURCES.get(self.date_source or "", self.date_source)
        return f"{self.title} - {self.photo_date} ({how})"


def write_tiff(path: Path, image: np.ndarray, meta: Meta) -> None:
    """Lossless (deflate) RGB TIFF, 8 or 16 bits per channel as given."""
    xmp = _xmp(meta)
    tifffile.imwrite(
        path,
        image,
        photometric="rgb",
        compression="zlib",
        resolution=(meta.dpi, meta.dpi),
        resolutionunit="INCH",
        datetime=meta.scanned,
        software=_SOFTWARE,
        description=_ascii(meta.description),
        metadata=None,
        extratags=[(_XMP_TAG, "B", len(xmp), xmp, True)],
    )


def write_jpeg(path: Path, image: np.ndarray, meta: Meta, *, quality: int = 95) -> None:
    """Sharing copy: always 8-bit, full chroma resolution."""
    if image.dtype == np.uint16:
        image = (image >> 8).astype(np.uint8)
    exif = Image.Exif()
    exif[_EXIF_DESCRIPTION] = _ascii(meta.description)
    exif[_EXIF_DATETIME] = meta.scanned.strftime("%Y:%m:%d %H:%M:%S")
    exif[_EXIF_SOFTWARE] = _SOFTWARE
    if meta.photo_date:
        exif.get_ifd(ExifTags.IFD.Exif)[_EXIF_DATETIME_ORIGINAL] = meta.photo_date.exif()
    Image.fromarray(image).save(
        path,
        quality=quality,
        subsampling=0,
        dpi=(meta.dpi, meta.dpi),
        exif=exif,
        xmp=_xmp(meta),
    )


def read_tiff(path: Path) -> tuple[np.ndarray, Meta]:
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        image = page.asarray()
        tags = page.tags
        num, den = tags["XResolution"].value if "XResolution" in tags else (0, 1)
        stamp = tags["DateTime"].value if "DateTime" in tags else None
        xmp = tags[_XMP_TAG].value if _XMP_TAG in tags else None
    return image, _meta_from(xmp, stamp, round(num / den))


def read_jpeg(path: Path) -> np.ndarray:
    with Image.open(path) as img:
        return np.asarray(img.convert("RGB"))


def read_meta(path: Path) -> Meta:
    if path.suffix.lower() in (".tif", ".tiff"):
        return read_tiff(path)[1]
    with Image.open(path) as img:
        stamp = img.getexif().get(_EXIF_DATETIME)
        dpi = round(img.info.get("dpi", (0, 0))[0])
        return _meta_from(img.info.get("xmp"), stamp, dpi)


def _meta_from(xmp: bytes | str | None, stamp: str | None, dpi: int) -> Meta:
    fields = _read_xmp(xmp)
    date_text = fields.get("date")
    if date_text and fields.get("approximate") == "True":
        date_text = f"~{date_text}"
    return Meta(
        title=fields.get("title", ""),
        scanned=datetime.strptime(stamp, "%Y:%m:%d %H:%M:%S") if stamp else datetime.now(),
        dpi=dpi,
        photo_date=PhotoDate.parse(date_text) if date_text else None,
        date_source=fields.get("date_source"),
    )


def _xmp(meta: Meta) -> bytes:
    def alt(text: str) -> str:
        return f'<rdf:Alt><rdf:li xml:lang="x-default">{escape(text)}</rdf:li></rdf:Alt>'

    date = meta.photo_date
    dated = ""
    if date:
        plain = str(PhotoDate(date.year, date.month, date.day, date.decade))
        # photoshop:DateCreated allows partial dates (1985, 1985-06); decades are
        # written as their first year, with the precision alongside.
        created = str(date.year) if date.decade else plain
        dated = (
            f"<photoshop:DateCreated>{created}</photoshop:DateCreated>"
            f"<photoscan:Date>{plain}</photoscan:Date>"
            f"<photoscan:DatePrecision>{date.precision}</photoscan:DatePrecision>"
            f"<photoscan:DateApproximate>{date.approximate}</photoscan:DateApproximate>"
            f"<photoscan:DateSource>{escape(meta.date_source or '')}</photoscan:DateSource>"
        )
    namespaces = " ".join(f'xmlns:{k}="{v}"' for k, v in _NS.items() if k not in ("x", "rdf"))
    return (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        f'<x:xmpmeta xmlns:x="{_NS["x"]}"><rdf:RDF xmlns:rdf="{_NS["rdf"]}">'
        f'<rdf:Description rdf:about="" {namespaces}>'
        f"<dc:title>{alt(meta.title)}</dc:title>"
        f"<dc:description>{alt(meta.description)}</dc:description>"
        f"{dated}"
        f"<xmp:MetadataDate>{meta.scanned.isoformat(timespec='seconds')}</xmp:MetadataDate>"
        f"<xmp:CreatorTool>{_SOFTWARE}</xmp:CreatorTool>"
        "</rdf:Description></rdf:RDF></x:xmpmeta>"
        '<?xpacket end="w"?>'
    ).encode()


def _read_xmp(xmp: bytes | str | None) -> dict[str, str]:
    if not xmp:
        return {}
    if isinstance(xmp, bytes):
        xmp = xmp.decode()
    # ElementTree rejects the xpacket processing instructions around the packet.
    start, end = xmp.find("<x:xmpmeta"), xmp.rfind("</x:xmpmeta>") + len("</x:xmpmeta>")
    root = ET.fromstring(xmp[start:end])

    def text(path: str) -> str | None:
        node = root.find(path, _NS)
        return node.text if node is not None else None

    fields = {
        "title": text(".//dc:title/rdf:Alt/rdf:li"),
        "date": text(".//photoscan:Date"),
        "approximate": text(".//photoscan:DateApproximate"),
        "date_source": text(".//photoscan:DateSource"),
    }
    return {k: v for k, v in fields.items() if v}


def _ascii(text: str) -> str:
    """EXIF/TIFF text tags are ASCII: fold accents (é -> e), drop the rest."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", folded)
