"""Persistent historical records and point-in-time feature API for SmartBet AI.

SQLite-backed history, leakage-safe training datasets, and model evaluation.
Set SPORTS_DB to choose the database file. If API_KEY is set, send X-API-Key
when importing games or logging predictions.
"""
import os
import sqlite3
from pathlib import Path
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

DB_PATH = os.getenv("SPORTS_DB", "sports.db")
Path(DB_PATH).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
API_KEY = os.getenv("API_KEY")
router = APIRouter(tags=["Historical data and model evaluation"])


def check_key(x_api_key: Optional[str] = Header(None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")


@contextmanager
def db():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys=ON")
        yield con
        con.commit()
    finally:
        con.close()


with db() as con:
    con.executescript("""
    CREATE TABLE IF NOT EXISTS history_games(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sport TEXT NOT NULL, league TEXT, season TEXT, date TEXT NOT NULL,
        home TEXT NOT NULL, away TEXT NOT NULL,
        home_score INTEGER NOT NULL, away_score INTEGER NOT NULL,
        UNIQUE(sport, date, home, away));
    CREATE INDEX IF NOT EXISTS ix_history_games_sport_date
        ON history_games(sport, date, id);
    CREATE TABLE IF NOT EXISTS history_predictions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER NOT NULL REFERENCES history_games(id),
        model TEXT NOT NULL, home_win_prob REAL NOT NULL,
        created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS ix_history_predictions_game
        ON history_predictions(game_id, model);
    """)


class HistoricalGameIn(BaseModel):
    sport: str = Field(min_length=2, max_length=30)
    date: date
    home: str = Field(min_length=1, max_length=100)
    away: str = Field(min_length=1, max_length=100)
    home_score: int = Field(ge=0)
    away_score: int = Field(ge=0)
    season: Optional[str] = None
    league: Optional[str] = None

    @model_validator(mode="after")
    def validate_teams(self):
        if self.home.strip().casefold() == self.away.strip().casefold():
            raise ValueError("Home and away teams must be different")
        return self


class HistoricalPredictionIn(BaseModel):
    game_id: int
    model: str = Field(min_length=1, max_length=100)
    home_win_prob: float = Field(ge=0, le=1)


class Tracker:
    """Build team features from results already played before a target date."""
    def __init__(self, k: float = 20, home_adv: float = 60):
        self.k, self.home_adv = k, home_adv
        self.elo = defaultdict(lambda: 1500.0)
        self.recent = defaultdict(list)  # (win, scored, conceded)
        self.last_played: dict[str, date] = {}
        self.h2h_wins = defaultdict(lambda: defaultdict(float))
        self.h2h_n = defaultdict(int)

    def _form(self, team: str, n: int):
        records = self.recent[team][-n:]
        if not records:
            return None, None, None
        return (round(sum(x[0] for x in records) / len(records), 3),
                round(sum(x[1] for x in records) / len(records), 2),
                round(sum(x[2] for x in records) / len(records), 2))

    def features(self, home: str, away: str, target_date: date) -> dict:
        result = {}
        for side, team in (("home", home), ("away", away)):
            for n in (5, 10):
                win_rate, scored, conceded = self._form(team, n)
                result[f"{side}_win_rate_{n}"] = win_rate
                if n == 10:
                    result[f"{side}_avg_scored_10"] = scored
                    result[f"{side}_avg_conceded_10"] = conceded
            last = self.last_played.get(team)
            result[f"{side}_rest_days"] = (target_date - last).days if last else None
            result[f"{side}_games_played"] = len(self.recent[team])
        result["home_elo"] = round(self.elo[home], 1)
        result["away_elo"] = round(self.elo[away], 1)
        result["elo_diff"] = round(self.elo[home] - self.elo[away], 1)
        key = tuple(sorted((home, away), key=str.casefold))
        count = self.h2h_n[key]
        result["h2h_games"] = count
        result["h2h_home_win_rate"] = (
            round(self.h2h_wins[key][home] / count, 3) if count else None)
        return result

    def update(self, game):
        home, away = game["home"], game["away"]
        hs, aws = game["home_score"], game["away_score"]
        outcome = 1.0 if hs > aws else 0.5 if hs == aws else 0.0
        expected = 1 / (1 + 10 ** ((self.elo[away] - self.elo[home] - self.home_adv) / 400))
        self.elo[home] += self.k * (outcome - expected)
        self.elo[away] -= self.k * (outcome - expected)
        self.recent[home].append((outcome, hs, aws))
        self.recent[away].append((1 - outcome, aws, hs))
        played = date.fromisoformat(game["date"])
        self.last_played[home] = self.last_played[away] = played
        key = tuple(sorted((home, away), key=str.casefold))
        self.h2h_n[key] += 1
        self.h2h_wins[key][home] += outcome
        self.h2h_wins[key][away] += 1 - outcome


def _history_rows(con, sport: str, before: Optional[str] = None):
    sql = "SELECT * FROM history_games WHERE sport=?"
    params = [sport.lower()]
    if before:
        sql += " AND date<?"
        params.append(before)
    return con.execute(sql + " ORDER BY date, id", params).fetchall()


@router.post("/history/games/bulk", status_code=201, dependencies=[Depends(check_key)])
def bulk_import(games: list[HistoricalGameIn]):
    """Import past results; duplicate sport/date/home/away rows are skipped."""
    if len(games) > 5000:
        raise HTTPException(413, "Maximum 5,000 games per import")
    with db() as con:
        before = con.total_changes
        con.executemany(
            "INSERT OR IGNORE INTO history_games(sport,league,season,date,home,away,home_score,away_score) VALUES(?,?,?,?,?,?,?,?)",
            [(g.sport.strip().lower(), g.league, g.season, g.date.isoformat(),
              g.home.strip(), g.away.strip(), g.home_score, g.away_score) for g in games])
        inserted = con.total_changes - before
    return {"received": len(games), "inserted": inserted, "duplicates_skipped": len(games) - inserted}


@router.get("/history/games")
def history(sport: str, team: Optional[str] = None, season: Optional[str] = None,
            date_from: Optional[date] = None, date_to: Optional[date] = None,
            limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    sql, params = "SELECT * FROM history_games WHERE sport=?", [sport.lower()]
    if team:
        sql += " AND (home=? OR away=?)"; params += [team, team]
    if season:
        sql += " AND season=?"; params.append(season)
    if date_from:
        sql += " AND date>=?"; params.append(date_from.isoformat())
    if date_to:
        sql += " AND date<=?"; params.append(date_to.isoformat())
    sql += " ORDER BY date DESC,id DESC LIMIT ? OFFSET ?"; params += [limit, offset]
    with db() as con:
        return [dict(row) for row in con.execute(sql, params)]


@router.get("/history/h2h")
def historical_h2h(sport: str, a: str, b: str, limit: int = Query(20, ge=1, le=200)):
    with db() as con:
        rows = con.execute(
            "SELECT * FROM history_games WHERE sport=? AND ((home=? AND away=?) OR (home=? AND away=?)) ORDER BY date DESC,id DESC LIMIT ?",
            (sport.lower(), a, b, b, a, limit)).fetchall()
    wins = {a: 0, b: 0, "draws": 0}
    for row in rows:
        if row["home_score"] == row["away_score"]:
            wins["draws"] += 1
        else:
            winner = row["home"] if row["home_score"] > row["away_score"] else row["away"]
            wins[winner] += 1
    return {"games": len(rows), "record": wins, "history": [dict(row) for row in rows]}


@router.get("/features/{sport}")
def matchup_features(sport: str, home: str, away: str, as_of: Optional[date] = None):
    target = as_of or date.today()
    tracker = Tracker()
    with db() as con:
        for row in _history_rows(con, sport, target.isoformat()):
            tracker.update(row)
    return {"sport": sport.lower(), "home": home, "away": away,
            "as_of": target.isoformat(), "features": tracker.features(home, away, target),
            "data_cutoff": "strictly_before_as_of_date"}


@router.get("/dataset/{sport}")
def training_dataset(sport: str, date_from: Optional[date] = None,
                     min_games: int = Query(5, ge=0),
                     limit: int = Query(5000, ge=1, le=50000)):
    """Generate features before each game; games on the same date are batched to prevent leakage."""
    tracker, output = Tracker(), []
    with db() as con:
        rows = _history_rows(con, sport)
    index = 0
    while index < len(rows):
        game_date = date.fromisoformat(rows[index]["date"])
        end = index
        while end < len(rows) and rows[end]["date"] == rows[index]["date"]:
            end += 1
        day_rows = rows[index:end]
        for game in day_rows:
            features = tracker.features(game["home"], game["away"], game_date)
            enough = min(features["home_games_played"], features["away_games_played"]) >= min_games
            if enough and (date_from is None or game_date >= date_from):
                margin = game["home_score"] - game["away_score"]
                output.append({"game_id": game["id"], "date": game["date"],
                    "home": game["home"], "away": game["away"], **features,
                    "label_result": "H" if margin > 0 else "A" if margin < 0 else "D",
                    "label_home_win": int(margin > 0), "label_margin": margin})
        # Only after every fixture on this date has features calculated do results update the tracker.
        for game in day_rows:
            tracker.update(game)
        index = end
    return {"count": len(output), "rows": output[-limit:],
            "leakage_control": "features use only games dated before each target game"}


@router.post("/history/predictions", status_code=201, dependencies=[Depends(check_key)])
def log_prediction(prediction: HistoricalPredictionIn):
    with db() as con:
        if not con.execute("SELECT 1 FROM history_games WHERE id=?", (prediction.game_id,)).fetchone():
            raise HTTPException(404, "game_id not found in historical database")
        con.execute("INSERT INTO history_predictions(game_id,model,home_win_prob,created_at) VALUES(?,?,?,?)",
            (prediction.game_id, prediction.model, prediction.home_win_prob,
             datetime.now(timezone.utc).isoformat()))
    return {"logged": True, "game_id": prediction.game_id, "model": prediction.model}


@router.get("/accuracy/{sport}")
def model_accuracy(sport: str, model: Optional[str] = None):
    sql = ("SELECT p.model,p.home_win_prob,g.home_score,g.away_score FROM history_predictions p "
           "JOIN history_games g ON g.id=p.game_id WHERE g.sport=?")
    params = [sport.lower()]
    if model:
        sql += " AND p.model=?"; params.append(model)
    stats = defaultdict(lambda: {"n": 0, "correct": 0, "brier": 0.0})
    with db() as con:
        rows = con.execute(sql, params).fetchall()
    for row in rows:
        actual = int(row["home_score"] > row["away_score"])
        bucket = stats[row["model"]]
        bucket["n"] += 1
        bucket["correct"] += int((row["home_win_prob"] >= 0.5) == bool(actual))
        bucket["brier"] += (row["home_win_prob"] - actual) ** 2
    return {name: {"predictions": s["n"],
                   "accuracy": round(s["correct"] / s["n"], 3),
                   "brier_score": round(s["brier"] / s["n"], 4)}
            for name, s in stats.items()}


@router.get("/history/health")
def history_health():
    with db() as con:
        games = con.execute("SELECT COUNT(*) FROM history_games").fetchone()[0]
        predictions = con.execute("SELECT COUNT(*) FROM history_predictions").fetchone()[0]
    return {"storage": "sqlite", "database": os.path.basename(DB_PATH),
            "historical_games": games, "logged_predictions": predictions}


def save_single_game(game: dict):
    """Mirror a normal SmartBet /games submission into persistent history."""
    with db() as con:
        con.execute(
            "INSERT OR IGNORE INTO history_games(sport,league,season,date,home,away,home_score,away_score) VALUES(?,?,?,?,?,?,?,?)",
            (game["sport"].lower(), game.get("league"), str(game.get("season")) if game.get("season") else None,
             game["date"].isoformat() if hasattr(game["date"], "isoformat") else str(game["date"]),
             game["home"], game["away"], game["home_score"], game["away_score"]))
