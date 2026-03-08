"""
main.py — College Assistant Chatbot
=====================================
Entry point for the college chatbot.

Flow:
  1. Ask user which college they want to know about
  2. Scrape + build knowledge base (or use cached)
  3. Chat loop: answer queries using RAG + Groq API
  4. If Groq is unsure → re-scrape targeted content

Usage:
    python main.py
"""

import os
import sys
import json
import re
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

from scraper import CollegeScraper

# ── Config ────────────────────────────────────────────────────────────────────

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"   # fast + smart; free tier available
TOP_K = 6          # chunks retrieved per query
MAX_HISTORY = 10   # conversation turns kept in memory

# ── Client ────────────────────────────────────────────────────────────────────

client = Groq(api_key=GROQ_API_KEY)


def print_banner():
    print("\n" + "═" * 58)
    print("       🎓  College Assistant Chatbot  (Groq)")
    print("═" * 58)
    print("  Ask anything about admissions, fees, courses,")
    print("  placements, campus life, and more.")
    print("  Type  'exit' to quit  |  'switch' to change college")
    print("═" * 58 + "\n")


def ask_college_name() -> str:
    """Prompt user for a college name until they give a non-empty one."""
    while True:
        name = input("🏫  Which college do you want to explore?\n> ").strip()
        if name.lower() in ("exit", "quit"):
            print("Goodbye!")
            sys.exit(0)
        if len(name) >= 3:
            return name
        print("   Please enter a valid college name (at least 3 characters).\n")


def build_knowledge_base(scraper: CollegeScraper, college_name: str) -> dict:
    """Run scraper and show progress to user."""
    print(f"\n⏳  Setting up knowledge base for '{college_name}' …")
    result = scraper.scrape_and_store(college_name)

    if result["status"] == "cached":
        print(f"✅  Found cached data — {result['chunks']} knowledge chunks ready.\n")
    elif result["status"] == "success":
        sources = ", ".join(result.get("sources", []))
        print(f"✅  Scraped {result['chunks']} chunks from: {sources}\n")
    else:
        print(f"⚠️   {result['message']}\n")

    return result


def retrieve_context(scraper: CollegeScraper, college_name: str, query: str, top_k: int = TOP_K) -> str:
    """Retrieve top-k relevant chunks and format them as a context block."""
    hits = scraper.search(college_name, query, top_k=top_k)
    if not hits:
        return ""
    parts = []
    for i, h in enumerate(hits, 1):
        parts.append(f"[{i}] ({h['section'].upper()} | {h['source']})\n{h['content']}")
    return "\n\n".join(parts)


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
WRONG response: "The branches are CSE and ECE." ← incomplete list, do NOT do this
CORRECT response: {{"needs_more_data": true, "search_query": "{college_name} B.Tech all branches courses offered"}}

User: "What is the fee structure?"
Context has: full fee breakdown with numbers
CORRECT response: Answer directly from context with the fee details.

## Other rules:
- Never guess, infer, or fill gaps with general knowledge
- Never say "you may want to check the website" as a substitute for real data — trigger the JSON signal instead
- Keep answers clear, friendly, and well-structured when you do answer
- If off-topic (unrelated to {college_name}), politely redirect
"""


def call_llm(college_name: str, conversation: list[dict], context: str) -> str:
    """
    Call Groq with the conversation history + fresh context injected
    as a system-level context block.
    Groq uses the OpenAI-compatible chat completions format.
    """
    last_user_msg = conversation[-1]["content"]

    augmented_user_msg = f"""Context from knowledge base:
───────────────────────────
{context if context else "(No relevant chunks found)"}
───────────────────────────

