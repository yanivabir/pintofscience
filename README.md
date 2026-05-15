# Pint of Science Poll

Audience participation polling app for live talks.

## Setup your questions

Edit [`questions.json`](questions.json) — replace the examples with your real questions and answers. The order in the file is the display order on the presenter chart (participants see them shuffled).

```json
[
  {
    "text": "Your question here?",
    "answer": "The answer, as long as you like."
  }
]
```

**Important:** questions are loaded into the database on first boot. If you change the file after deploying, you need to either redeploy with a fresh database or manually clear the `questions` table.

---

## Deploy to Railway

1. **Create a GitHub repo** and push this folder to it.

2. **Go to [railway.app](https://railway.app)** → New Project → Deploy from GitHub repo → select your repo.

3. **Add a PostgreSQL database:**  
   In your Railway project, click **+ New** → **Database** → **PostgreSQL**.  
   Railway automatically sets `DATABASE_URL` in your app's environment.

4. **Railway auto-deploys.** Once the build finishes you'll get a public URL like  
   `https://your-app.up.railway.app`

5. **Participant link:** `https://your-app.up.railway.app/`  
   **Presenter link:** `https://your-app.up.railway.app/presenter`

6. **Generate a QR code** for the participant link at [qr.io](https://qr.io) or any QR generator, and put it on your slides.

---

## How it works

| Who | What they see |
|-----|--------------|
| Audience | Questions one at a time (randomised order per person) → rate curiosity 1–5 → optionally tick "I know the answer" → if not, see the answer and rate satisfaction 1–5 |
| Presenter | Bar chart at `/presenter` — avg curiosity (blue), avg satisfaction (orange), knew-the-answer count (green, right axis) — auto-refreshes every 3 s |

---

## Running locally (optional)

```bash
pip install -r requirements.txt
DATABASE_URL=postgresql://localhost/pintofscience uvicorn app:app --reload
```
