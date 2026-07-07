# Atlas Trading Platform

AI-assisted futures trading platform: a FastAPI backend (`live/`) that receives
TradingView webhooks, tracks the full trade lifecycle, relays orders to PickMyTrade, and
serves a versioned REST + SSE API; and a Next.js frontend (`frontend/`) consuming it.

This repository was consolidated from two previously-separate repos (`live/` and
`frontend/`, each with their own git history) into one root repo starting at the commit
that added this file - see [`docs/monorepo-proposal.md`](docs/monorepo-proposal.md) for
the consolidation decision and rationale, and [`docs/`](docs/) generally for the
sprint-by-sprint architecture record.

## Layout
- [`live/`](live/README.md) - backend (FastAPI, PostgreSQL, SSE)
- [`frontend/`](frontend/README.md) - frontend (Next.js, TypeScript, Tailwind, Recharts)
- [`docs/`](docs/) - architecture decisions, API contracts, and deployment checklists, one
  folder per sprint

This repo is intentionally scoped to those three directories only - the Pine Script
strategy source, the standalone backtest-analysis dashboard, and raw backtest data live
elsewhere in this project folder but are not part of this repository (see
`docs/monorepo-proposal.md`, Decision 1).

## Getting started
See `live/README.md` and `frontend/README.md` for setup, environment variables, running
tests, and local development (including a seeded in-memory dev server that needs no
database - `live/scripts/dev_seed_server.py`).
