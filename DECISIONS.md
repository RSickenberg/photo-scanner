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
- **Premises:** glass dust doesn't move during a Session (recalibrate with `c` if it does); a Calibration at the Session's dpi lines up pixel for pixel with later Scans.
- **Amended (2026-09-24):** (1) With a calibration, a pixel is part of a Print only if it differs from the empty-glass reference *and* from the Scan's own background colour. On a real Scan with a thick Polaroid, the lid sat differently than during calibration and shaded a 2.5 mm gap between two Prints 7.1 units off the reference (cut-off 8) but only 3.3 off the Scan's lid colour; the reference test alone joined the two Prints. (2) A calibration made within `calibration_max_age_minutes` (120 by default) on the same scanner and dpi is reused by the next Sessions without asking, if its empty-glass Scan hasn't been pruned. `c` still redoes it. How much real glass dust gets caught is not yet measured: that needs a real Calibration with dust on the glass.

## D-007 (2026-09-24) — Archive by Source, Photo date in DateTimeOriginal, Backs read by Apple Vision

- **Status:** decided
- **Foundational:** yes
- **Decision:** see ADR 0002 for the layout (`photos/` for Ugreen Photos, `archive/` for masters, Scans, Backs and records; Sources instead of dated Session folders; no dates in names). Photo dates are chosen in this order: typed, Back text, front text, Source estimate, unknown. Approximate dates are written as the first day of their period. Text is read with Apple Vision (`pyobjc-framework-vision`, macOS only), trying all four orientations, and only date-shaped text is used. Backs are paired with fronts by position and size (up to 3 cm of movement, any turn, sizes within 10%). Nothing is migrated from the old layout.
- **Why:** the scan date is meaningless for a family archive, and Ugreen Photos only honours EXIF `DateTimeOriginal` (tested by the user). Backs mostly carry machine-printed dates. On a real Scan, Vision read "18.05.98" off a printed card in about 0.3 s but misread handwriting, hence dates only from date-shaped text. Tesseract was rejected: an extra install and weaker on photos, when Vision is built in. OCR-suggested dates needing confirmation were rejected for speed; they're traceable (`date_source`, `dates` report) and correctable (`photoscan date`). Two same-size Prints that swap places can't be told apart by position and size; accepted.
- **Premises:** the user browses in Ugreen Photos (pointed at `photos/` only) and in Finder. The only Session in the old layout was a test, already deleted. First day of the period chosen for approximate dates; the user didn't object.
- **Amended (2026-09-24), after a real Back pass on the white lid:** (1) A white Back can be detected as several pieces, none the size of its front. Pieces lying within 3 cm of an unpaired front are its Back, cut from the front's footprint plus those pieces; an undetected Back is still cut from the footprint so its faint printing can be read. On the real Scan: 3 of 3 Backs paired, 0 unmatched (was 2 paired, 3 unmatched pieces). (2) Backs are saved as JPEG only (user's call: they're kept for what's printed on them). (3) Only Vision lines with confidence ≥ 0.8 are used: it misread "18.05.98" as "18.05.38" at 0.5 and that became a wrong date, 1938; its correct reads scored 1.0. (4) More date shapes from real backs: year-first `99.12.25` (when the first number can't be a day) and month-year `03.2000`. When several are found, the most precise wins, then the earliest.

## D-008 (2026-09-24) — Printed captions stay with their Print

- **Status:** decided
- **Foundational:** no
- **Decision:** after detection, a side of a Print with small text fragments (too small to be Prints) within 2.5 cm is extended over them, then up to the paper's edge: the strongest highlight or lightness step, ≥ 2 units, within 1.5 cm past the text. Without text fragments, nothing is extended.
- **Why:** a real race photo had "20KM DE LAUSANNE 2009" printed on a white strip that's only 2–5 units off the white lid, so only its letters were detected, and the strip was cut off. Extending on edges alone was rejected: the lid has straight streaks too, which would add lid margins to Extracts.
- **Premises:** captions carry text. A plain white margin without text on the white lid is still lost (black cloth avoids it).
- **Amended (2026-09-24):** a caption between two Prints was claimed by both, and the upper Print's edge search stopped at the lower Print's top edge, so the Extracts overlapped. Each text fragment now belongs to the nearest Print only, and the search for a paper edge stops before any other Print. Verified on that real Scan: no overlap, caption kept with its photo.

## D-009 (2026-09-24) — Split Prints joined across a partly bridged gap

- **Status:** decided
- **Foundational:** no
- **Decision:** each detected shape is checked for a gap. On the raw mask (before the clean-up that fills small holes), lines across the shape along its sides are measured for coverage. A narrow dip (≤ 50% of the best-covered line within 1 cm on either side), leaving Print-sized parts on both sides, is a gap: the shape is cut there, the gap itself going to neither part, and each part is checked again (both directions, up to 3 levels).
- **Why:** on a real Scan, a photo and a thick Polaroid 2.5 mm apart were joined by a shadow along ~2.5 cm of their gap and came out as one Extract, with or without calibration. Shrinking the shape to break "necks" was tried and rejected: such a bridge is short but wide, so shrinking never cuts it. The gap's lines were ~15-28% covered, against ~100% inside Prints.
- **Premises:** Prints are solid (every line across them is mostly covered). Known risk: a thin object running the full height of a photo, lid-coloured and aligned with its edge, would look like a gap and split that photo; `recut` can redo it.

