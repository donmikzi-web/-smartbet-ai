"""Live scoreboard ingestion and historical ML models for SmartBet AI.

Uses ESPN's public scoreboard endpoint as an unofficial source. Replace
fetch_scoreboard() with a licensed provider for production. Models and SQLite
must be stored on persistent storage when deployed.
"""
from __future__ import annotations
import asyncio
import json
import os
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from fastapi import Depends, HTTPException, Query
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from sports_history_api import Tracker, _history_rows, db, training_dataset, check_key
from sports_api import app

MODEL_DIR = Path(os.getenv("MODEL_DIR", "models"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)
LEAGUES = {
    "nba": ("basketball", "nba"), "wnba": ("basketball", "wnba"),
    "ncaam": ("basketball", "mens-college-basketball"),
    "ncaaw": ("basketball", "womens-college-basketball"),
    "nfl": ("football", "nfl"), "mlb": ("baseball", "mlb"),
    "nhl": ("hockey", "nhl"), "epl": ("soccer", "eng.1"),
    "laliga": ("soccer", "esp.1"), "mls": ("soccer", "usa.1"),
}
NON_FEATURES = {"game_id", "date", "home", "away", "label_result", "label_home_win", "label_margin"}


def fetch_scoreboard(sport: str, dates: str) -> list[dict]:
    if sport not in LEAGUES:
        raise HTTPException(404, f"Unknown sport. Choose from {sorted(LEAGUES)}")
    category, league = LEAGUES[sport]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{category}/{league}/scoreboard?dates={dates}&limit=1000"
    req = urllib.request.Request(url, headers={"User-Agent": "SmartBetAI/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(502, f"ESPN scoreboard request failed: {exc}")
    found = []
    for event in payload.get("events", []):
        try:
            competition = event["competitions"][0]
            teams = {x["homeAway"]: x for x in competition["competitors"]}
            home, away = teams["home"], teams["away"]
            complete = bool(competition["status"]["type"]["completed"])
            found.append({
                "date": event["date"][:10],
                "home": home["team"]["displayName"],
                "away": away["team"]["displayName"],
                "home_score": int(home.get("score") or 0),
                "away_score": int(away.get("score") or 0),
                "completed": complete,
            })
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return found


def ingest(sport: str, days_back: int) -> dict:
    sport = sport.lower()
    if sport not in LEAGUES:
        raise HTTPException(404, f"Unknown sport. Choose from {sorted(LEAGUES)}")
    end = date.today()
    start = end - timedelta(days=days_back)
    cursor = start
    inserted = seen = 0
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=13), end)
        period = f"{cursor:%Y%m%d}-{chunk_end:%Y%m%d}"
        completed = [g for g in fetch_scoreboard(sport, period) if g["completed"]]
        seen += len(completed)
        with db() as con:
            before = con.total_changes
            con.executemany(
                "INSERT OR IGNORE INTO history_games(sport,league,season,date,home,away,home_score,away_score) VALUES(?,?,?,?,?,?,?,?)",
                [(sport, LEAGUES[sport][1], None, g["date"], g["home"], g["away"], g["home_score"], g["away_score"]) for g in completed],
            )
            inserted += con.total_changes - before
        cursor = chunk_end + timedelta(days=1)
    return {"sport": sport, "completed_games_seen": seen, "new_games": inserted, "source": "ESPN public scoreboard"}


@app.post("/ml/ingest/{sport}", dependencies=[Depends(check_key)])
def ingest_endpoint(sport: str, days_back: int = Query(365, ge=1, le=3650)):
    return ingest(sport, days_back)


def _models():
    return {
        "logistic": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=1000, class_weight="balanced")),
        "gradient_boosting": make_pipeline(SimpleImputer(strategy="median"), HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=160, l2_regularization=1.0, random_state=7)),
    }


@app.post("/ml/train/{sport}", dependencies=[Depends(check_key)])
def train(sport: str):
    sport = sport.lower()
    data = training_dataset(sport, None, 3, 50000)
    rows = data["rows"]
    if len(rows) < 200:
        raise HTTPException(400, f"Only {len(rows)} usable games for {sport}; at least 200 are required. Run POST /ml/ingest/{sport}?days_back=730 and try again.")
    columns = [key for key in rows[0] if key not in NON_FEATURES]
    X = np.asarray([[np.nan if row.get(col) is None else row[col] for col in columns] for row in rows], dtype=float)
    y = np.asarray([row["label_home_win"] for row in rows], dtype=int)
    split = int(len(rows) * 0.8)
    X_train, X_test, y_train, y_test = X[:split], X[split:], y[:split], y[split:]
    if len(set(y_train)) < 2 or len(set(y_test)) < 2:
        raise HTTPException(400, "The time-ordered training/validation split needs both home-win and non-home-win examples. Import a broader history.")
    report, winner, best_loss = {}, None, float("inf")
    for name, estimator in _models().items():
        estimator.fit(X_train, y_train)
        probabilities = np.clip(estimator.predict_proba(X_test)[:, 1], 0.001, 0.999)
        loss = log_loss(y_test, probabilities, labels=[0, 1])
        report[name] = {"log_loss": round(float(loss), 4), "brier": round(float(brier_score_loss(y_test, probabilities)), 4), "accuracy": round(float(accuracy_score(y_test, probabilities >= 0.5)), 4)}
        if loss < best_loss:
            winner, best_loss = name, loss
    baseline = np.full(len(y_test), float(y_train.mean()))
    report["baseline"] = {"log_loss": round(float(log_loss(y_test, baseline, labels=[0, 1])), 4), "accuracy": round(float(max(y_test.mean(), 1-y_test.mean())), 4)}
    final_model = _models()[winner].fit(X, y)
    bundle = {"model": final_model, "columns": columns, "name": winner, "trained_on": len(rows), "holdout_games": len(y_test), "holdout": report, "trained_at": date.today().isoformat()}
    joblib.dump(bundle, MODEL_DIR / f"{sport}.joblib")
    return {"sport": sport, "chosen_model": winner, "trained_on": len(rows), "holdout_games": len(y_test), "holdout_results": report}


