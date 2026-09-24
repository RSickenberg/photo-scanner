# Changelog

## [v2.0.2](https://github.com/RSickenberg/photo-scanner/compare/v2.0.1...v2.0.2)

- fix: keep printed captions, pair white Backs, trust only confident OCR [`828658f`](https://github.com/RSickenberg/photo-scanner/commit/828658fbf67530ef267af49519e32b177244210c)

## [v2.0.1](https://github.com/RSickenberg/photo-scanner/compare/v2.0.0...v2.0.1) (2026-09-24)

- fix(detect): don't join Prints when the lid shades differently than at calibration [`c920949`](https://github.com/RSickenberg/photo-scanner/commit/c9209499d1c6d5136d3acc330fa9374ced0fcb8f)
- chore(release): 2.0.1 [`b416b7a`](https://github.com/RSickenberg/photo-scanner/commit/b416b7ad4e506bf3d14bf9d7c649e5f33fbc9f8a)

## [v2.0.0](https://github.com/RSickenberg/photo-scanner/compare/v1.0.0...v2.0.0) (2026-09-24)

- build(deps): bump astral-sh/setup-uv from 6 to 7 in the actions group [`#1`](https://github.com/RSickenberg/photo-scanner/pull/1)
- feat!: organise the archive by Source, date photos, scan and read Backs [`d956717`](https://github.com/RSickenberg/photo-scanner/commit/d9567175b6701f82c838c3e1e0dae467a1a8e9d8)
- feat(backs): scan Backs at back_dpi (300 by default) [`448cd3e`](https://github.com/RSickenberg/photo-scanner/commit/448cd3e73b15dbf2a4218d55c707e39a9ffe3c2e)
- build(uv): bumped deps to current version [`13bc152`](https://github.com/RSickenberg/photo-scanner/commit/13bc152b93cb8b2358a695f316257236f1d5fa17)
- chore(release): 2.0.0 [`22ed69c`](https://github.com/RSickenberg/photo-scanner/commit/22ed69c5efb15d78031b5e9a4236632e5669500b)
- docs(pyproject): tweaked description to fit latest changes [`9128f2e`](https://github.com/RSickenberg/photo-scanner/commit/9128f2e049a4f956691e12928c6319bc93a3b7cd)

## v1.0.0 (2026-09-24)

- feat: scan multiple prints at once, cut them into extracts, back up to NAS [`4200243`](https://github.com/RSickenberg/photo-scanner/commit/4200243802790de4a3e6f43266565f8e0931e151)
- feat: record scans in session.json and support any SANE scanner [`6781ef9`](https://github.com/RSickenberg/photo-scanner/commit/6781ef9307859591d4cb044bd306fafb4f0b3544)
- feat: calibrate each session on the empty glass and repair glass dust [`9d68ab2`](https://github.com/RSickenberg/photo-scanner/commit/9d68ab22292dd28b846c25ce214573d1ec2ace76)
- feat(prune): add --force to delete all local files without the NAS [`e9690a6`](https://github.com/RSickenberg/photo-scanner/commit/e9690a69cbc4d48b7c5cb5abe96cd2bbfd715903)
- fix(detect): keep pale Polaroid frames and pale areas on the white lid [`c97f759`](https://github.com/RSickenberg/photo-scanner/commit/c97f75966906abbd583f47464749898a2a6f856a)
- docs(config): add config.toml.example, kept in sync with `photoscan config` by a test [`fbf599d`](https://github.com/RSickenberg/photo-scanner/commit/fbf599d291fe493b763873dc4fc5ee58437cb651)
- ci(deps): add dependabot for uv, npm release tooling and GitHub Actions [`cf94e4a`](https://github.com/RSickenberg/photo-scanner/commit/cf94e4a9777f3e5935edcd3d5aa5feb40ebe257f)
- chore(release): 1.0.0 [`909bb4a`](https://github.com/RSickenberg/photo-scanner/commit/909bb4a0f43686216a07f584013bb574ec1daf16)
- fix: use pixma's 48-bit colour mode instead of --depth [`9d590c8`](https://github.com/RSickenberg/photo-scanner/commit/9d590c8038d1194db8e8b61353f61eb1d3b4961a)
- chore: track CHANGELOG.md so release-it includes it in the release commit [`2b2cb62`](https://github.com/RSickenberg/photo-scanner/commit/2b2cb623a7d2e012005eed47972011dcbdc4b832)
- ci(tests): run the tests on linux instead of mac-latest [`716cfe0`](https://github.com/RSickenberg/photo-scanner/commit/716cfe09a6836d4e9e849974db49634b9311efdc)
