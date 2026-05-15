import os
import json
import random
import hashlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional
import asyncpg

pool = None


async def init_db(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            text TEXT NOT NULL,
            answer TEXT NOT NULL,
            display_order INTEGER NOT NULL
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            question_id INTEGER REFERENCES questions(id),
            curiosity INTEGER NOT NULL CHECK (curiosity BETWEEN 1 AND 5),
            knows_answer BOOLEAN NOT NULL DEFAULT FALSE,
            satisfaction INTEGER CHECK (satisfaction BETWEEN 1 AND 5),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(session_id, question_id)
        )
    """)
    count = await conn.fetchval("SELECT COUNT(*) FROM questions")
    if count == 0:
        with open("questions.json") as f:
            questions = json.load(f)
        for i, q in enumerate(questions):
            await conn.execute(
                "INSERT INTO questions (text, answer, display_order) VALUES ($1, $2, $3)",
                q["text"], q["answer"], i,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    db_url = db_url.replace("postgres://", "postgresql://", 1)
    # Log host so we can diagnose connection issues (password stays hidden)
    import urllib.parse as _up
    _p = _up.urlparse(db_url)
    print(f"[DB] connecting to {_p.hostname}:{_p.port} db={_p.path}", flush=True)
    pool = await asyncpg.create_pool(db_url, ssl="require")
    async with pool.acquire() as conn:
        await init_db(conn)
    yield
    await pool.close()


app = FastAPI(lifespan=lifespan)


def shuffle_for_session(items: list, session_id: str) -> list:
    seed = int(hashlib.md5(session_id.encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    items = list(items)
    rng.shuffle(items)
    return items


class CuriositySubmit(BaseModel):
    session_id: str
    question_id: int
    curiosity: int
    knows_answer: bool


class SatisfactionSubmit(BaseModel):
    session_id: str
    question_id: int
    satisfaction: int


@app.get("/api/questions")
async def get_questions(session_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, text FROM questions ORDER BY display_order"
        )
    questions = [{"id": r["id"], "text": r["text"]} for r in rows]
    return shuffle_for_session(questions, session_id)


@app.get("/api/questions/{question_id}/answer")
async def get_answer(question_id: int, session_id: str):
    async with pool.acquire() as conn:
        resp = await conn.fetchrow(
            "SELECT knows_answer FROM responses WHERE session_id=$1 AND question_id=$2",
            session_id, question_id,
        )
        if not resp:
            raise HTTPException(403, "Submit curiosity rating first")
        if resp["knows_answer"]:
            raise HTTPException(403, "You indicated you know the answer")
        q = await conn.fetchrow("SELECT answer FROM questions WHERE id=$1", question_id)
    return {"answer": q["answer"]}


@app.post("/api/response/curiosity")
async def submit_curiosity(data: CuriositySubmit):
    if not 1 <= data.curiosity <= 5:
        raise HTTPException(400, "Curiosity must be 1–5")
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM responses WHERE session_id=$1 AND question_id=$2",
            data.session_id, data.question_id,
        )
        if existing:
            raise HTTPException(409, "Already submitted for this question")
        await conn.execute(
            """INSERT INTO responses (session_id, question_id, curiosity, knows_answer)
               VALUES ($1, $2, $3, $4)""",
            data.session_id, data.question_id, data.curiosity, data.knows_answer,
        )
    return {"ok": True, "show_answer": not data.knows_answer}


@app.post("/api/response/satisfaction")
async def submit_satisfaction(data: SatisfactionSubmit):
    if not 1 <= data.satisfaction <= 5:
        raise HTTPException(400, "Satisfaction must be 1–5")
    async with pool.acquire() as conn:
        resp = await conn.fetchrow(
            "SELECT knows_answer, satisfaction FROM responses WHERE session_id=$1 AND question_id=$2",
            data.session_id, data.question_id,
        )
        if not resp:
            raise HTTPException(400, "Submit curiosity rating first")
        if resp["knows_answer"]:
            raise HTTPException(400, "No satisfaction rating for questions you already knew")
        if resp["satisfaction"] is not None:
            raise HTTPException(409, "Already submitted satisfaction rating")
        await conn.execute(
            "UPDATE responses SET satisfaction=$1 WHERE session_id=$2 AND question_id=$3",
            data.satisfaction, data.session_id, data.question_id,
        )
    return {"ok": True}


@app.get("/api/stats")
async def get_stats():
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                q.id,
                q.text,
                q.display_order,
                COUNT(r.id)::int                                                     AS total_responses,
                ROUND(AVG(r.curiosity)::numeric, 2)::float                           AS avg_curiosity,
                SUM(CASE WHEN r.knows_answer THEN 1 ELSE 0 END)::int                AS knew_count,
                ROUND(AVG(CASE WHEN NOT r.knows_answer THEN r.satisfaction END)::numeric, 2)::float
                                                                                     AS avg_satisfaction
            FROM questions q
            LEFT JOIN responses r ON r.question_id = q.id
            GROUP BY q.id, q.text, q.display_order
            ORDER BY q.display_order
        """)
    return [dict(r) for r in rows]


