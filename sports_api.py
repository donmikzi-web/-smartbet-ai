"""SmartBet AI sports analysis API.

Run: pip install -r requirements.txt
     uvicorn sports_api:app --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs

Quick-entry cache plus persistent SQLite history and ML model routes.
"""
from collections import defaultdict
from datetime import date
from math import erf, sqrt
import os
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from sports_history_api import router as history_router, save_single_game

app = FastAPI(title="SmartBet AI Sports Analysis API", version="2.0.0",
              description="Basketball (NBA/NCAA) and football analysis API. Estimates are not betting guarantees.")
GAMES: list[dict] = []
PLAYER_STATS: list[dict] = []

class GameIn(BaseModel):
    sport: str = Field(min_length=2, max_length=30, examples=["basketball", "soccer"])
    league: str = Field(default="Unspecified", max_length=80)
    date: date
    home: str = Field(min_length=1, max_length=100)
    away: str = Field(min_length=1, max_length=100)
    home_score: int = Field(ge=0)
    away_score: int = Field(ge=0)
    home_first_half_score: Optional[int] = Field(default=None, ge=0)
    away_first_half_score: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def different_teams(self):
        if self.home.strip().casefold() == self.away.strip().casefold():
            raise ValueError("Home and away teams must be different")
        if (self.home_first_half_score is None) != (self.away_first_half_score is None):
            raise ValueError("Provide both first-half scores, or neither")
        if self.home_first_half_score is not None and (
            self.home_first_half_score > self.home_score or self.away_first_half_score > self.away_score
        ):
            raise ValueError("First-half score cannot exceed the final score")
        return self

class PlayerStatIn(BaseModel):
    sport: str
    player: str
    team: str
    game_id: int
    stats: dict[str, float]

class MatchupQuery(BaseModel):
    sport: str = Field(examples=["basketball", "soccer"])
    home: str
    away: str
    market: str = Field(description="total, first_half_total, or winner")
    line: Optional[float] = None


def _games(sport: str, team: Optional[str] = None):
    out = [g for g in GAMES if g["sport"] == sport.lower()]
    if team:
        out = [g for g in out if team.casefold() in (g["home"].casefold(), g["away"].casefold())]
    return sorted(out, key=lambda g: (g["date"], g["id"]))


def _result(g: dict, team: str) -> str:
    mine, theirs = ((g["home_score"], g["away_score"]) if g["home"].casefold() == team.casefold()
                    else (g["away_score"], g["home_score"]))
    return "W" if mine > theirs else "L" if mine < theirs else "D"


def _elo(sport: str, k: float = 20, home_adv: float = 60):
    ratings = defaultdict(lambda: 1500.0)
    for g in _games(sport):
        h, a = g["home"], g["away"]
        rh, ra = ratings[h], ratings[a]
        expected = 1 / (1 + 10 ** ((ra - rh - home_adv) / 400))
        actual = 1.0 if g["home_score"] > g["away_score"] else 0.5 if g["home_score"] == g["away_score"] else 0.0
        ratings[h] += k * (actual - expected)
        ratings[a] -= k * (actual - expected)
    return dict(ratings)


def _normal_cdf(x: float, mean: float, sd: float) -> float:
    if sd <= 0:
        return 1.0 if x >= mean else 0.0
    return 0.5 * (1 + erf((x - mean) / (sd * sqrt(2))))

@app.get("/health")
def health():
    return {"status": "ok", "games": len(GAMES), "player_stat_records": len(PLAYER_STATS),
            "storage": "in-memory", "api_version": "2.0.0"}

@app.post("/games", status_code=201)
def add_game(game: GameIn):
    rec = game.model_dump()
    rec["sport"] = rec["sport"].strip().lower()
    rec["home"] = rec["home"].strip(); rec["away"] = rec["away"].strip()
    rec["id"] = max((g["id"] for g in GAMES), default=0) + 1
    GAMES.append(rec)
    save_single_game(rec)  # persist the same completed result for historical training/features
    return rec

@app.post("/player-stats", status_code=201)
def add_player_stat(stat: PlayerStatIn):
    if not any(g["id"] == stat.game_id for g in GAMES):
        raise HTTPException(404, "game_id not found")
    rec = stat.model_dump(); rec["sport"] = rec["sport"].lower()
    PLAYER_STATS.append(rec)
    return rec

@app.get("/sports")
def sports():
    return sorted({g["sport"] for g in GAMES})

@app.get("/games")
def list_games(sport: str, team: Optional[str] = None, limit: int = Query(50, ge=1, le=500)):
    return _games(sport, team)[-limit:]

@app.get("/standings/{sport}")
def standings(sport: str):
    table = defaultdict(lambda: {"played":0,"wins":0,"draws":0,"losses":0,"for":0,"against":0,"points":0})
    for g in _games(sport):
        for team, mine, theirs in ((g["home"],g["home_score"],g["away_score"]),(g["away"],g["away_score"],g["home_score"])):
            row=table[team]; row["played"]+=1; row["for"]+=mine; row["against"]+=theirs
            if mine>theirs: row["wins"]+=1; row["points"]+=3 if sport.lower() in ("soccer","football") else 2
            elif mine<theirs: row["losses"]+=1
            else: row["draws"]+=1; row["points"]+=1 if sport.lower() in ("soccer","football") else 1
    rows=[{"team":t,**r,"diff":r["for"]-r["against"]} for t,r in table.items()]
    return sorted(rows,key=lambda r:(-r["points"],-r["wins"],-r["diff"]))

