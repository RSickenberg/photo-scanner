# 2. Organise the archive by Source; put the photo date in metadata, not folder names

Date: 2026-09-24
Status: Accepted

## Context

Sessions were folders named `<scan date>_<label>`. For a family archive, the
scan date is meaningless. What people look for is the physical origin (which
album or box) and when the picture was taken. The archive is browsed both in
Finder / the NAS file browser and in Ugreen Photos, which builds its timeline
from embedded metadata. Photo dates are often approximate, found late, or
never found.

## Decision

- Top-level folders are **Sources** (album, box, envelope), named by their
  slug only: `<output>/<source-slug>/{scans,extracts}/`. A Source spans any
  number of Sessions. Sessions and Calibrations are records of the work, kept
  aside (`_sessions/`, `_calibrations/`).
- The **Photo date** lives in each Extract's metadata (EXIF `DateTimeOriginal`
  plus its real precision in XMP), never in folder or file names. It comes, in
  order of trust, from: a date typed for the Scan, a date read by text
  recognition on the front or Back, the Source's estimate. Otherwise it's
  unknown, and nothing is invented. `photoscan date` corrects it afterwards.

## Consequences

- Dates can change without renaming anything, so a correction doesn't make the
  path-keyed NAS Backup copy files again.
- Chronological browsing depends on Ugreen Photos reading the metadata.
  Tested by the user on 2026-09-24 with the files in `ugreen-test/`: Ugreen
  Photos places a photo by EXIF `DateTimeOriginal` only. It ignores XMP
  `photoshop:DateCreated` (even partial, e.g. `1985-06`) and EXIF `DateTime`.
  With no date at all, it falls back to the file's modification time. So every
  known or estimated Photo date must be written as a full `DateTimeOriginal`,
  with its real precision kept in XMP and in the record; an unknown date
  writes no `DateTimeOriginal`.
- Sessions made before this change (`<date>_<label>/`) aren't migrated.
