"""
app.py — Flask Backend for College Assistant Chatbot
=====================================================
REST API endpoints:
  POST /api/college/load       — scrape & build knowledge base
  POST /api/chat               — send message, get response
  GET  /api/colleges           — list all scraped colleges
  DELETE /api/college/<name>   — remove a college from DB

Sessions are stored server-side in memory (keyed by session_id from client).
For production, swap with Redis or a DB-backed session store.
"""

import os
import re
import json
import uuid
import logging
from datetime import datetime
from threading import Lock
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq

from scraper import CollegeScraper, scrape_via_duckduckgo, scrape_wikipedia, store_chunks

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app, origins=["http://localhost:3000", "https://*.vercel.app"], supports_credentials=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
TOP_K = 6
MAX_HISTORY = 10

groq_client = Groq(api_key=GROQ_API_KEY)
scraper = CollegeScraper()

# In-memory session store: session_id -> {college_name, conversation, created_at}
sessions: dict[str, dict] = {}
sessions_lock = Lock()


# ── Helpers (ported from main.py) ─────────────────────────────────────────────

def build_system_prompt(college_name: str) -> str:
    return f"""You are a strict college assistant specialising in '{college_name}'.

Answer ONLY using the context chunks provided. Do NOT use any outside knowledge.

## CRITICAL RULE — When to signal for more data:
If the context chunks do NOT contain a complete, specific answer to the question,
you MUST respond with ONLY this JSON (no extra text, no markdown, nothing else):
{{"needs_more_data": true, "search_query": "<specific phrase to search for>"}}

IMPORTANT: Never mix a text answer with the JSON signal in the same response.
It is either a clean text answer OR the JSON signal — never both.

Trigger this signal when:
- The answer requires a list/enumeration and the context only has partial items
- The context says "such as" or "including" without listing everything
- Numbers, fees, dates, or rankings are missing or vague
- The user is asking for something specific that isn't clearly in the context

## Examples of CORRECT behavior:
User: "What are all the B.Tech branches?"
Context has: "CSE and ECE are popular branches"
WRONG: "The branches are CSE and ECE."
CORRECT: {{"needs_more_data": true, "search_query": "{college_name} B.Tech all branches courses offered"}}

## Other rules:
- Never guess, infer, or fill gaps with general knowledge
- Never say "you may want to check the website" as a substitute for real data
- Keep answers clear, friendly, and well-structured when you do answer
- If off-topic (unrelated to {college_name}), politely redirect
"""


def retrieve_context(college_name: str, query: str, top_k: int = TOP_K) -> tuple[str, list]:
    hits = scraper.search(college_name, query, top_k=top_k)
    if not hits:
        return "", []
    parts = [f"[{i}] ({h['section'].upper()} | {h['source']})\n{h['content']}"
             for i, h in enumerate(hits, 1)]
    return "\n\n".join(parts), hits


def context_is_thin(hits: list, query: str) -> bool:
    if len(hits) < 3:
        return True
    list_keywords = ["all", "list", "branches", "courses", "programs", "departments",
                     "fees", "fee structure", "cutoff", "eligibility", "specialization"]
    q_lower = query.lower()
    total_words = sum(len(h["content"].split()) for h in hits)
    if any(kw in q_lower for kw in list_keywords) and total_words < 200:
        return True
    return False


def call_llm(college_name: str, conversation: list, context: str) -> str:
    last_user_msg = conversation[-1]["content"]
    augmented = (
        f"Context from knowledge base:\n"
        f"───────────────────────────\n"
        f"{context if context else '(No relevant chunks found)'}\n"
        f"───────────────────────────\n\n"
        f"User question: {last_user_msg}"
    )
    messages = (
        [{"role": "system", "content": build_system_prompt(college_name)}]
        + conversation[:-1]
        + [{"role": "user", "content": augmented}]
    )
    response = groq_client.chat.completions.create(
        model=MODEL, max_tokens=1000, temperature=0.3, messages=messages
    )
    return response.choices[0].message.content


