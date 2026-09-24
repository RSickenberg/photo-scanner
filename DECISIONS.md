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

- **Status:** decided (pending a test on the real scanner)
- **Foundational:** yes
- **Decision:** Python, driving `scanimage` (Homebrew `sane-backends`, `pixma` backend); detection and cutting with OpenCV. Details in `docs/adr/0001-sane-for-scanner-access.md`.
- **Why:** detection logic is plain, testable Python; SANE lists the LiDE 400 as supported. Swift + ImageCaptureCore + Vision rejected for now (harder CLI setup, fewer references), but agreed as the fallback.
- **Premises:** `scanimage -L` sees the LiDE 400 over USB on this Mac (macOS 27). Not yet verified: scanner was unplugged on 2026-09-24.

## D-002 (2026-09-24) — Write locally, copy to the NAS in the background

- **Status:** decided
- **Foundational:** yes
- **Decision:** Sessions are written to a local `output_dir`. After each Scan, a background thread copies new or changed files to the mounted NAS share (`nas_dir`), checks each copy with SHA-256, and records it in `<output_dir>/.backup.json`. `prune` deletes local files only after re-verifying the NAS copy.
- **Why:** scanning must never wait on the network or lose work when Wi-Fi drops or the Mac sleeps. Writing straight to the share was rejected for exactly that reason. The tool reads a Finder-mounted folder instead of connecting to the NAS itself, so no NAS password is stored in the tool.
- **Premises:** the NAS is reachable as an SMB share mounted under `/Volumes`; one `photoscan` process at a time writes the manifest.

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

