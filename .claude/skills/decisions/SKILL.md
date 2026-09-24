---
name: decisions
description: >-
  Maintain this project's DECISIONS.md: a decision-centric discipline where
  the user arbitrates every non-trivial technical or architectural choice
  instead of Claude deciding silently. Use whenever a choice is being made
  that isn't fully dictated by the existing code (a library, a data model,
  an infrastructure pattern, a trade-off between two valid approaches) —
  proactively, not only when the user says "log this decision" or
  "decisions.md". Scoped down from a full spec-writing process (see
  yannlugrin/claude's `specify` skill for that heavier workflow): this is
  for logging decisions made *during* ordinary engineering work on an
  existing project, not for producing a requirements document upfront.
---

# Decisions

`DECISIONS.md`, at the repository root, is the record of *why* the project
is shaped the way it is. The code shows what was built; this file is the
only place "why not the obvious alternative" survives.

## Roles

- **The user is the sole arbiter.** Present options with a recommendation
  and reasoning; they rule; only then implement. Don't silently pick between
  two reasonable approaches — surface the choice.
- **You hold the log.** Draft entries, keep them accurate, flag when a new
  fact contradicts a logged premise.

## When an entry is warranted

Not every choice needs a `D-NNN` entry — most decisions are adequately
explained by the code and a good commit message. Write one only for:

- **Foundational decisions** — framework/library choice, data model shape,
  auth strategy, deployment topology, anything many later decisions build on.
- **Decisions whose justification would otherwise be lost** — a rejected
  alternative worth remembering, a deliberate deviation from the obvious
  approach, a constraint that isn't visible in the code itself.
- **Anything the user explicitly asks to track.**

Trivial or fully code-evident choices (variable naming, which of two
equivalent utility functions to call) don't need an entry — don't pad the
log.

## Entry format

```markdown
## D-NNN (YYYY-MM-DD) — short title

- **Status:** open | decided | reaffirmed (date) | reopened | superseded by D-MMM
- **Foundational:** yes | no
- **Decision:** what was decided (or the options, while open)
- **Why:** the reasoning, including alternatives rejected and why
- **Premises:** the facts and context this decision depends on
```

Example:

```markdown
## D-004 (2026-08-05) — Redis for the Messenger transport

- **Status:** decided
- **Foundational:** no
- **Decision:** use Redis (not a DB-backed transport) for async messages
- **Why:** already running Redis for cache; avoids adding a queue table and
  its migration/locking concerns; DB transport rejected as one more moving
  part for no benefit at this scale
- **Premises:** message volume is low (no need for Redis Cluster); Redis is
  already a hard dependency of this project
```

Numbers matter: an entry written with concrete premises carries its own
expiry condition — the day "message volume is low" stops being true, the
entry is visibly stale and worth reopening, instead of quietly outliving its
reasoning.

## Rules

- **Premises are concrete, not vague.** "No web app exists yet", not "early
  stage". They're what makes a decision auditable later.
- `D-NNN` entries are **never deleted** — superseded or reopened, with the
  date of reaffirmation recorded (staleness is measured from the last
  affirmation, not creation).
- **Open questions** live as a one-line list at the top of the file, deleted
  once ruled (git history keeps them) — promoted to a full entry only if
  they match one of the three kinds above.
- When new work touches a logged premise and makes it look false, say so
  immediately, naming the entry (`this touches D-004's premise that message
  volume is low`) — don't wait to be asked.
- Don't relitigate a decided entry without a concrete new fact. Disagreeing
  in general isn't grounds to reopen it.
- Facts cited in a premise should be verified (docs, actual behavior), not
  assumed from training data, when there's real doubt.

## Workflow

1. When a qualifying choice comes up mid-task, stop and present it: the
   options, your recommendation, why. Batch related questions.
2. On the user's ruling, write/update the entry in `DECISIONS.md` in the
   same commit as the change it justifies — a commit where the log asserts
   something the code contradicts is a state nobody should read.
3. If `DECISIONS.md` doesn't exist yet in the project, create it from the
   template in this template repo's `common/DECISIONS.md` rather than
   inventing a new format.
