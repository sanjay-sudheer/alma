# 🎓 Alma — College Intelligence Chatbot

An AI-powered college research assistant that scrapes the web in real-time, builds a local knowledge base using RAG (Retrieval-Augmented Generation), and answers student queries with verified data. Built with Flask, Next.js, Groq, and Google OAuth.

---

## ✨ Features

- **Real-time Web Scraping** — Scrapes Wikipedia, DuckDuckGo results, and college websites on demand
- **RAG Pipeline** — Stores scraped content as vector chunks in SQLite; retrieves the most relevant ones per query
- **Smart Re-scraping** — If the AI detects it doesn't have enough data, it automatically scrapes more and retries
- **Hallucination Guard** — Detects vague/deferral phrases in AI responses and triggers re-scraping instead of guessing
- **Conversation Memory** — Keeps last 10 turns of context per session
- **Google Sign-In** — Secure authentication via NextAuth.js + Google OAuth
- **Collapsible Sidebar** — Shows recent colleges, quick-switch between colleges
- **Suggested Queries** — Pre-built question chips after loading a college
- **Source Badges** — Every AI response shows which sources were used (Wikipedia, official site, etc.)

---

## 🗂 Project Structure

```
college-chatbot/
├── backend/
│   ├── app.py              ← Flask REST API
│   ├── scraper.py          ← Web scraper + SQLite RAG vector store
│   ├── main.py             ← CLI version (optional, for testing)
│   ├── requirements.txt    ← Python dependencies
│   └── .env                ← Your backend secrets (never commit this)
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── globals.css
│   │   │   ├── page.tsx                        ← redirects to /chat
│   │   │   ├── chat/page.tsx                   ← main chat interface
│   │   │   ├── auth/signin/page.tsx            ← Google sign-in page
│   │   │   └── api/auth/[...nextauth]/route.ts ← NextAuth handler
│   │   ├── components/
│   │   │   └── Providers.tsx
│   │   └── lib/
│   │       └── api.ts                          ← API client (fetch wrappers)
│   ├── .env.local          ← Your frontend secrets (never commit this)
│   ├── next.config.js
│   ├── tailwind.config.ts
│   └── package.json
│
└── README.md
```

---

## ⚙️ Prerequisites

Make sure you have these installed:

| Tool | Version | Download |
|------|---------|----------|
| Python | 3.10+ | python.org |
| Node.js | 18+ | nodejs.org |
| npm | 9+ | comes with Node |

---

## 🚀 Setup & Running

### Step 1 — Clone / Extract the project

```
college-chatbot/
├── backend/
└── frontend/
```

---

### Step 2 — Backend Setup

#### 2a. Create a virtual environment

```bash
cd college-chatbot/backend

# Create venv
python -m venv venv

# Activate it
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac / Linux
```

#### 2b. Install dependencies

```bash
pip install -r requirements.txt
pip install python-dotenv    # if not already in requirements
```

#### 2c. Create the `.env` file

Create a file called `.env` inside the `backend/` folder:

```
backend/.env
```

Add this content:

```env
GROQ_API_KEY=your_groq_api_key_here
```

> 🔑 Get a free Groq API key at [console.groq.com](https://console.groq.com) — no credit card needed.

The backend loads it automatically using `python-dotenv`:

```python
from dotenv import load_dotenv
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
```

#### 2d. Run the Flask server

```bash
python app.py
```

You should see:
```
INFO | Database ready: college_rag.db
 * Running on http://127.0.0.1:5000
```

> ✅ Keep this terminal open. The backend must be running for the frontend to work.

---

### Step 3 — Google OAuth Setup

You need a Google OAuth client to enable "Sign in with Google".

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or select an existing one)
3. Navigate to **APIs & Services → Credentials**
4. Click **Create Credentials → OAuth 2.0 Client ID**
5. Set **Application type** to **Web application**
6. Under **Authorized redirect URIs**, add:
   ```
   http://localhost:3000/api/auth/callback/google
   ```
