---
name: new-project
description: >-
  Scaffold a new project from the personal project-template repo
  (RSickenberg/project-template): asks which PHP/JS stack overlay applies,
  runs bootstrap.sh, then seeds CLAUDE.md and DECISIONS.md with the new
  project's specifics. Use when the user says "start a new project", "set
  up a new repo like the others", "bootstrap this from the template", or
  similar — not for adding template files to an already-mature project
  (just run bootstrap.sh directly for that, it's idempotent).
---

# New project

Wraps `project-template`'s `bootstrap.sh` with the questions and follow-up
edits that make the result actually usable, instead of leaving placeholders.

## Steps

1. **Locate the template.** Default to `~/Projects/_templates/project-template`
   if present; otherwise clone `git@github.com:RSickenberg/project-template.git`
   to a scratch location (ask before cloning somewhere permanent).

2. **Ask what's needed** (use AskUserQuestion, don't guess):
   - Target directory for the new project.
   - Stack overlay: `php-frankenphp-symfony`, `php-frankenphp-laravel`,
     `node`, or none (common files only).
   - One-line description of what the project is/does.

3. **Run it:**
   ```bash
   <template-dir>/bootstrap.sh <target-dir> <stack>
   ```
   It only adds missing files — safe even against an existing directory.

4. **Seed `CLAUDE.md`.** Fill in "What this project is" and "Stack" from the
   answers in step 2; leave the rest of the placeholders for the user, don't
   invent conventions that don't exist yet.

5. **Leave `DECISIONS.md` as the template ships it** — empty log, the format
   comment. Don't pre-write speculative entries; the `decisions` skill
   populates it as real choices come up during the work.

6. **Stack-specific follow-up**, only for the overlay actually chosen:
   - `node`: merge `node/package.scripts.json` into `package.json`, delete
     the merged file.
   - `php-frankenphp-symfony` / `php-frankenphp-laravel`: mention that
     `.env`, `compose.yaml` service names/ports, and the `Dockerfile` base
     image versions still need review against the actual project.

7. **Report what was created and what's still a placeholder** — don't claim
   the project is "ready" when `CLAUDE.md` conventions or `.env` are still
   templated.

Do not `git init`, commit, or push on the user's behalf as part of this
skill — creating/pushing a new repository is a separate, explicit
confirmation (see the main session's action-category rules), not implied by
scaffolding files locally.
