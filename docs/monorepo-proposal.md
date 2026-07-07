# Monorepo Consolidation Proposal

Status: **proposal only - no git operations have been performed.** Per your instruction, this
describes options and a recommendation; nothing here executes until you pick one.

## Current state (verified)

| Location | Git status | History |
|---|---|---|
| `live/` | own repo, remote `github.com/Msalh/mnqu6-live-dashboard.git` | 5 commits, all Sprint-0-era (Pine/dashboard/initial relay). **All Sprint 1-3 work is uncommitted** working-tree changes - it was never committed, so there's no Sprint 1-3 history to lose either way. |
| `frontend/` | own repo, no remote | 1 commit (`create-next-app`'s scaffold commit). Everything from Sprint 2-3 is uncommitted. |
| `docs/` | no repo | Created fresh this session, never committed anywhere. |
| Project root (`C:\Projects\Trading`) | no repo | Also contains `dashboard/`, `data/`, `pine/`, `screenshots/` - the Pine-script/backtest-analysis phase of this project, unrelated to whether Atlas's web platform is a monorepo. |

Two things worth naming plainly: first, because nothing from Sprints 1-3 is committed yet,
"preserving history" mostly concerns five early commits, not months of team activity - the
cost/benefit of a complex rewrite is genuinely low here. Second, the root folder has
occupants (`pine/`, `dashboard/`, `data/`, `screenshots/`) that your monorepo instruction
didn't mention - I'm treating that as an open question below, not assuming an answer.

## Decision 1: does the monorepo include `pine/`, `dashboard/`, `data/`, `screenshots/`?

Your instruction named `live/`, `frontend/`, `docs/` specifically. Two reasonable readings:
- **(a) Atlas-scoped**: the monorepo is exactly those three, living at `C:\Projects\Trading`
  alongside the other folders which stay as plain untracked directories (or their own
  separate concern later). Simplest, matches your instruction literally.
- **(b) Whole-project**: the monorepo also absorbs `pine/` (the strategy source TradingView
  alerts actually come from) and maybe `dashboard/`/`data/` (the Streamlit backtest tool),
  since they're all part of "the trading system" even if not part of the Atlas web platform
  specifically.

**Recommendation: (a).** `pine/` changes independently of the web platform's release cadence
(Pine edits don't need a `live/`+`frontend/` deploy, and vice versa), and `dashboard/`/`data/`
are a separate analysis tool with its own already-working Streamlit-specific setup
(`.claude/launch.json`'s `trade-dashboard` entry). Bundling them in doesn't cost much but
doesn't buy anything either - happy to revisit if you'd rather have one repo for
everything.

## Decision 2: how to consolidate the git history

### Option A - Fresh start (recommended)
`git init` once at the monorepo root. Remove the two nested `.git` directories (`live/.git`,
`frontend/.git`) so they stop being independent repos. Stage everything, one commit
("Consolidate into Atlas monorepo: backend + frontend + docs, Sprints 1-3"). Push to a new
GitHub repo.

- **Preserves**: nothing is deleted - `live/`'s current 5 commits and full file history
  still exist locally in `live/.git` until that directory is actually removed, and a safety
  copy (see below) keeps them recoverable indefinitely. What's lost is *live, browsable*
  history in the new repo - `git log` on the new repo starts from the consolidation commit,
  not from "Initial live entry dashboard."
- **Cost**: low complexity, low risk, fast.
- **Best if**: you don't need `git blame`/`git log` to reach back before this consolidation
  for files under `live/`.

### Option B - Rewrite history to preserve it exactly
Use `git filter-repo` (or two `git subtree split` passes) to rewrite `live/`'s 5 commits so
every path gets a `live/` prefix, do the same trivial rewrite for `frontend/`'s 1 commit,
then merge both rewritten histories into one new repo with `git merge --allow-unrelated-histories`,
and add `docs/` as a fresh commit on top.

- **Preserves**: real, correct, browsable history - `git log --follow live/atlas/main.py`
  keeps working back through the Sprint-0 commits.
- **Cost**: meaningfully more steps, more that can go wrong, needs `git-filter-repo`
  installed (not currently available in this environment - would need to be installed
  first), and the rewritten commits have different hashes than what's currently on
  `github.com/Msalh/mnqu6-live-dashboard` - pushing this anywhere still means a force-push /
  new remote, not a clean continuation.
- **Best if**: those 5 early commits have value to you beyond what's already captured in
  this session's sprint summaries and docs.

### Option C - Keep `live/`'s repo, nest the rest under it
Leave `live/`'s repo exactly as-is (zero rewriting, zero risk to its history) and move
`frontend/` and `docs/` to become subdirectories inside it: `live/frontend/`, `live/docs/`.

- **Preserves**: `live/`'s history perfectly, trivially, with no tooling needed.
- **Cost**: doesn't match "live/ for backend, frontend/ for Next.js, docs/ for
  documentation" as three siblings - under this option `live/` stops meaning "the backend"
  and starts meaning "the repo root," which reads confusingly given the directory is
  literally named `live`. Would probably want to rename `live/` → repo root and `live/atlas/`
  stays as the backend package, i.e. a bigger reshuffle than it first sounds like.
- **Best if**: preserving `live/`'s exact history is more important than the directory
  layout matching your stated `live/` / `frontend/` / `docs/` sibling structure.

## Recommendation
**Option A**, scoped per Decision 1(a) - new root repo containing exactly `live/`,
`frontend/`, `docs/` as siblings, one consolidation commit, pushed to a new GitHub repo
(suggest renaming from `mnqu6-live-dashboard` to something like `atlas-trading-platform`,
since the project has outgrown the old name - your call).

## Safety plan (applies regardless of which option you pick)
Before touching anything:
1. Tag or branch `live/`'s current state (`git tag pre-monorepo-backup` or push a backup
   branch to the existing GitHub remote) so the 5 original commits are recoverable from
   GitHub even after `live/.git` is removed locally.
2. Zip/copy the whole `C:\Projects\Trading` directory as a point-in-time backup before any
   `.git` directory is deleted, independent of git itself.
3. Do the consolidation on a throwaway copy first if you want to sanity-check the result
   before committing to it for real.

## What I need from you to proceed
1. Decision 1: Atlas-scoped monorepo, or whole-project?
2. Decision 2: Option A, B, or C?
3. New GitHub repo name (or reuse/rename the existing one)?
4. Confirmation to actually execute - I will not run any of this without an explicit go-ahead,
   consistent with "do not perform the git history migration yet."
