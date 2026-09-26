# Changelog

## [v2.3.0](https://github.com/RSickenberg/photo-scanner/compare/v2.2.0...v2.3.0)

- feat(storage): smaller TIFFs, slimmer calibrations, and `photoscan compact` [`bf607da`](https://github.com/RSickenberg/photo-scanner/commit/bf607da5cfdbf05e4ead9ff0c1530cf3214579e9)

## [v2.2.0](https://github.com/RSickenberg/photo-scanner/compare/v2.1.1...v2.2.0) (2026-09-26)

- feat(backup): progress bars for sync and prune [`09cd834`](https://github.com/RSickenberg/photo-scanner/commit/09cd8342e3f49e7593bae15c6b70e26508955fb1)
- chore(release): 2.2.0 [`692ca47`](https://github.com/RSickenberg/photo-scanner/commit/692ca47f218316a34cde6ae2c1ae20608d5e4dc6)

## [v2.1.1](https://github.com/RSickenberg/photo-scanner/compare/v2.1.0...v2.1.1) (2026-09-25)

- fix(backs): a Print left face up or taken off the glass gets no Back [`1597daa`](https://github.com/RSickenberg/photo-scanner/commit/1597daad4619c1a93d019044140663be2548931c)
- fix(detect): don't take a photo's colour for the lid when Prints cover the glass edges [`e8693e5`](https://github.com/RSickenberg/photo-scanner/commit/e8693e56759f9b54969e2f2578bffd89bca2a9c9)
- chore(release): 2.1.1 [`0459893`](https://github.com/RSickenberg/photo-scanner/commit/045989374f0c25d9b8fa8ba5258464035bacb631)

## [v2.1.0](https://github.com/RSickenberg/photo-scanner/compare/v2.0.3...v2.1.0) (2026-09-24)

- feat(session): d dates the latest Scan, never over hand or Back dates [`7fad99a`](https://github.com/RSickenberg/photo-scanner/commit/7fad99a9c3466bbe3e9b61481806b8f5dea1de95)
- refactor: simpler archive, backup and command line [`182b091`](https://github.com/RSickenberg/photo-scanner/commit/182b091056a81dd652bdd5880c429858cc0e6ad2)
- fix: don't create a Source on a typo; reject config values of the wrong kind [`62bfa61`](https://github.com/RSickenberg/photo-scanner/commit/62bfa61d5bb69ba12ce63d6ea404e59e9a3c50c8)
- refactor(detect): Region methods, one caption code path, shared helpers [`27a0043`](https://github.com/RSickenberg/photo-scanner/commit/27a0043ca442654bcfc5adf7422045663b7dc5a0)
- chore(release): 2.1.0 [`0619bd7`](https://github.com/RSickenberg/photo-scanner/commit/0619bd7dc0eabbe7bf3fdf124cf6ff7bf75b7add)

## [v2.0.3](https://github.com/RSickenberg/photo-scanner/compare/v2.0.2...v2.0.3) (2026-09-24)

- fix(detect): split Prints joined across a partly bridged gap [`f5541a1`](https://github.com/RSickenberg/photo-scanner/commit/f5541a1df303e073d3d6192c55d437377eda6631)
- fix(detect): a caption between two Prints belongs to the nearest one only [`87eb42c`](https://github.com/RSickenberg/photo-scanner/commit/87eb42c0cfc4a544654005e84c2f68e76fc020d4)
- feat(backs): keep the whole Back Scan as JPEG [`460812f`](https://github.com/RSickenberg/photo-scanner/commit/460812fb1c9ca9454b576614dce4204e7dd533ee)
- chore(release): 2.0.3 [`2500588`](https://github.com/RSickenberg/photo-scanner/commit/2500588fe42291d7e5d7b36f541a68f02ee417cc)

## [v2.0.2](https://github.com/RSickenberg/photo-scanner/compare/v2.0.1...v2.0.2) (2026-09-24)

- fix: keep printed captions, pair white Backs, trust only confident OCR [`828658f`](https://github.com/RSickenberg/photo-scanner/commit/828658fbf67530ef267af49519e32b177244210c)
- chore(release): 2.0.2 [`c854337`](https://github.com/RSickenberg/photo-scanner/commit/c854337efb2880fe4bddc42eab9737bfc9a9e572)

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
