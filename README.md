# photo-scanner

Back up old family photos quickly: put several Prints on a flatbed scanner
(built and tested with a **Canon CanoScan LiDE 400**) and press Enter.
`photoscan` scans the glass, finds each Print, straightens it, saves it as
its own file, dates it, and backs everything up to your NAS, laid out for
**Ugreen Photos**. macOS only.

Words used below (see [CONTEXT.md](CONTEXT.md)):
- **Print**: a physical photo.
- **Source**: where Prints come from: an album, a box, an envelope. The archive is organised by Source.
- **Scan**: one pass of the scanner, with several Prints on it.
- **Extract**: one Print cut out of a Scan.
- **Back**: the reverse side of a Print, often with a printed date.
- **Photo date**: when the picture was taken, as precisely as it's known.
- **Session**: one sitting of scanning, possibly across several Sources.

## Install

```bash
brew install sane-backends   # scanner driver (scanimage)
uv tool install git+https://github.com/RSickenberg/photo-scanner
photoscan config             # creates ~/.config/photoscan/config.toml from config.toml.example; set nas_dir there
photoscan devices            # should list your scanner, e.g. pixma:04A91912_…
```

In Ugreen Photos, add **only `<nas_dir>/photos`** as a photo folder. The
`archive/` tree next to it holds masters, whole Scans and Backs, which would
otherwise show up as duplicates in the timeline.

### Other scanners

