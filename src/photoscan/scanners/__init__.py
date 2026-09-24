"""Scanner backends: the only place that knows how a Scan is obtained.

Everything else sees a `Scanner`. To support a scanner SANE can't drive, add
a module here implementing the protocol and register it in `_BACKENDS`
(see ADR 0001 for the ImageCaptureCore fallback).
"""

from typing import Protocol

import numpy as np


class ScannerError(Exception):
    pass


class Scanner(Protocol):
    @property
    def name(self) -> str | None:
        """Device identifier, recorded with each Scan; None until known."""
        ...

    def scan(self, dpi: int, *, deep: bool = False) -> np.ndarray:
        """One pass over the whole glass, as an RGB array (uint16 when `deep`)."""
        ...

    def devices(self) -> list[str]:
        """Devices this backend can see."""
        ...


def create(backend: str, device: str | None) -> Scanner:
    from photoscan.scanners.sane import SaneScanner

    backends = {"sane": SaneScanner}
    if backend not in backends:
        raise ScannerError(f"Unknown scanner backend {backend!r}; available: {', '.join(backends)}")
    return backends[backend](device=device)
