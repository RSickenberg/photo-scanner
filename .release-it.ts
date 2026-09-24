import type {Config} from 'release-it';

// Usage: `npm run release` (script: "release": "dotenv release-it")
//
// Notes from past projects:
// - Add `--remote release` to the two commands below if this repo's GitHub
//   remote isn't named "origin" (e.g. a private/second remote setup).
// - If you version a non-package.json file (e.g. a VERSION file consumed by
//   a non-JS app), add the `@release-it/bumper` plugin block at the bottom.

export default {
  git: {
    commit: true,
    tag: true,
    push: true,
    commitMessage: 'chore(release): ${version}',
    tagName: 'v${version}',
    requireCleanWorkingDir: false,
    requireBranch: 'main',
    requireUpstream: true,
    pushArgs: ['--follow-tags'],
    pushRepo: 'origin',
    tagArgs: ['-s'],
  },
  github: {
    release: true,
    draft: true,
    releaseNotes:
      'npx auto-changelog --commit-limit false --stdout --unreleased-only -v ${version} --template https://raw.githubusercontent.com/release-it/release-it/main/templates/keepachangelog.hbs',
  },
  hooks: {
    'after:bump':
      'npx auto-changelog -p --commit-limit false -u --template https://raw.githubusercontent.com/release-it/release-it/main/templates/keepachangelog.hbs',
  },
  // VERSION is what the Python package reads (pyproject.toml > tool.hatch.version).
  plugins: {
    '@release-it/bumper': {
      in: 'VERSION',
      out: 'VERSION',
      consumeWholeFile: true,
    },
  },
} satisfies Config;
