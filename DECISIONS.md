<!--
Decision log for this project. Maintained by the `decisions` Claude Code
skill (.claude/skills/decisions/SKILL.md) — read that file for the rules.
Short version: entries are for decisions that are foundational, whose
reasoning wouldn't otherwise survive in the code/commit, or that you asked
to be tracked. Never delete an entry; supersede or reopen it instead.
-->

# Decisions

## Open questions

<!-- one line each; delete once ruled (git history keeps them) -->

## Log

<!--
## D-001 (YYYY-MM-DD) — short title

- **Status:** open | decided | reaffirmed (date) | reopened | superseded by D-NNN
- **Foundational:** yes | no
- **Decision:** what was decided (or the options, while open)
- **Why:** the reasoning, including alternatives rejected and why
- **Premises:** the facts and context this decision depends on
-->

## D-001 (2026-09-24) — Python + SANE for scanner access

- **Status:** decided (verified on the real scanner 2026-09-24)
- **Foundational:** yes
- **Decision:** Python, driving `scanimage` (Homebrew `sane-backends`, `pixma` backend); detection and cutting with OpenCV. Details in `docs/adr/0001-sane-for-scanner-access.md`.
- **Why:** detection logic is plain, testable Python; SANE lists the LiDE 400 as supported. Swift + ImageCaptureCore + Vision rejected for now (harder CLI setup, fewer references), but agreed as the fallback.
- **Premises:** `scanimage -L` sees the LiDE 400 over USB on this Mac (macOS 27) as `pixma:04A91912_…`: verified 2026-09-24, 8-bit (`--mode Color`) and 16-bit (`--mode "48 bits color"`; pixma has no `--depth`) both scan.

## D-002 (2026-09-24) — Write locally, copy to the NAS in the background

- **Status:** decided
- **Foundational:** yes
- **Decision:** Sessions are written to a local `output_dir`. After each Scan, a background thread copies new or changed files to the mounted NAS share (`nas_dir`), checks each copy with SHA-256, and records it in `<output_dir>/.backup.json`. `prune` deletes local files only after re-verifying the NAS copy.
- **Why:** scanning must never wait on the network or lose work when Wi-Fi drops or the Mac sleeps. Writing straight to the share was rejected for exactly that reason. The tool reads a Finder-mounted folder instead of connecting to the NAS itself, so no NAS password is stored in the tool.
- **Premises:** the NAS is reachable as an SMB share mounted under `/Volumes`; one `photoscan` process at a time writes the manifest.
- **Amended (2026-09-24):** at the user's request, `prune --force` bypasses the NAS entirely and deletes all local files, backed up or not (`session.json` kept). It prints how many files were never backed up and asks for confirmation unless `--yes` is given. Plain `prune` keeps the verified-only rule.

## D-003 (2026-09-24) — Output format

- **Status:** decided
- **Foundational:** no
- **Decision:** 600 dpi, 8-bit colour by default (`--16bit` optional), black-and-white Prints scanned in colour too. Each Extract is saved as deflate-compressed TIFF plus JPEG q95 (4:4:4). The whole Scan is always kept. Label goes in XMP (dc:title/description), date in TIFF/EXIF DateTime.
- **Why:** 600 dpi is the usual archival resolution for prints. The TIFF is the lossless master and the JPEG is for sharing. Keeping the whole Scan means detection mistakes can be fixed later with `recut`. XMP rather than EXIF because Labels can contain accents.
- **Premises:** about 26 MB per 6×4" Print at 8-bit before compression is acceptable NAS usage.

## D-004 (2026-09-24) — Release tooling via a release-only package.json

- **Status:** decided
- **Foundational:** no
- **Decision:** use the project-template's release-it + auto-changelog flow unchanged, through a `package.json` that holds only release devDependencies. `@release-it/bumper` writes `VERSION`, which hatchling reads as the Python package version.
- **Why:** same `npm run release` as the other projects. A Python-native release tool was rejected to keep one process across repos.
- **Premises:** Node is available on the release machine.

## D-005 (2026-09-24) — Scanner backends behind a protocol; SANE reads each device's options

- **Status:** decided
- **Foundational:** yes
- **Decision:** scanner access lives in `photoscan/scanners/`: a `Scanner` protocol (`name`, `scan`, `devices`) and `create(backend, device)`, selected by `backend` in the config (only `"sane"` today). The SANE backend doesn't hard-code option names. It reads `scanimage --all-options` once per device and picks the colour mode, plus a 16-bit mode (`48 bits…`) or `--depth 16`, whichever the device offers. The device name is recorded with each Scan in `session.json`.
- **Why:** the user wants the tool open to more scanners. The pixma backend names 16-bit `--mode "48 bits color"` and has no `--depth`, which broke the first real scan, while other backends do the opposite. Reading options per device covers all SANE scanners without per-model code. The backend registry is the seam for scanners SANE can't drive (e.g. ImageCaptureCore, ADR 0001). A plugin/entry-point system was rejected as overkill for a one-person tool.
- **Premises:** SANE backends expose their colour mode as `Color` and 16-bit either as a `48…` mode or a `--depth` choice of `16` (true for pixma, genesys, epson2 as of sane-backends 1.x).

## D-006 (2026-09-24) — Per-Session Calibration; repair only glass dust that matches

- **Status:** decided
- **Foundational:** no
- **Decision:** each Session starts with a Calibration: a Scan of the empty glass at the Session's dpi, saved under `calibration/` and recorded in `session.json`. Detection then compares each Scan pixel by pixel with that reference, instead of one colour estimated from the Scan's border. Specks found in the Calibration are repaired in an Extract (TIFF + JPEG, OpenCV Telea inpainting) only where the Extract shows the same speck: visible there, and with a speck-contrast correlation of at least 0.6 with the Calibration. Noise figures are taken from p90 and scaled (×1.41), not from p99.
- **Why:** the user asked for calibration and dust removal. A real LiDE 400 lid showed ~1900 fibres. With a plain dust map, lint on the lid (which ends up behind the Print) would have been "repaired" over real photo detail: 38 false repairs on two real Polaroids with a visible-only rule, 0 with shape matching. p99 noise was inflated to 9 by the fibres, which would have pushed the cut-off above Polaroid frames (~12). Dust on the Prints themselves stays out of scope, because the LiDE 400 has no infrared channel and software guessing risks erasing real detail. A GPU/Metal path was rejected: image processing takes ~0.3 s per Scan, while the scanner takes 20 s or more.
- **Premises:** glass dust doesn't move during a Session (recalibrate with `c` if it does); a Calibration at the Session's dpi lines up pixel for pixel with later Scans. How much real glass dust gets caught is not yet measured: that needs a real Calibration with dust on the glass.

