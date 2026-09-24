# Context

Glossary for photo-scanner: digitising and backing up old family photos by
scanning several at once and cutting each one out into its own file.

## Terms

**Print**
A physical family photo placed on the scanner glass. Several Prints go on the
glass at once. Never call this a "picture" or "photo" in code or docs: those
words are ambiguous between the Print and the files made from it.

**Scan**
One pass of the scanner: a single image of the whole glass, containing zero or
more Prints. Every Scan is kept, uncut, so it can be re-cut later.

**Extract**
One Print cut out of a Scan, straightened, and saved as its own file. One Scan
yields one Extract per Print detected on it. Each Extract has a lossless
**master** (archive copy) and a **photo** (the copy people browse).

**Session**
One sitting in which many Scans are made in a row, possibly for several
Sources. It is a record of the work (when, which Calibrations, which Scans),
not a way of organising the archive: that is the Source.

**Source**
The physical origin of a set of Prints: an album, a box, an envelope (e.g.
"Album Grand-mère 1970s"). The archive is organised by Source, mirroring the
physical collection, so any Extract leads back to its original Print. A
Source can span several Sessions, and one Session can cover several Sources.
Scan order within a Source is its order (album page order).

**Label**
Superseded by **Source** (2026-09-24): Sessions used to carry a single
free-text Label that named their folder. Kept here because Sessions scanned
before Sources existed still have one.

**Photo date**
When a Print's picture was taken, as far as it is known: a day, a month, a
year, a decade, or unknown, possibly approximate ("ca. 1975"). Distinct from
the **scan date** (when it was digitised). The photo date orders the archive
in time; the scan date is only a record of the work.

**Back**
The reverse side of a Print. It often carries a machine-printed date or lab
stamp, sometimes handwriting.

**Calibration**
A Scan of the empty glass (lid closed or black cloth laid) made at the start
of a Session, or again mid-Session. It is the reference for what "background"
looks like, and where the specks are. Later Scans in the Session are compared
against it.

**Glass dust**
Specks lying on the scanner glass. They show at the same place and with the
same shape on every Scan, over Prints too, and are repaired in Extracts.
Distinct from **lint on the lid**, which also appears in a Calibration but
ends up behind the Print and never shows on it, so it is never repaired.
Dust on the Prints themselves is out of scope.

**Backup**
The copy of a Session's Scans and Extracts on the NAS, which is the
long-term home of the archive.
