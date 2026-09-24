"""Reading and writing Scans and Extracts, with their Label and date embedded.

The Label goes into XMP (dc:title / dc:description) because it is free text
that may contain accents, which EXIF's ASCII fields can't hold. Date and
software go into the standard TIFF/EXIF tags.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import tifffile
from PIL import Image

from photoscan import __version__

_XMP_TAG = 700
_EXIF_DATETIME, _EXIF_SOFTWARE = 0x0132, 0x0131
_NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
}
_SOFTWARE = f"photoscan {__version__}"


@dataclass(frozen=True)
class Meta:
    label: str
    created: datetime
    dpi: int


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
        datetime=meta.created,
        software=_SOFTWARE,
        metadata=None,
        extratags=[(_XMP_TAG, "B", len(xmp), xmp, True)],
    )


def read_tiff(path: Path) -> tuple[np.ndarray, Meta]:
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        image = page.asarray()
        num, den = page.tags["XResolution"].value if "XResolution" in page.tags else (0, 1)
        stamp = page.tags["DateTime"].value if "DateTime" in page.tags else None
        xmp = page.tags[_XMP_TAG].value if _XMP_TAG in page.tags else None
    created = datetime.strptime(stamp, "%Y:%m:%d %H:%M:%S") if stamp else datetime.now()
    return image, Meta(label=_label_from_xmp(xmp), created=created, dpi=round(num / den))


def write_jpeg(path: Path, image: np.ndarray, meta: Meta, *, quality: int = 95) -> None:
    """Sharing copy: always 8-bit, full chroma resolution."""
    if image.dtype == np.uint16:
        image = (image >> 8).astype(np.uint8)
    exif = Image.Exif()
    exif[_EXIF_DATETIME] = meta.created.strftime("%Y:%m:%d %H:%M:%S")
    exif[_EXIF_SOFTWARE] = _SOFTWARE
    Image.fromarray(image).save(
        path,
        quality=quality,
        subsampling=0,
        dpi=(meta.dpi, meta.dpi),
        exif=exif,
        xmp=_xmp(meta),
    )


def read_label(path: Path) -> str:
    if path.suffix.lower() in (".tif", ".tiff"):
        return read_tiff(path)[1].label
    with Image.open(path) as img:
        return _label_from_xmp(img.info.get("xmp"))


def _xmp(meta: Meta) -> bytes:
    label = escape(meta.label)
    alt = f'<rdf:Alt><rdf:li xml:lang="x-default">{label}</rdf:li></rdf:Alt>'
    return (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        f'<rdf:RDF xmlns:rdf="{_NS["rdf"]}">'
        f'<rdf:Description rdf:about="" xmlns:dc="{_NS["dc"]}"'
        ' xmlns:xmp="http://ns.adobe.com/xap/1.0/">'
        f"<dc:title>{alt}</dc:title>"
        f"<dc:description>{alt}</dc:description>"
        f"<xmp:CreateDate>{meta.created.isoformat(timespec='seconds')}</xmp:CreateDate>"
        f"<xmp:CreatorTool>{_SOFTWARE}</xmp:CreatorTool>"
        "</rdf:Description></rdf:RDF></x:xmpmeta>"
        '<?xpacket end="w"?>'
    ).encode()


def _label_from_xmp(xmp: bytes | str | None) -> str:
    if not xmp:
        return ""
    if isinstance(xmp, bytes):
        xmp = xmp.decode()
    # ElementTree rejects the xpacket processing instructions around the packet.
    start, end = xmp.find("<x:xmpmeta"), xmp.rfind("</x:xmpmeta>") + len("</x:xmpmeta>")
    title = ET.fromstring(xmp[start:end]).find(".//dc:title/rdf:Alt/rdf:li", _NS)
    return title.text or "" if title is not None else ""