@app.get("/reset")
async def reset_page():
    return HTMLResponse("""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reset Poll</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #111827; color: #f3f4f6;
      min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px;
    }
    .card {
      background: #1f2937; border-radius: 16px; padding: 36px 32px;
      max-width: 400px; width: 100%; text-align: center;
    }
    h1 { font-size: 22px; margin-bottom: 10px; }
    p  { color: #9ca3af; font-size: 14px; margin-bottom: 28px; line-height: 1.5; }
    input {
      width: 100%; padding: 13px 14px; font-size: 16px; border-radius: 10px;
      border: 2px solid #374151; background: #111827; color: #f3f4f6;
      margin-bottom: 14px; outline: none;
    }
    input:focus { border-color: #f59e0b; }
    button {
      width: 100%; padding: 14px; font-size: 16px; font-weight: 700;
      border: none; border-radius: 10px; background: #ef4444; color: #fff; cursor: pointer;
    }
    button:active { opacity: 0.85; }
    .msg { margin-top: 18px; font-size: 14px; min-height: 20px; }
    .ok  { color: #10b981; }
    .err { color: #ef4444; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Reset Poll</h1>
    <p>Clears all responses so the poll is fresh for a new audience.<br>Questions are kept.</p>
    <input type="password" id="key" placeholder="Reset key" autocomplete="off">
    <button onclick="doReset()">Clear all responses</button>
    <div class="msg" id="msg"></div>
  </div>
  <script>
    async function doReset() {
      const key = document.getElementById('key').value.trim();
      const msg = document.getElementById('msg');
      if (!key) { msg.textContent = 'Enter the reset key.'; msg.className = 'msg err'; return; }
      msg.textContent = '…'; msg.className = 'msg';
      try {
        const res = await fetch('/api/reset', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key }),
        });
        const data = await res.json();
        if (res.ok) { msg.textContent = 'Done — all responses cleared.'; msg.className = 'msg ok'; }
        else        { msg.textContent = data.detail || 'Error.'; msg.className = 'msg err'; }
      } catch { msg.textContent = 'Request failed.'; msg.className = 'msg err'; }
    }
    document.getElementById('key').addEventListener('keydown', e => { if (e.key === 'Enter') doReset(); });
  </script>
</body>
</html>""")


class ResetRequest(BaseModel):
    key: str


@app.post("/api/reset")
async def do_reset(data: ResetRequest):
    reset_key = os.environ.get("RESET_KEY", "")
    if not reset_key:
        raise HTTPException(503, "RESET_KEY environment variable not set")
    if data.key != reset_key:
        raise HTTPException(403, "Wrong key")
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM responses")
    return {"ok": True}


@app.get("/presenter")
async def presenter():
    return FileResponse("static/presenter.html")


@app.get("/")
async def participant():
    return FileResponse("static/participant.html")
