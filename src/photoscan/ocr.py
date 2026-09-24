"""Reading printed text off Prints with Apple's Vision framework (Live Text's engine).

On-device, on the Neural Engine. Machine-printed dates (lab stamps, camera
imprints, printed cards) read well; handwriting mostly doesn't, so only
date-shaped text is ever used (see dates.find_dates). Returns nothing where
Vision isn't available (e.g. Linux CI).
"""

import cv2
import numpy as np

LANGUAGES = ["fr-FR", "en-US", "de-DE"]

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
    if image.dtype == np.uint16:
        image = (image >> 8).astype(np.uint8)
    lines: list[str] = []
    for turns in range(4):
        for line in _recognise(np.rot90(image, turns)):
            if line not in lines:
                lines.append(line)
    return lines


def _recognise(image: np.ndarray) -> list[str]:
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
    return [str(r.topCandidates_(1)[0].string()) for r in (request.results() or [])]
