# EFL Project Overview

## Architecture
- **Backend:** Python/Flask API (`efl2024_api/`) — connects to MongoDB Atlas
- **Production API:** https://continuous-jannelle-auctionfantasy-953e5c9b.koyeb.app
- **Frontend:** React/Vite (`~/Documents/efl2025_first/`) — fetches data via Flask API
- **DB:** MongoDB Atlas, active DB is `afc2026` (set in `config.py` line 17)

## DB Skills (slash commands)
- `/db-players` — list all players from `afc2026.players`
- `/db-leagues` — all leagues with team counts
- `/db-teams [league name]` — teams, optionally filtered by league
- `/db-squad <team name>` — full squad for a team
- `/db-standings [league name]` — leaderboard
- `/db-player-search <name>` — find a player across all leagues
- `/db-global` — current match state and deadlines

## Key Backend Files
- `config.py` — DB connection, active DB name, shared constants (`DRAFT_LEAGUE_ID`, `AUCTION_LEAGUE_ID`)
- `main.py` — league/team/user CRUD, `/create_league`, `/add_team`, `/join_league`
- `draftapi.py` — draft pick/drop logic
- `add_drop.py` — auction add/drop
- `transfers.py` — auction transfers and releases
- `waivers.py` — weekly waiver processing
- `liveupdates.py` — point updates from ESPN API

## Key Frontend Files (efl2025_first/src/)
- `Players.jsx` — player browser grid
- `Teams.jsx` — team rosters grouped by owner
- `Auction.jsx` / `Auction_New.jsx` — auction UI
- `WaiverView.jsx` / `WaiverSystem.jsx` — waiver preferences
- `ManageTeam.jsx` — owner team management

## DB Collections (afc2026)
- `players` — master player list (249 players, set once per season)
- `leagueplayers` — per-league copy of players + status/points/ownerTeam
- `teams` — owner teams per league
- `leagues` — league config and admins
- `users` — user accounts
- `userteams` — user → team mapping per league
- `teamwaivers` — waiver history per team
- `global_data` — match state and deadlines

## Versioning
- Version defined in `pyproject.toml` (`[project].version`)
- `GET /version` returns current version from prod
- Patch version auto-bumps on every `git push` via `.git/hooks/pre-push`
- On a fresh clone, run `sh scripts/install-hooks.sh` to install the hook
- Python runtime pinned to 3.13 via `.python-version`

## Season Setup Checklist (for 2026)
1. `players` collection already populated in `afc2026`
2. Create EFL Draft + EFL Auction leagues via `POST /create_league`
3. Update `DRAFT_LEAGUE_ID` and `AUCTION_LEAGUE_ID` in `config.py`
4. Add teams via `POST /add_team`
5. Owners join via `POST /join_league` + `POST /teams/join`
