# photo-scanner

Back up old family photos quickly: put several Prints on a **Canon CanoScan
LiDE 400**, press Enter, and `photoscan` scans the glass, finds each Print,
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
photoscan config             # creates ~/.config/photoscan/config.toml; set nas_dir there
photoscan devices            # should list the LiDE 400 (pixma:...)
```

## Use

```bash
photoscan session "Grandma album 1970s"
```

Lay the Prints on the glass **with a gap of about 1 cm between them**, then
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
  scans/grandma-album-1970s_s001.tif          whole Scan, kept for re-cutting
  extracts/grandma-album-1970s_s001_p01.tif   lossless archive copy
  extracts/grandma-album-1970s_s001_p01.jpg   for sharing
```

The Label and the date are embedded in every file (XMP title/description,
EXIF/TIFF date).

| Command | What it does |
|---|---|
| `photoscan session [LABEL]` | Scan batch after batch |
| `photoscan recut scans/*.tif` | Redo the Extracts of existing Scans |
| `photoscan rotate FILE… --degrees 90` | Turn Extracts clockwise (TIFF and JPEG together) |
| `photoscan sync` | Copy anything not yet on the NAS, verifying each file |
| `photoscan prune` | Delete local files whose NAS copy is verified identical |
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