Any scanner [supported by SANE](http://www.sane-project.org/sane-supported-devices.html)
should work: `photoscan` reads each scanner's own options and picks its
colour and 16-bit modes. The first scanner found is used; set `device` in the
config to choose one. Scanners SANE can't drive need a new backend in
`src/photoscan/scanners/`, selected with `backend = "..."` in the config.

## Use

```bash
photoscan session "Album Grand-mère"
```

A new Source asks for its rough date (`1970s`, `~1985`, or Enter for
unknown). Without a name, `photoscan session` lists the existing Sources to
pick from.

Each Session starts with a **Calibration**: empty the glass, close the lid
(or lay the black cloth), and press Enter. `photoscan` learns what the
background looks like and where the dust is on the glass. If a calibration
was made less than `calibration_max_age_minutes` ago (120 by default) on the
same scanner at the same dpi, it's reused without asking. `s` or
`--no-calibrate` skips calibration.

Lay the Prints on the glass **with a gap of about 1 cm between them** and
about 5 mm from the glass edges, then **cover them with a black cloth or
sheet** instead of closing the white lid. The prompt shows what the next Scan
is filed under, e.g. `[Album Grand-mère · est. 1970s]`:

| Key | Does |
|---|---|
| Enter | Scan the Prints on the glass |
| `b` | Scan the **Backs** (at `back_dpi`, 300 by default: half the time of 600, enough for printed dates): flip every Print in place, then Enter. Each Back is paired with its front even if it moved a little; one that can't be paired is kept and reported |
| `d` | Date the **latest Scan** of the current Source, even one from an earlier Session (`1985-06-15`, `1985-06`, `1985`, `1980s`, `~1985`; empty clears it). Extracts already dated by hand or by their Back keep their date. It isn't carried over: each Scan starts undated |
| `o` | Switch to another Source, or create one |
| `c` | Recalibrate, e.g. after switching between lid and cloth or cleaning the glass |
| `q` | Finish |

Add `--preview` to see each Scan with numbered boxes, and press `r` to throw
away a bad cut and rescan. Add `--16bit` for special Prints. The default is
600 dpi, 8 bits per channel.

A printed caption on a white strip (e.g. "20KM DE LAUSANNE 2009" under a
race photo) stays with its Print: the text is found next to the photo and the
Print is extended over it, up to the strip's paper edge.

Known limitation: on the white lid, Prints with large near-white areas (sky,
plain white borders without text) can be split into pieces or missed. That's
what the black cloth avoids. Because the whole Scan is always kept, `recut`
can redo the cuts later.

### Layout

```
~/Pictures/photoscan/
  photos/album-grand-mere/album-grand-mere_s001_p01.jpg          one JPEG per Print: Ugreen's folder
  archive/album-grand-mere/source.json                            the Source's record
  archive/album-grand-mere/scans/album-grand-mere_s001.tif         whole Scans (+ _back.jpg)
  archive/album-grand-mere/masters/album-grand-mere_s001_p01.tif   lossless Extracts
  archive/album-grand-mere/backs/album-grand-mere_s001_p01_back.jpg
  archive/_sessions/2026-09-24_01.json                             each sitting
  archive/_calibrations/2026-09-24_01_cal_01.tif                   empty-glass Scans
```

Names never contain the Photo date, so fixing a date never renames a file or
makes the NAS Backup copy it again.

### Photo dates

Ugreen Photos places photos by EXIF `DateTimeOriginal`, so that's where the
Photo date goes, not the scan date. It's chosen in this order:

1. a date set by hand for that Extract (`photoscan date`);
2. a date printed on the Back (lab stamps, e.g. `13.07.2009`, `99.12.25`,
   `03.2000`), read by Apple Vision on the Mac. Only text Vision is confident
   about is used, and when several dates are found, the most precise wins,
   then the earliest (a picture is taken before it's printed);
3. a date set for its whole Scan (`d` in a Session);
4. a date printed on the front (camera imprints, printed cards);
5. the Source's rough date;
6. otherwise unknown: no date is invented, and Ugreen falls back to the
   file's date.

Approximate dates are written as the first day of their period (`1980s` is
1980-01-01, `~1985` is 1985-01-01). Their real precision is kept in XMP and in
`source.json`. Ugreen shows the Source name as the title and a description
such as "Album Grand-mère - ca. 1975 (estimated for the Source)".

```bash
photoscan date 1983-07 photos/album-grand-mere/album-grand-mere_s004_p02.jpg
photoscan date "~1975" --source "Album Grand-mère"   # new estimate; re-dates what used it
photoscan dates "Album Grand-mère"                   # every Extract, its date, where it came from
```

### Glass dust

Dust found by the Calibration is repaired in the Extracts. A speck is only
repaired where the Extract shows the same speck, at the same place and with
the same shape. Lint on the lid shows up in the Calibration too, but it ends
up behind the Print, so it's left alone there. The untouched Scan in
`scans/` always keeps the original.

### Records

`source.json` records every Scan of the Source: when, in which Session, by
which scanner, at which dpi and bit depth, with which Calibration, and each
Extract's region, Photo date and where it came from, the text read on its
front and Back, and the dust specks repaired. It also holds totals (scans,
extracts, dated, undated). Each Session's record in `archive/_sessions/`
lists its Calibrations (background colour, noise, detection cut-off, specks
found) and the Scans it made. Records are never pruned.

## Commands

| Command | What it does |
|---|---|
| `photoscan session [SOURCE]` | Calibrate, then scan batch after batch |
| `photoscan date DATE FILE…` | Set the Photo date of Extracts (empty `""` clears a typed date) |
| `photoscan date DATE --source NAME` | Set a Source's rough date |
| `photoscan dates [SOURCE]` | List Extracts with their Photo date and where it came from |
| `photoscan recut archive/*/scans/*.tif` | Redo the Extracts (and Backs) of existing Scans |
| `photoscan rotate FILE… --degrees 90` | Turn Extracts clockwise (master and photo together) |
| `photoscan sync` | Copy anything not yet on the NAS, verifying each file |
| `photoscan prune` | Delete local files whose NAS copy is verified identical |
| `photoscan prune --force` | Delete **all** local images without checking the NAS. Warns how many were never backed up; `--yes` skips the question |
| `photoscan devices` / `config` | Scanner list / config file |

## NAS backup

Files are always written locally first, then copied to `nas_dir` in the
background after each Scan, keeping their file dates. Each copy is checked
with SHA-256 before it counts as backed up. If the NAS isn't mounted,
scanning carries on; run `photoscan sync` later. `prune` frees local space
and only deletes files whose NAS copy matches.

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