def is_needs_more_data(text: str) -> dict | None:
    match = re.search(r'\{[^{}]*"needs_more_data"\s*:\s*true[^{}]*\}', text, re.IGNORECASE | re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if data.get("needs_more_data"):
                return data
        except json.JSONDecodeError:
            pass
    return None


def clean_response(text: str) -> str:
    cleaned = re.sub(r'\{[^{}]*"needs_more_data"\s*:\s*true[^{}]*\}', "", text, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


_HALLUCINATION_PATTERNS = re.compile(
    r"(table[s]? (below|above|follows|mentioned)"
    r"|not specified in (the |this )?(provided )?context"
    r"|exact amount is not (specified|mentioned|available|provided)"
    r"|you (may|might|can|should) (want to )?check (the )?(official )?website"
    r"|contact (the )?college (for|directly))",
    re.IGNORECASE,
)

def response_has_hallucination(text: str) -> bool:
    return bool(_HALLUCINATION_PATTERNS.search(text))


def do_targeted_rescrape(college_name: str, search_query: str) -> int:
    row = scraper.conn.execute(
        "SELECT id FROM colleges WHERE name_lower = ?", (college_name.lower(),)
    ).fetchone()
    if not row:
        return 0
    college_id = row[0]
    total = 0
    web_chunks = scrape_via_duckduckgo(f"{college_name} {search_query}")
    if web_chunks:
        total += store_chunks(scraper.conn, college_id, web_chunks)
    wiki_chunks = scrape_wikipedia(college_name)
    if wiki_chunks:
        total += store_chunks(scraper.conn, college_id, wiki_chunks)
    return total


def process_message(session_id: str, user_message: str) -> dict:
    """Core chat logic. Returns dict with reply, rescrape_triggered, sources_used."""
    with sessions_lock:
        session = sessions.get(session_id)
    if not session:
        return {"error": "Session not found. Please load a college first."}, 404

    college_name = session["college_name"]
    conversation = session["conversation"]

    conversation.append({"role": "user", "content": user_message})
    if len(conversation) > MAX_HISTORY * 2:
        conversation = conversation[-(MAX_HISTORY * 2):]

    context, hits = retrieve_context(college_name, user_message)
    rescrape_triggered = False
    rescrape_reason = None

    # Proactive thin-context rescrape
    if context_is_thin(hits, user_message):
        log.info(f"Thin context for '{user_message}' — proactive rescrape")
        do_targeted_rescrape(college_name, user_message)
        context, hits = retrieve_context(college_name, user_message)
        rescrape_triggered = True
        rescrape_reason = "thin_context"

    # Call LLM
    response_text = call_llm(college_name, conversation, context)
    signal = is_needs_more_data(response_text)

    if not signal and response_has_hallucination(response_text):
        signal = {"needs_more_data": True, "search_query": f"{user_message} details"}
        rescrape_reason = "hallucination_detected"

    if signal:
        search_query = signal.get("search_query", user_message)
        log.info(f"LLM signalled needs_more_data — rescraping for: {search_query}")
        do_targeted_rescrape(college_name, search_query)
        context, hits = retrieve_context(college_name, user_message)
        rescrape_triggered = True
        response_text = call_llm(college_name, conversation, context)

        if is_needs_more_data(response_text) or response_has_hallucination(response_text):
            partial_prompt = (
                f"Context from knowledge base:\n───────────────────────────\n"
                f"{context if context else '(No relevant chunks found)'}\n"
                f"───────────────────────────\n\n"
                f"The user asked: {user_message}\n\n"
                f"Share whatever partial or related information is available in the context above. "
                f"Be honest that the information may be incomplete. "
                f"At the end, add: '⚠️ For complete and accurate details, manual verification on the official website is recommended.'"
            )
            fallback_messages = [
                {"role": "system", "content": build_system_prompt(college_name)},
                {"role": "user", "content": partial_prompt},
            ]
            try:
                fallback_resp = groq_client.chat.completions.create(
                    model=MODEL, max_tokens=800, temperature=0.3, messages=fallback_messages
                )
                response_text = fallback_resp.choices[0].message.content
            except Exception:
                response_text = (
                    f"I have limited information about this for {college_name}.\n\n"
                    f"⚠️ For complete and accurate details, manual verification on the official website is recommended."
                )

    display_text = clean_response(response_text)
    conversation.append({"role": "assistant", "content": display_text})

    with sessions_lock:
        sessions[session_id]["conversation"] = conversation

    sources = list({h["source"] for h in hits}) if hits else []
    return {
        "reply": display_text,
        "rescrape_triggered": rescrape_triggered,
        "rescrape_reason": rescrape_reason,
        "sources": sources,
        "session_id": session_id,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": MODEL, "timestamp": datetime.utcnow().isoformat()})


@app.route("/api/college/load", methods=["POST"])
def load_college():
    """
    Body: { "college_name": "...", "session_id": "..." (optional), "force_refresh": false }
    Returns: { "session_id": "...", "status": "success|cached|error", "chunks": N, "message": "..." }
    """
    data = request.get_json(force=True)
    college_name = (data.get("college_name") or "").strip()
    if len(college_name) < 3:
        return jsonify({"error": "college_name must be at least 3 characters"}), 400

    force_refresh = data.get("force_refresh", False)
    session_id = data.get("session_id") or str(uuid.uuid4())

    log.info(f"Loading college: {college_name} (session={session_id})")
    result = scraper.scrape_and_store(college_name, force_refresh=force_refresh)

    if result["status"] == "error":
        return jsonify(result), 422

    with sessions_lock:
        sessions[session_id] = {
            "college_name": college_name,
            "conversation": [],
            "created_at": datetime.utcnow().isoformat(),
        }

    return jsonify({**result, "session_id": session_id})


@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Body: { "session_id": "...", "message": "..." }
    Returns: { "reply": "...", "rescrape_triggered": bool, "sources": [...] }
    """
    data = request.get_json(force=True)
    session_id = data.get("session_id", "").strip()
    message = (data.get("message") or "").strip()

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    if not message:
        return jsonify({"error": "message cannot be empty"}), 400
    if len(message) > 2000:
        return jsonify({"error": "message too long (max 2000 chars)"}), 400

    with sessions_lock:
        if session_id not in sessions:
            return jsonify({"error": "Session not found. Please load a college first."}), 404

    result = process_message(session_id, message)
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    return jsonify(result)


@app.route("/api/colleges", methods=["GET"])
def list_colleges():
    """List all colleges in the DB."""
    colleges = scraper.list_colleges()
    return jsonify({"colleges": colleges})


@app.route("/api/college/history", methods=["GET"])
def get_history():
    """GET /api/college/history?session_id=xxx"""
    session_id = request.args.get("session_id", "").strip()
    if not session_id:
        return jsonify({"error": "session_id required"}), 400
    with sessions_lock:
        session = sessions.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    return jsonify({
        "college_name": session["college_name"],
        "conversation": session["conversation"],
        "created_at": session["created_at"],
    })


@app.route("/api/college/reset", methods=["POST"])
def reset_session():
    """Reset conversation history for a session."""
    data = request.get_json(force=True)
    session_id = data.get("session_id", "").strip()
    with sessions_lock:
        if session_id in sessions:
            sessions[session_id]["conversation"] = []
    return jsonify({"status": "ok", "message": "Conversation history cleared."})


if __name__ == "__main__":
    if not GROQ_API_KEY:
        print("❌  GROQ_API_KEY not set. Export it before running.")
        exit(1)
    app.run(debug=True, port=5000)
