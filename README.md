# photo-scanner

Back up old family photos quickly: put several Prints on a flatbed scanner
(built and tested with a **Canon CanoScan LiDE 400**), press Enter, and `photoscan` scans the glass, finds each Print,
straightens it and saves it as its own file. It then backs everything up to
your NAS. macOS only.

Words used below (see [CONTEXT.md](CONTEXT.md)):
- **Print**: a physical photo.
- **Scan**: one pass of the scanner, with several Prints on it.
- **Extract**: one Print cut out of a Scan.
- **Session**: one sitting, under one **Label**.

## Install

```bash
brew install sane-backends   # scanner driver (scanimage)
uv tool install git+https://github.com/RSickenberg/photo-scanner
photoscan config             # creates ~/.config/photoscan/config.toml from config.toml.example; set nas_dir there
photoscan devices            # should list your scanner, e.g. pixma:04A91912_…
```

### Other scanners

Any scanner [supported by SANE](http://www.sane-project.org/sane-supported-devices.html)
should work: `photoscan` reads each scanner's own options and picks its
colour and 16-bit modes. The first scanner found is used; set `device` in the
config to choose one. Scanners SANE can't drive need a new backend in
`src/photoscan/scanners/`, selected with `backend = "..."` in the config.

## Use

```bash
photoscan session "Grandma album 1970s"
```

Each Session starts with a **Calibration**: empty the glass, close the lid
(or lay the black cloth), and press Enter. `photoscan` learns what the
background looks like and where the dust is on the glass. Press `c` during
the Session to recalibrate, for example after switching between lid and cloth
or cleaning the glass. `s` or `--no-calibrate` skips it.

Lay the Prints on the glass **with a gap of about 1 cm between them**, about
5 mm from the glass edges, then
**cover them with a black cloth or sheet** instead of closing the white lid.
Detection is reliable on a dark background, but photos with white borders get
lost on the white lid. Press Enter to scan. Repeat with the next batch, and
press `q` to finish.

Known limitation: on the white lid, Prints with large near-white areas (sky,
white borders) can be split into pieces or missed. That's what the black
cloth avoids. Because the whole Scan is always kept, `recut` can redo the
cuts later.

Add `--preview` to see each Scan with numbered boxes, and press `r` to throw
away a bad cut and rescan. Add `--16bit` for special Prints. The default is
600 dpi, 8 bits per channel.

Each Session produces:

```
~/Pictures/photoscan/2026-09-24_grandma-album-1970s/
  session.json
  calibration/cal_01.tif                       empty glass, reference for the Session
  scans/grandma-album-1970s_s001.tif          whole Scan, kept for re-cutting
  extracts/grandma-album-1970s_s001_p01.tif   lossless archive copy
  extracts/grandma-album-1970s_s001_p01.jpg   for sharing
```

The Label and the date are embedded in every file (XMP title/description,
EXIF/TIFF date).

**Glass dust** found by the Calibration is repaired in the Extracts (TIFF and
JPEG). A speck is only repaired where the Extract shows the same speck, at
the same place and with the same shape. Lint on the lid shows up in the
Calibration too, but it ends up behind the Print, so it's left alone there.
The untouched Scan in `scans/` always keeps the original.

`session.json` keeps a record of the Session: every Calibration (time,
scanner, dpi, background colour, noise, detection cut-off, specks found) and,
for every Scan, when it was scanned, by which scanner, at which dpi and bit
depth, which Calibration it used, which Extracts came out of it, and how many
dust specks were repaired in each. It also holds running totals. Discarding a Scan from the preview
removes it from the record, and `recut` updates its Extracts and adds a
`recut_at` time.

```json
{
  "label": "Grandma album 1970s",
  "date": "2026-09-24",
  "calibrations": [
    {
      "id": "cal_01",
      "calibrated_at": "2026-09-24T19:00:42",
      "scanner": "pixma:04A91912_4FA05A",
      "dpi": 600,
      "background_lab": [234.3, 128.1, 129.2],
      "noise": 2.12,
      "threshold": 8.0,
      "dust_specks": 1940
    }
  ],
  "scans": [
    {
      "scan": "grandma-album-1970s_s001",
      "scanned_at": "2026-09-24T19:02:11",
      "scanner": "pixma:04A91912_4FA05A",
      "dpi": 600,
      "bits": 8,
      "calibration": "cal_01",
      "extracts": ["grandma-album-1970s_s001_p01", "grandma-album-1970s_s001_p02"],
      "dust_repaired": { "grandma-album-1970s_s001_p01": 2, "grandma-album-1970s_s001_p02": 0 }
    }
  ],
  "totals": { "scans": 1, "extracts": 2 }
}
```

| Command | What it does |
|---|---|
| `photoscan session [LABEL]` | Calibrate, then scan batch after batch |
| `photoscan recut scans/*.tif` | Redo the Extracts of existing Scans |
| `photoscan rotate FILE… --degrees 90` | Turn Extracts clockwise (TIFF and JPEG together) |
| `photoscan sync` | Copy anything not yet on the NAS, verifying each file |
| `photoscan prune` | Delete local files whose NAS copy is verified identical |
| `photoscan prune --force` | Delete **all** local Scans and Extracts without checking the NAS. Warns how many were never backed up; `--yes` skips the question |
| `photoscan devices` / `config` | Scanner list / config file |

## NAS backup

Files are always written locally first, then copied to `nas_dir` in the
background after each Scan. Each copy is checked with SHA-256 before it
counts as backed up. If the NAS isn't mounted, scanning carries on; run
`photoscan sync` later. `prune` frees local space and only deletes files
whose NAS copy matches.

## Development

```bash
make install   # uv sync + npm install (release tooling)
make test
make lint
make release   # release-it: bumps VERSION, CHANGELOG, signed tag, draft GitHub release
```

Tests use generated images (`tests/synthetic.py`), never real photos.
Design decisions are recorded in [DECISIONS.md](DECISIONS.md) and
[docs/adr/](docs/adr/).
