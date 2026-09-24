# Changelog

## 1.0.0

- feat: scan multiple prints at once, cut them into extracts, back up to NAS [`4200243`](https://github.com/RSickenberg/photo-scanner/commit/4200243802790de4a3e6f43266565f8e0931e151)
- feat: record scans in session.json and support any SANE scanner [`6781ef9`](https://github.com/RSickenberg/photo-scanner/commit/6781ef9307859591d4cb044bd306fafb4f0b3544)
- feat: calibrate each session on the empty glass and repair glass dust [`9d68ab2`](https://github.com/RSickenberg/photo-scanner/commit/9d68ab22292dd28b846c25ce214573d1ec2ace76)
- feat(prune): add --force to delete all local files without the NAS [`e9690a6`](https://github.com/RSickenberg/photo-scanner/commit/e9690a69cbc4d48b7c5cb5abe96cd2bbfd715903)
- fix(detect): keep pale Polaroid frames and pale areas on the white lid [`c97f759`](https://github.com/RSickenberg/photo-scanner/commit/c97f75966906abbd583f47464749898a2a6f856a)
- docs(config): add config.toml.example, kept in sync with `photoscan config` by a test [`fbf599d`](https://github.com/RSickenberg/photo-scanner/commit/fbf599d291fe493b763873dc4fc5ee58437cb651)
- ci(deps): add dependabot for uv, npm release tooling and GitHub Actions [`cf94e4a`](https://github.com/RSickenberg/photo-scanner/commit/cf94e4a9777f3e5935edcd3d5aa5feb40ebe257f)
- fix: use pixma's 48-bit colour mode instead of --depth [`9d590c8`](https://github.com/RSickenberg/photo-scanner/commit/9d590c8038d1194db8e8b61353f61eb1d3b4961a)
- chore: track CHANGELOG.md so release-it includes it in the release commit [`2b2cb62`](https://github.com/RSickenberg/photo-scanner/commit/2b2cb623a7d2e012005eed47972011dcbdc4b832)
- ci(tests): run the tests on linux instead of mac-latest [`716cfe0`](https://github.com/RSickenberg/photo-scanner/commit/716cfe09a6836d4e9e849974db49634b9311efdc)
