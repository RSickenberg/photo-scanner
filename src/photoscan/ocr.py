"""Reading printed text off Prints with Apple's Vision framework (Live Text's engine).

On-device, on the Neural Engine. Machine-printed dates (lab stamps, camera
imprints, printed cards) read well; handwriting mostly doesn't, so only
date-shaped text is ever used (see dates.find_dates). Returns nothing where
Vision isn't available (e.g. Linux CI).
"""

import cv2
import numpy as np

from photoscan.imagefiles import to_8bit

LANGUAGES = ["fr-FR", "en-US", "de-DE"]
# Vision scores lines coarsely (0.3 / 0.5 / 1.0). On a real card it read
# "18.05.98" at 1.0 but also misread it as "18.05.38" at 0.5: a wrong date is
# worse than none, so only confident lines are kept.
MIN_CONFIDENCE = 0.8

try:
    import Vision
    from Foundation import NSData
except ImportError:  # not macOS
    Vision = None


def available() -> bool:
    return Vision is not None


def read_text(image: np.ndarray) -> list[str]:
    """Every line of text found, trying the four orientations (a Print or its
    Back can lie any way round on the glass)."""
    if Vision is None:
        return []
    image = to_8bit(image)
    lines: list[str] = []
    for turns in range(4):
        for line in confident(_recognise(np.rot90(image, turns))):
            if line not in lines:
                lines.append(line)
    return lines


def confident(lines: list[tuple[str, float]]) -> list[str]:
    return [text for text, confidence in lines if confidence >= MIN_CONFIDENCE]


def _recognise(image: np.ndarray) -> list[tuple[str, float]]:
    ok, png = cv2.imencode(".png", cv2.cvtColor(np.ascontiguousarray(image), cv2.COLOR_RGB2BGR))
    if not ok:
        return []
    data = NSData.dataWithBytes_length_(png.tobytes(), len(png))
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setRecognitionLanguages_(LANGUAGES)
    request.setUsesLanguageCorrection_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
    success, _ = handler.performRequests_error_([request], None)
    if not success:
        return []
    best = [r.topCandidates_(1)[0] for r in (request.results() or [])]
    return [(str(c.string()), float(c.confidence())) for c in best]
