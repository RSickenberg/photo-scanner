# 1. Drive the scanner through SANE, from Python

Date: 2026-09-24
Status: Accepted (verified on the real LiDE 400, 2026-09-24)

## Context

The tool must trigger Scans on a Canon CanoScan LiDE 400 from a Mac,
without a GUI, and then detect and cut out each Print. Two viable ways to
reach the scanner:

- **SANE** (`sane-backends` via Homebrew, `scanimage` CLI, `pixma` backend,
  which lists the LiDE 400 as supported), used from Python, with OpenCV for
  detection.
- **Apple ImageCaptureCore** from Swift, through Canon's installed ICA driver,
  with Vision / CoreImage for detection.

## Decision

Use Python + SANE + OpenCV. Scanner access sits behind a single narrow
interface ("give me a Scan at N dpi"), the `Scanner` protocol in
`photoscan.scanners`, so the backend can be replaced without touching
detection, cutting, or storage. The backend is chosen in config
(`backend = "sane"`), and the SANE backend adapts to each device's own option
names, so any SANE-supported scanner should work, not just the LiDE 400.

## Consequences

- Detection and cutting are plain Python, easy to unit-test against fixture
  Scans in CI, with no scanner needed.
- Depends on SANE's libusb access working on current macOS. If the spike
  fails, fall back to **Swift + ImageCaptureCore + Vision/CoreImage**, as
  agreed with the user. Because the fallback also brings its own detection
  (Vision), switching would be a rewrite, not just a backend swap. That is
  the main reason this ADR exists.
