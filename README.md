# SmartBet AI — Sports Analysis Platform

A responsive website and FastAPI backend for NBA basketball, NCAA basketball, and football. It includes completed-game entry, team standings/form, head-to-head records, Elo estimates, player-stat leaders, full-game and first-half totals analysis, **persistent SQLite historical records**, leakage-safe training datasets, and model-accuracy tracking.

## Project entry points

- `index.html` — website homepage served by FastAPI.
- `sports_api.py` — main FastAPI application and static website host.
- `sports_history_api.py` — persistent SQLite history and feature endpoints.
- `sports_ml_api.py` — ESPN ingestion, model training, and ML prediction endpoints.
- `render.yaml` — Render deployment configuration.

## Run locally

1. Install Python 3.10 or newer.
2. Install dependencies: `pip install -r requirements.txt`
3. Optional: set `API_FOOTBALL_KEY` as a server environment variable to enable the API-Sports league metadata proxy.
4. Optional: set `SPORTS_DB` to a writable SQLite database path (default `sports.db`). Set `API_KEY` to protect historical bulk imports and prediction logging; send it in the `X-API-Key` header.
5. Start: `uvicorn sports_api:app --reload --host 0.0.0.0 --port 8000`
6. Open the website at `http://localhost:8000` and interactive API documentation at `http://localhost:8000/docs`.

## Main analysis API

- `GET /health` — service status and in-memory counts.
- `POST /games` — add a completed game; it is held in memory for the original analysis endpoints and mirrored into persistent SQLite history.
- `GET /games?sport=nba` — list in-memory game records.
- `GET /sports` — sports represented in in-memory records.
- `GET /standings/{sport}` — standings calculated from in-memory results.
- `GET /teams/{sport}/{team}/form?n=5` — recent form.
- `GET /h2h/{sport}?a=Team+A&b=Team+B` — in-memory head-to-head history.
- `GET /ratings/{sport}` and `GET /predict/{sport}?home=Team+A&away=Team+B` — Elo estimates.
- `GET /analysis/total?...` — full-game or first-half total estimate (first-half scores required for the latter).
- `POST /player-stats` and `GET /leaders/{sport}/{stat}` — player stat ingestion and leaders.
- `GET /api/football/leagues?id=39&season=2026` — secure API-Sports metadata proxy.

## Persistent Sports History API

SQLite database defaults to `sports.db`; records survive application restarts as long as the database file is on persistent storage.

- `POST /history/games/bulk` — import up to 5,000 past results per request; duplicates are skipped.
- `GET /history/games?sport=nba&team=...&season=...` — browse history with optional filters and pagination.
- `GET /history/h2h?sport=nba&a=Team+A&b=Team+B` — persistent head-to-head history.
- `GET /features/{sport}?home=...&away=...&as_of=YYYY-MM-DD` — pre-match feature vector (form, rest, Elo, H2H).
- `GET /dataset/{sport}?min_games=5` — training rows with features computed before each target game's date.
- `POST /history/predictions` — log a model probability against a historical game ID.
- `GET /accuracy/{sport}?model=...` — prediction accuracy and Brier score.
- `GET /history/health` — SQLite record counts and storage status.

### API key for write operations

If `API_KEY` is configured, send `X-API-Key: yourkey` on `POST /history/games/bulk` and `POST /history/predictions`. Read endpoints remain accessible so the website can display public analysis. Do not put the key in frontend JavaScript.

### Leakage prevention

Training features are computed from games dated strictly before the target game's date. All games on the same date are treated as a batch: none of that day's results are used to create features for another game on the same date. This prevents same-day result leakage. The historical dataset includes home-win/draw/away labels and score margin.

## Data and model limitations

- Historical results are persistent in SQLite. The original quick-entry analysis endpoints still maintain their own in-memory cache, which resets on restart; the historical API remains persistent. Bulk-imported rows are available through `/history/*`, `/features/*`, and `/dataset/*`.
- The API does not scrape or invent match data. Import verified results or connect a licensed sports-data provider.
- NBA, NCAA, and football should use consistent sport identifiers (`nba`, `ncaa`, `soccer`) across imported records and requests. Keep each competition's dataset separate.
- The baseline totals model uses historical score distributions, not a trained or validated betting model. Elo estimates are not guaranteed outcomes and do not model injuries, lineups, pace, travel, or bookmaker margin.
- Odds are not generated. Connect a licensed odds provider before calculating expected value.
- The app does not connect to SportyBet, place bets, or guarantee outcomes. Check every market and price manually and bet responsibly.

## Deploy on Render (not GitHub Pages)

The repository includes `index.html` at the project root. GitHub stores the source code; it does not run this project. Because SmartBet AI requires Python/FastAPI (and includes a Node helper), GitHub Pages is not a suitable host. Use Render to run the Python web service. The included `render.yaml` configures that service and starts `uvicorn sports_api:app`. Push the project to GitHub, connect it to Render, and deploy. Add `API_FOOTBALL_KEY` only if available. Add `SPORTS_DB` if you want a custom database path. **Important:** SQLite needs a persistent disk; ephemeral free-service filesystems can be reset on redeploy/restart. For durable hosted history, attach persistent storage or migrate to managed PostgreSQL.

Before public launch, add authentication/rate limits for all data ingestion, backups, automated result settlement, logging, and model back-testing.


## Machine-learning engine (new)

The app now includes `sports_ml_api.py`, which registers ML routes on the existing FastAPI application. It ingests completed scores from ESPN's unofficial public scoreboard, builds time-ordered features from the SQLite history database, trains Logistic Regression and HistGradientBoosting candidates, selects the lower holdout log-loss model, and serves predictions for upcoming fixtures.

Install and run:

```bash
pip install -r requirements.txt
uvicorn sports_api:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` for the website and `http://localhost:8000/docs` for API documentation.

### ML workflow

1. `POST /ml/ingest/nba?days_back=730` (or `ncaam`, `ncaaw`, `wnba`, `epl`, `laliga`, `mls`, `nfl`, `mlb`, `nhl`).
2. `POST /ml/train/nba` to train and validate the model. Training currently requires at least 200 usable historical games and both outcome classes in the chronological validation split.
3. `GET /ml/predict/nba?home=Boston%20Celtics&away=New%20York%20Knicks` for a model estimate.
4. `GET /ml/upcoming/nba?days_ahead=7` for upcoming fixtures with available predictions.
5. `GET /ml/models` to inspect trained model metadata and holdout metrics.

The dashboard includes buttons for importing results, training/validating a model, and loading upcoming predictions. If `API_KEY` is configured, send it as `X-API-Key` for history imports, ML ingestion, and model training. Set `INGEST_SPORTS=nba,ncaam,epl`, `INGEST_INTERVAL_MIN=30`, and optionally `INGEST_RETRAIN=1` to enable periodic background refreshes. Automatic retraining is disabled by default to avoid repeatedly training on every poll.

### Deployment and data persistence

`render.yaml` is configured for a free Render web service. Free Render services have an ephemeral filesystem, so SQLite history and trained model files can be lost on restart, spin-down, or redeploy. For persistent production use, attach a paid persistent disk or migrate SQLite to a managed PostgreSQL database and store model artifacts in durable storage. Render documents that free web services do not support persistent disks and spin down after inactivity. The ESPN scoreboard is unofficial and may change without notice; use a licensed provider for production. The current model estimates home win versus non-home-win; soccer draws are included in non-home-win, and this is not a three-way 1X2 prediction. First-half totals are still handled by the separate historical totals estimator and are not predicted by this ML classifier.

Model outputs are estimates, not guarantees. No automatic betting or bookmaker account integration is included.