@app.get("/ml/models")
def list_models():
    result = {}
    for path in MODEL_DIR.glob("*.joblib"):
        try:
            bundle = joblib.load(path)
            result[path.stem] = {"model": bundle["name"], "trained_on": bundle["trained_on"], "trained_at": bundle.get("trained_at"), "holdout": bundle["holdout"]}
        except Exception:
            result[path.stem] = {"status": "model file unreadable"}
    return result


def _load_model(sport: str):
    path = MODEL_DIR / f"{sport}.joblib"
    if not path.exists():
        raise HTTPException(404, f"No trained model for {sport}. Run POST /ml/train/{sport} first.")
    return joblib.load(path)


def _tracker(sport: str, as_of: Optional[date] = None):
    """Build features only from games dated strictly before the target day."""
    tracker = Tracker()
    with db() as con:
        rows = _history_rows(con, sport, as_of.isoformat() if as_of else None)
        for row in rows:
            tracker.update(row)
    return tracker


def _predict(bundle, tracker, home: str, away: str, target: date):
    features = tracker.features(home, away, target)
    values = np.asarray([[np.nan if features.get(col) is None else features.get(col, np.nan) for col in bundle["columns"]]], dtype=float)
    probability = float(np.clip(bundle["model"].predict_proba(values)[0, 1], 0.001, 0.999))
    return probability, features


@app.get("/ml/predict/{sport}")
def ml_predict(sport: str, home: str, away: str):
    sport = sport.lower()
    if home.strip().casefold() == away.strip().casefold():
        raise HTTPException(400, "Home and away teams must be different")
    target_date = date.today()
    bundle, tracker = _load_model(sport), _tracker(sport, target_date)
    for team in (home, away):
        if not tracker.recent.get(team):
            raise HTTPException(404, f"No historical records for '{team}'. Check the team name in /history/games.")
    probability, features = _predict(bundle, tracker, home, away, target_date)
    return {"sport": sport, "home": home, "away": away, "home_win_prob": round(probability, 4), "away_or_draw_prob": round(1-probability, 4), "model": bundle["name"], "trained_on": bundle["trained_on"], "key_factors": {key: features.get(key) for key in ("elo_diff", "home_win_rate_5", "away_win_rate_5", "h2h_home_win_rate")}, "warning": "Model estimate, not a guaranteed result. Draws are grouped with non-home wins."}


@app.get("/ml/upcoming/{sport}")
def upcoming(sport: str, days_ahead: int = Query(3, ge=1, le=14)):
    sport = sport.lower()
    bundle = _load_model(sport)
    today = date.today()
    end = today + timedelta(days=days_ahead)
    fixtures = fetch_scoreboard(sport, f"{today:%Y%m%d}-{end:%Y%m%d}")
    output = []
    for game in fixtures:
        if game["completed"]:
            continue
        if not tracker.recent.get(game["home"]) or not tracker.recent.get(game["away"]):
            output.append({"date": game["date"], "home": game["home"], "away": game["away"], "home_win_prob": None, "note": "Insufficient history for one or both teams"})
            continue
        fixture_date = date.fromisoformat(game["date"])
        tracker = _tracker(sport, fixture_date)
        probability, _ = _predict(bundle, tracker, game["home"], game["away"], fixture_date)
        output.append({"date": game["date"], "home": game["home"], "away": game["away"], "home_win_prob": round(probability, 4), "model": bundle["name"]})
    return output


@app.on_event("startup")
async def start_auto_ingest():
    sports = [item.strip() for item in os.getenv("INGEST_SPORTS", "").lower().split(",") if item.strip()]
    try:
        minutes = int(os.getenv("INGEST_INTERVAL_MIN", "0"))
    except ValueError:
        minutes = 0
    if not sports or minutes <= 0:
        return
    async def refresh_loop():
        while True:
            for item in sports:
                try:
                    await asyncio.to_thread(ingest, item, 3)
                    if os.getenv("INGEST_RETRAIN", "0") == "1":
                        await asyncio.to_thread(train, item)
                except Exception as exc:
                    print(f"SmartBet auto-ingest for {item} failed: {exc}")
            await asyncio.sleep(minutes * 60)
    asyncio.create_task(refresh_loop())