7. Click **Create** — copy the **Client ID** and **Client Secret**

---

### Step 4 — Frontend Setup

#### 4a. Install dependencies

```bash
cd college-chatbot/frontend
npm install
```

#### 4b. Create the `.env.local` file

Create a file called `.env.local` inside the `frontend/` folder:

```
frontend/.env.local
```

Add this content:

```env
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here

NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=any_long_random_string_you_make_up

NEXT_PUBLIC_API_URL=http://localhost:5000
```

> 💡 For `NEXTAUTH_SECRET`, just make up any long random string like:
> `NEXTAUTH_SECRET=alma_chatbot_super_secret_key_2024_xyz`

#### 4c. Run the dev server

```bash
npm run dev
```

You should see:
```
▲ Next.js 14
- Local: http://localhost:3000
```

---

### Step 5 — Open the app

Visit **[http://localhost:3000](http://localhost:3000)** in your browser.

1. Click **Continue with Google** and sign in
2. You'll be redirected to the chat page
3. Type a college name in the sidebar (e.g. `IIT Bombay`)
4. Click the arrow button — Alma will scrape the web and build a knowledge base
5. Ask anything!

---

## 🔌 Backend API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/college/load` | Scrape & load a college into session |
| `POST` | `/api/chat` | Send a message, get AI reply |
| `GET` | `/api/colleges` | List all scraped colleges in DB |
| `GET` | `/api/college/history?session_id=` | Get conversation history |
| `POST` | `/api/college/reset` | Clear conversation history |

### Example — Load a college

```json
POST http://localhost:5000/api/college/load
Content-Type: application/json

{
  "college_name": "IIT Bombay",
  "force_refresh": false
}
```

Response:
```json
{
  "session_id": "abc-123-uuid",
  "status": "success",
  "chunks": 247,
  "sources": ["wikipedia", "web:iitb.ac.in"],
  "message": "Scraped and stored 247 knowledge chunks..."
}
```

### Example — Chat

```json
POST http://localhost:5000/api/chat
Content-Type: application/json

{
  "session_id": "abc-123-uuid",
  "message": "What are all the B.Tech branches?"
}
```

Response:
```json
{
  "reply": "IIT Bombay offers B.Tech in...",
  "rescrape_triggered": false,
  "sources": ["wikipedia"],
  "session_id": "abc-123-uuid"
}
```

---

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Model | Groq — `llama-3.3-70b-versatile` |
| Web Scraping | BeautifulSoup + DuckDuckGo HTML search |
| Vector Store | SQLite + NumPy cosine similarity |
| Backend | Flask + Flask-CORS |
| Frontend | Next.js 14 + TypeScript |
| Auth | NextAuth.js + Google OAuth 2.0 |
| Styling | Tailwind CSS |
| Fonts | Playfair Display + DM Sans |

---

## 🐛 Common Issues

| Error | Fix |
|-------|-----|
| `SQLite objects created in a thread...` | Make sure you're using the fixed `scraper.py` with `check_same_thread=False` |
| `GROQ_API_KEY not set` | Check your `backend/.env` file exists and has the key |
| `NEXTAUTH_SECRET` error | Make sure `.env.local` has `NEXTAUTH_SECRET` set to any long string |
| Google sign-in redirect error | Make sure `http://localhost:3000/api/auth/callback/google` is added in Google Console |
| `CORS` errors in browser | Make sure the Flask backend is running on port 5000 |
| `Cannot find module` in Next.js | Run `npm install` inside the `frontend/` folder |

---

## 📝 Notes

- The SQLite database (`college_rag.db`) is created automatically in the `backend/` folder on first run
- Already-scraped colleges are cached — re-loading them is instant. Use `force_refresh: true` in the API to re-scrape
- The AI model is `llama-3.3-70b-versatile` via Groq — it's free tier with generous limits
- Sessions are stored in memory, so they reset when the Flask server restarts