User question: {last_user_msg}"""

    # Build messages: system + history (minus last) + augmented last user msg
    messages = (
        [{"role": "system", "content": build_system_prompt(college_name)}]
        + conversation[:-1]
        + [{"role": "user", "content": augmented_user_msg}]
    )

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=1000,
        temperature=0.3,
        messages=messages,
    )
    return response.choices[0].message.content


THIN_CONTEXT_THRESHOLD = 3   # if fewer than this many chunks retrieved, auto-rescrape


def context_is_thin(hits: list[dict], query: str) -> bool:
    """
    Return True if retrieved context is likely insufficient:
    - Too few chunks, OR
    - Query asks for a complete list but context has very little content
    """
    if len(hits) < THIN_CONTEXT_THRESHOLD:
        return True
    list_keywords = ["all", "list", "branches", "courses", "programs", "departments",
                     "fees", "fee structure", "cutoff", "eligibility", "specialization"]
    q_lower = query.lower()
    total_words = sum(len(h["content"].split()) for h in hits)
    if any(kw in q_lower for kw in list_keywords) and total_words < 200:
        return True
    return False


def is_needs_more_data(response_text: str) -> dict | None:
    """
    Check if LLM returned a needs_more_data signal.
    Handles cases where JSON is embedded anywhere in the response text.
    """
    # Try to find JSON block anywhere in the response
    match = re.search(r'\{[^{}]*"needs_more_data"\s*:\s*true[^{}]*\}', response_text, re.IGNORECASE | re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if data.get("needs_more_data"):
                return data
        except json.JSONDecodeError:
            pass
    return None


def clean_response(response_text: str) -> str:
    """
    Strip any embedded JSON signal blocks from the response before showing to user.
    Also strips any leftover blank lines around where the JSON was.
    """
    cleaned = re.sub(
        r'\{[^{}]*"needs_more_data"\s*:\s*true[^{}]*\}',
        "",
        response_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Collapse multiple blank lines left behind
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# Phrases that mean the LLM is guessing or deferring instead of answering from context
_HALLUCINATION_PATTERNS = re.compile(
    r"(table[s]? (below|above|follows|mentioned)"
    r"|as (shown|mentioned|listed|given) (in|below|above)"
    r"|not specified in (the |this )?(provided )?context"
    r"|exact amount is not (specified|mentioned|available|provided)"
    r"|detailed (fees?|info|information).{0,40}available"
    r"|you (may|might|can|should) (want to )?check (the )?(official )?website"
    r"|contact (the )?college (for|directly)"
    r"|refer to the (official|college) website)",
    re.IGNORECASE,
)

def response_has_hallucination(text: str) -> bool:
    """Return True if the response contains deferral/hallucination weasel phrases."""
    return bool(_HALLUCINATION_PATTERNS.search(text))


def targeted_rescrape(scraper: CollegeScraper, college_name: str, search_query: str):
    """Re-scrape with a targeted query hint and add new chunks to DB."""
    print(f"\n🔍  Re-scraping for more info: '{search_query}' …")
    from scraper import scrape_via_duckduckgo, scrape_wikipedia, store_chunks

    row = scraper.conn.execute(
        "SELECT id FROM colleges WHERE name_lower = ?", (college_name.lower(),)
    ).fetchone()
    if not row:
        print("   Could not find college in DB for re-scrape.\n")
        return

    college_id = row[0]
    total_inserted = 0

    # 1. Try a targeted DuckDuckGo search with the specific query
    web_chunks = scrape_via_duckduckgo(f"{college_name} {search_query}")
    if web_chunks:
        total_inserted += store_chunks(scraper.conn, college_id, web_chunks)

    # 2. Also re-scrape Wikipedia in case we missed structured content
    wiki_chunks = scrape_wikipedia(college_name)
    if wiki_chunks:
        total_inserted += store_chunks(scraper.conn, college_id, wiki_chunks)

    if total_inserted > 0:
        print(f"   ✅ Added {total_inserted} new chunks to knowledge base.\n")
    else:
        print("   ⚠️  Could not find additional data online.\n")


# ── Main Chat Loop ────────────────────────────────────────────────────────────

def chat_loop(scraper: CollegeScraper, college_name: str):
    """Run the interactive chat loop for a given college."""
    print(f"\n💬  Chat started for: {college_name}")
    print("    (type 'switch' to change college, 'exit' to quit)\n")

    conversation: list[dict] = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            sys.exit(0)

        if not user_input:
            continue

        if user_input.lower() == "exit":
            print("Goodbye!")
            sys.exit(0)

        if user_input.lower() == "switch":
            return  # bubble up to main() to re-ask college name

        # Add user turn to history
        conversation.append({"role": "user", "content": user_input})

        # Keep history bounded
        if len(conversation) > MAX_HISTORY * 2:
            conversation = conversation[-(MAX_HISTORY * 2):]

        # Retrieve context
        hits = scraper.search(college_name, user_input, top_k=TOP_K)
        context = ""
        if hits:
            parts = [f"[{i}] ({h['section'].upper()} | {h['source']})\n{h['content']}"
                     for i, h in enumerate(hits, 1)]
            context = "\n\n".join(parts)

        # ── Proactive rescrape: if context is thin, fetch more before asking LLM ──
        if context_is_thin(hits, user_input):
            print(f"\n🔍  Context looks thin for this query — fetching more data …")
            targeted_rescrape(scraper, college_name, user_input)
            # Re-retrieve with freshly added chunks
            hits = scraper.search(college_name, user_input, top_k=TOP_K)
            if hits:
                parts = [f"[{i}] ({h['section'].upper()} | {h['source']})\n{h['content']}"
                         for i, h in enumerate(hits, 1)]
                context = "\n\n".join(parts)

        # Call LLM
        try:
            response_text = call_llm(college_name, conversation, context)
        except Exception as e:
            print(f"\n⚠️   LLM error: {e}\n")
            conversation.pop()  # remove failed user turn
            continue

        # Check if LLM flagged missing data (explicit JSON signal)
        signal = is_needs_more_data(response_text)

        # Also catch implicit hallucination / deferral phrases
        if not signal and response_has_hallucination(response_text):
            print(f"\n⚠️  Response contains vague/deferral phrases — triggering rescrape …")
            signal = {"needs_more_data": True, "search_query": f"{user_input} details"}

        if signal:
            search_query = signal.get("search_query", user_input)
            targeted_rescrape(scraper, college_name, search_query)

            # Retry with fresh context
            context = retrieve_context(scraper, college_name, user_input)
            try:
                response_text = call_llm(college_name, conversation, context)
            except Exception as e:
                print(f"\n⚠️   LLM error on retry: {e}\n")
                conversation.pop()
                continue

            # If still no data after rescrape — ask LLM to share whatever partial info it has
            if is_needs_more_data(response_text) or response_has_hallucination(response_text):
                partial_context = retrieve_context(scraper, college_name, user_input, top_k=TOP_K)
                partial_prompt = (
                    f"Context from knowledge base:\n"
                    f"───────────────────────────\n"
                    f"{partial_context if partial_context else '(No relevant chunks found)'}\n"
                    f"───────────────────────────\n\n"
                    f"The user asked: {user_input}\n\n"
                    f"Share whatever partial or related information is available in the context above. "
                    f"Be honest that the information may be incomplete. "
                    f"At the end, add exactly this note on a new line: "
                    f"'⚠️ For complete and accurate details, manual verification on the official website is recommended.'"
                )
                try:
                    fallback_messages = [
                        {"role": "system", "content": build_system_prompt(college_name)},
                        {"role": "user", "content": partial_prompt},
                    ]
                    fallback_resp = client.chat.completions.create(
                        model=MODEL, max_tokens=800, temperature=0.3, messages=fallback_messages
                    )
                    response_text = fallback_resp.choices[0].message.content
                except Exception:
                    response_text = (
                        f"I have limited information about this for {college_name}.\n\n"
                        f"⚠️ For complete and accurate details, manual verification on the official website is recommended."
                    )

        # Add assistant response to history (always store and show clean version)
        display_text = clean_response(response_text)
        conversation.append({"role": "assistant", "content": display_text})
        print(f"\n🤖  Assistant: {display_text}\n")


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    if not GROQ_API_KEY:
        print("❌  GROQ_API_KEY environment variable is not set.")
        print("    Set it with: set GROQ_API_KEY=your_key_here  (Windows)")
        print("                 export GROQ_API_KEY=your_key_here  (Mac/Linux)")
        print("    Get a free key at: https://console.groq.com")
        sys.exit(1)

    print_banner()
    scraper = CollegeScraper()

    try:
        while True:
            college_name = ask_college_name()
            result = build_knowledge_base(scraper, college_name)

            if result["status"] == "error":
                print(f"❌  Could not load data for '{college_name}'. Try a different name.\n")
                continue

            chat_loop(scraper, college_name)
            # If chat_loop returns, user typed 'switch'
            print("\n" + "─" * 50 + "\n")

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
