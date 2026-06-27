"""Tic-tac-toe scoreboard API + static game UI (cloud-agnostic).

Durable store: Postgres. Live leaderboard: Redis sorted set. Redis connection
supports optional TLS + AUTH (REDIS_SSL / REDIS_PASSWORD) so the same image runs
on GCP Memorystore (no auth) and Azure Cache for Redis (TLS + access key).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import psycopg
import redis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PG_DSN = os.environ["DATABASE_URL"]
_LEADERBOARD = "leaderboard"

_r = redis.Redis(
    host=os.environ.get("REDIS_HOST", "127.0.0.1"),
    port=int(os.environ.get("REDIS_PORT", "6379")),
    password=os.environ.get("REDIS_PASSWORD") or None,
    ssl=os.environ.get("REDIS_SSL", "false").lower() == "true",
    socket_connect_timeout=3,
    decode_responses=True,
)


def _init_db() -> None:
    with psycopg.connect(PG_DSN, connect_timeout=15) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS players ("
            "name TEXT PRIMARY KEY, wins INTEGER NOT NULL DEFAULT 0)"
        )
        conn.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _init_db()
    yield


app = FastAPI(lifespan=lifespan)


class Win(BaseModel):
    player: str


@app.post("/api/win")
def record_win(win: Win) -> dict:
    name = win.player.strip()[:40]
    if not name:
        return JSONResponse({"error": "name required"}, status_code=400)
    with psycopg.connect(PG_DSN, connect_timeout=15) as conn:
        row = conn.execute(
            "INSERT INTO players(name, wins) VALUES (%s, 1) "
            "ON CONFLICT (name) DO UPDATE SET wins = players.wins + 1 RETURNING wins",
            (name,),
        ).fetchone()
        conn.commit()
    wins = int(row[0])
    try:
        _r.zadd(_LEADERBOARD, {name: wins})
    except redis.RedisError:
        pass
    return {"player": name, "wins": wins}


@app.get("/api/leaderboard")
def leaderboard() -> dict:
    try:
        top = _r.zrevrange(_LEADERBOARD, 0, 9, withscores=True)
        if top:
            return {"top": [{"player": n, "wins": int(s)} for n, s in top]}
    except redis.RedisError:
        pass
    with psycopg.connect(PG_DSN, connect_timeout=15) as conn:
        rows = conn.execute(
            "SELECT name, wins FROM players ORDER BY wins DESC, name LIMIT 10"
        ).fetchall()
    return {"top": [{"player": n, "wins": int(w)} for n, w in rows]}


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