@app.get("/teams/{sport}/{team}/form")
def form(sport: str, team: str, n: int = Query(5, ge=1, le=20)):
    games=_games(sport,team)[-n:]
    if not games: raise HTTPException(404,"no games for that team")
    results=[_result(g,team) for g in games]
    return {"team":team,"last":results,"games":len(results),"wins":results.count("W"),
            "win_rate":round(results.count("W")/len(results),3)}

@app.get("/h2h/{sport}")
def head_to_head(sport: str, a: str, b: str):
    games=[g for g in _games(sport) if {g["home"].casefold(),g["away"].casefold()}=={a.casefold(),b.casefold()}]
    return {"games":len(games),a:sum(_result(g,a)=="W" for g in games),b:sum(_result(g,b)=="W" for g in games),
            "draws":sum(_result(g,a)=="D" for g in games),"history":games}

@app.get("/ratings/{sport}")
def ratings(sport: str):
    return sorted(({"team":t,"elo":round(v,1)} for t,v in _elo(sport).items()),key=lambda x:-x["elo"])

@app.get("/predict/{sport}")
def predict(sport: str, home: str, away: str):
    if home.casefold()==away.casefold(): raise HTTPException(400,"Teams must be different")
    r=_elo(sport); rh,ra=r.get(home,1500.0),r.get(away,1500.0)
    p=1/(1+10**((ra-rh-60)/400))
    return {"sport":sport,"home":home,"away":away,"home_win_prob":round(p,3),"away_win_prob":round(1-p,3),
            "rating_sample_size":len(_games(sport)),"note":"Elo estimate from entered results; not a guaranteed outcome. Draws are not separately modelled in this endpoint."}

@app.get("/analysis/total")
def total_analysis(sport: str, home: str, away: str, line: float, first_half: bool = False):
    history=_games(sport)
    key_h="home_first_half_score" if first_half else "home_score"
    key_a="away_first_half_score" if first_half else "away_score"
    sample=[g[key_h]+g[key_a] for g in history if g[key_h] is not None and g[key_a] is not None]
    market="first_half_total" if first_half else "full_game_total"
    if len(sample)<5:
        return {"sport":sport,"home":home,"away":away,"market":market,"line":line,"sample_size":len(sample),
                "status":"insufficient_data","over_probability":None,"under_probability":None,
                "message":"At least 5 matching historical score records are required. Add real completed games, including first-half scores for first-half analysis."}
    mean=sum(sample)/len(sample); variance=sum((x-mean)**2 for x in sample)/len(sample); sd=sqrt(variance)
    p_over=1-_normal_cdf(line,mean,sd)
    return {"sport":sport,"home":home,"away":away,"market":market,"line":line,"sample_size":len(sample),
            "historical_average":round(mean,2),"historical_std_dev":round(sd,2),
            "over_probability":round(max(0,min(1,p_over)),3),"under_probability":round(max(0,min(1,1-p_over)),3),
            "status":"estimate","warning":"Historical league-wide score distribution only; it does not yet account for team pace, injuries, lineups, venue, or bookmaker margin."}

@app.get("/leaders/{sport}/{stat}")
def leaders(sport: str, stat: str, limit: int = Query(10,ge=1,le=100), average: bool = True):
    totals=defaultdict(list)
    for p in PLAYER_STATS:
        if p["sport"]==sport.lower() and stat in p["stats"]: totals[p["player"]].append(p["stats"][stat])
    rows=[{"player":n,"games":len(v),"total":sum(v),"average":round(sum(v)/len(v),2)} for n,v in totals.items()]
    return sorted(rows,key=lambda r:-r["average" if average else "total"])[:limit]

@app.post("/analysis/matchup")
def matchup(q: MatchupQuery):
    if q.market not in ("winner","total","first_half_total"):
        raise HTTPException(400,"market must be winner, total, or first_half_total")
    if q.market=="winner": return predict(q.sport,q.home,q.away)
    if q.line is None: raise HTTPException(400,"A line is required for totals markets")
    return total_analysis(q.sport,q.home,q.away,q.line,q.market=="first_half_total")

@app.get("/api/football/leagues")
async def football_leagues(id: int = 39, season: int = 2026):
    key=os.getenv("API_FOOTBALL_KEY")
    if not key: raise HTTPException(503,"API_FOOTBALL_KEY is not configured on the server")
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            response=await client.get("https://v3.football.api-sports.io/leagues",params={"id":id,"season":season},headers={"x-apisports-key":key})
            response.raise_for_status(); return response.json()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(exc.response.status_code,"API-Sports rejected the request")
        except httpx.HTTPError:
            raise HTTPException(502,"Could not reach API-Sports")

# Persistent historical database, leakage-safe datasets, and model evaluation.
app.include_router(history_router)

# Historical ML training, ESPN ingestion, model predictions, and upcoming fixtures.
import sports_ml_api  # noqa: F401,E402 - registers ML routes on this app

# Serve the existing SmartBet AI frontend from the same FastAPI service.
app.mount("/", StaticFiles(directory=".", html=True), name="site")
