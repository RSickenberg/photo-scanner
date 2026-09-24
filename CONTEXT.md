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
yields one Extract per Print detected on it.

**Session**
One sitting in which many Scans are made in a row under a single **Label**.
A Session is the unit of organisation on disk.

**Label**
Free-text name given to a Session by the user (e.g. "Grandma album 1970s").
It names the Session's folder and files and is written into each Extract's
metadata.

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
