"""
scraper.py — College Data Scraping Module
==========================================
Scrapes college information from the web and stores structured
chunks into a local SQLite vector store for RAG retrieval.

Usage:
    from scraper import CollegeScraper
    scraper = CollegeScraper()
    result = scraper.scrape_and_store("IIT Bombay")
    print(result)
"""

import re
import time
import json
import hashlib
import sqlite3
import logging
from typing import Optional
from urllib.parse import quote, quote_plus, urlparse

import requests
import numpy as np
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

DB_PATH = "college_rag.db"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Sections we want to extract from college pages
TARGET_SECTIONS = [
    "about", "overview", "history", "ranking", "admission",
    "eligibility", "fees", "courses", "programs", "departments",
    "placement", "campus", "facilities", "scholarship", "hostel",
    "contact", "location", "accreditation", "faculty",
]


# ─────────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────────

def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Create tables if they don't exist."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS colleges (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE NOT NULL,
            name_lower  TEXT NOT NULL,
            scraped_at  TEXT NOT NULL,
            meta        TEXT          -- JSON blob: official_url, wikipedia_url, etc.
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            college_id  INTEGER NOT NULL REFERENCES colleges(id),
            section     TEXT,          -- e.g. "admissions", "fees"
            source      TEXT,          -- e.g. "wikipedia", "official"
            content     TEXT NOT NULL,
            embedding   BLOB,          -- numpy float32 array serialised as bytes
            chunk_hash  TEXT UNIQUE,   -- dedup
            FOREIGN KEY (college_id) REFERENCES colleges(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_college ON chunks(college_id)")
    conn.commit()
    return conn


# ─────────────────────────────────────────────
# EMBEDDING
# ─────────────────────────────────────────────

class SimpleEmbedder:
    """
    Lightweight bag-of-words TF-IDF-like embedder.
    Produces a fixed-size 512-dim float32 vector via character n-gram hashing.
    """
    DIM = 512

    def embed(self, text: str) -> np.ndarray:
        text = text.lower()
        tokens = [text[i:i+3] for i in range(len(text) - 2)]
        vec = np.zeros(self.DIM, dtype=np.float32)
        for t in tokens:
            idx = int(hashlib.md5(t.encode()).hexdigest(), 16) % self.DIM
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        return [self.embed(t) for t in texts]


embedder = SimpleEmbedder()


def vec_to_blob(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()

def blob_to_vec(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)


# ─────────────────────────────────────────────
# TEXT CHUNKING
# ─────────────────────────────────────────────

def chunk_text(text: str, max_words: int = 150, overlap: int = 30) -> list[str]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunk = " ".join(words[start:end])
        if len(chunk.strip()) > 40:
            chunks.append(chunk.strip())
        if end == len(words):
            break
        start += max_words - overlap
    return chunks


def detect_section(text: str, heading: str = "") -> str:
    """Guess a section label from heading or content."""
    combined = (heading + " " + text[:200]).lower()
    for kw in TARGET_SECTIONS:
        if kw in combined:
            return kw
    return "general"


# ─────────────────────────────────────────────
# SCRAPERS
# ─────────────────────────────────────────────

def _get(url: str, timeout: int = 10) -> Optional[requests.Response]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning(f"GET failed {url}: {e}")
        return None


def _clean(text: str) -> str:
    """Normalise whitespace."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# Phrases that indicate a chunk is a useless table-reference artefact
_JUNK_PATTERNS = re.compile(
    r"(see (the )?table|refer (to )?table|as (shown|mentioned|given|listed) (in|below|above)"
    r"|table (below|above|follows)|click here|download (the )?brochure"
    r"|for more (details|info)|visit (the )?website|contact (the )?college)",
    re.IGNORECASE,
)

def _is_junk_chunk(text: str) -> bool:
    """Return True if a chunk is too vague to be useful for RAG."""
    if len(text.split()) < 8:
        return True
    if _JUNK_PATTERNS.search(text):
        return True
    return False


def table_to_text(table_tag) -> list[str]:
    """
    Convert an HTML <table> into human-readable text chunks.
    Each data row becomes a sentence: 'Header1: val1 | Header2: val2 …'
    Returns a list of text strings (one per row).
    """
    rows = table_tag.find_all("tr")
    if not rows:
        return []

    # Try to extract headers from first row
    header_cells = rows[0].find_all(["th", "td"])
    headers = [_clean(c.get_text(" ", strip=True)) for c in header_cells]
    has_headers = any(h for h in headers)

    chunks = []
    data_rows = rows[1:] if has_headers else rows
    for row in data_rows:
        cells = row.find_all(["td", "th"])
        values = [_clean(c.get_text(" ", strip=True)) for c in cells]
        if not any(values):
            continue
        if has_headers and len(headers) == len(values):
            line = " | ".join(f"{h}: {v}" for h, v in zip(headers, values) if v)
        else:
            line = " | ".join(v for v in values if v)
        if len(line) > 20:
            chunks.append(line)

    return chunks


def scrape_wikipedia(college_name: str) -> list[dict]:
    """Pull the Wikipedia article for the college."""
    # Step 1: Use the Wikipedia search API to get the best matching title
    search_url = (
        "https://en.wikipedia.org/w/api.php"
        f"?action=query&list=search&srsearch={quote_plus(college_name)}"
        "&format=json&srlimit=3"
    )
    r = _get(search_url)
    if not r:
        return []

    results = r.json().get("query", {}).get("search", [])
    if not results:
        log.warning("  Wikipedia: no search results found")
        return []

    title = results[0]["title"]

    # Step 2: Build the Wikipedia URL using the EXACT title from the API
    # Wikipedia URLs use underscores, and quote() (not quote_plus) for special chars
    page_url = "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="")
    log.info(f"  Wikipedia: {page_url}")

    r2 = _get(page_url)
    if not r2:
        return []

    soup = BeautifulSoup(r2.text, "lxml")
    for tag in soup.find_all(["sup", "style", "script", "nav"]):
        tag.decompose()

    chunks_out = []
    content_div = soup.find("div", {"id": "mw-content-text"})
    if not content_div:
        log.warning("  Wikipedia: could not find content div")
        return []

    current_section = "overview"
    for elem in content_div.find_all(["h2", "h3", "p", "ul", "li", "table"]):
        if elem.name in ("h2", "h3"):
            current_section = detect_section("", elem.get_text())
        elif elem.name == "table":
            for row_text in table_to_text(elem):
                if not _is_junk_chunk(row_text):
                    for c in chunk_text(row_text):
                        chunks_out.append({
                            "source": "wikipedia",
                            "section": current_section,
                            "content": c,
                            "url": page_url,
                        })
        else:
            text = _clean(elem.get_text(" ", strip=True))
            if len(text) > 60 and not _is_junk_chunk(text):
                for c in chunk_text(text):
                    chunks_out.append({
                        "source": "wikipedia",
                        "section": current_section,
                        "content": c,
                        "url": page_url,
                    })

    log.info(f"  Wikipedia → {len(chunks_out)} raw chunks")
    return chunks_out


def scrape_via_duckduckgo(college_name: str, site_hint: str = "") -> list[dict]:
    """
    Use DuckDuckGo HTML search to find relevant pages, then scrape them.
    Robust link extraction handles multiple DDG result HTML formats.
    """
    query = f"{college_name} {site_hint} official admission fees courses".strip()
    encoded = quote_plus(query)
    search_url = f"https://html.duckduckgo.com/html/?q={encoded}"

    r = _get(search_url)
    if not r:
        return []

    soup = BeautifulSoup(r.text, "lxml")

    # DDG embeds real URLs in the href of result links, but sometimes behind
    # a redirect param like ?uddg=<real_url>. Extract both styles.
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Direct links
        if href.startswith("http") and "duckduckgo.com" not in href:
            links.append(href)
        # Redirect links: ?uddg=https%3A%2F%2F...
        elif "uddg=" in href:
            match = re.search(r"uddg=(https?[^&]+)", href)
            if match:
                from urllib.parse import unquote
                links.append(unquote(match.group(1)))

    # Deduplicate while preserving order
    seen = set()
    unique_links = []
    for l in links:
        if l not in seen:
            seen.add(l)
            unique_links.append(l)

    log.info(f"  DDG found {len(unique_links)} candidate links")

    chunks_out = []
    scraped = 0
    for link in unique_links:
        if scraped >= 3:
            break
        domain = urlparse(link).netloc
        if any(skip in domain for skip in ["facebook", "twitter", "instagram", "youtube", "duckduckgo"]):
            continue

        log.info(f"  Scraping: {link}")
        page_r = _get(link, timeout=12)
        if not page_r:
            continue

        page_soup = BeautifulSoup(page_r.text, "lxml")
        for tag in page_soup.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        current_section = "general"
        for elem in page_soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "table"]):
            if elem.name in ("h1", "h2", "h3", "h4"):
                current_section = detect_section("", elem.get_text())
            elif elem.name == "table":
                for row_text in table_to_text(elem):
                    if not _is_junk_chunk(row_text):
                        for c in chunk_text(row_text):
                            chunks_out.append({
                                "source": "web:" + domain,
                                "section": current_section,
                                "content": c,
                                "url": link,
                            })
            else:
                text = _clean(elem.get_text(" ", strip=True))
                if len(text) > 60 and not _is_junk_chunk(text):
                    for c in chunk_text(text):
                        chunks_out.append({
                            "source": "web:" + domain,
                            "section": current_section,
                            "content": c,
                            "url": link,
                        })
        scraped += 1
        time.sleep(0.8)  # polite crawl delay

    log.info(f"  Web scrape → {len(chunks_out)} raw chunks")
    return chunks_out


# ─────────────────────────────────────────────
# DEDUPLICATION & STORAGE
# ─────────────────────────────────────────────

def _chunk_hash(college_id: int, content: str) -> str:
    key = f"{college_id}|{content}"
    return hashlib.sha256(key.encode()).hexdigest()


def store_chunks(conn: sqlite3.Connection, college_id: int, raw_chunks: list[dict]) -> int:
    """Embed and store chunks; return count of new rows inserted."""
    inserted = 0
    texts = [c["content"] for c in raw_chunks]
    embeddings = embedder.embed_batch(texts)

    for chunk, emb in zip(raw_chunks, embeddings):
        h = _chunk_hash(college_id, chunk["content"])
        try:
            conn.execute(
                """
                INSERT INTO chunks (college_id, section, source, content, embedding, chunk_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    college_id,
                    chunk.get("section", "general"),
                    chunk.get("source", "unknown"),
                    chunk["content"],
                    vec_to_blob(emb),
                    h,
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass  # duplicate, skip

    conn.commit()
    return inserted


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────

class CollegeScraper:
    def __init__(self, db_path: str = DB_PATH):
        self.conn = init_db(db_path)
        log.info(f"Database ready: {db_path}")

    def _get_or_create_college(self, name: str) -> tuple[int, bool]:
        """Return (college_id, is_new)."""
        row = self.conn.execute(
            "SELECT id FROM colleges WHERE name_lower = ?", (name.lower(),)
        ).fetchone()
        if row:
            return row[0], False

        from datetime import datetime
        self.conn.execute(
            "INSERT INTO colleges (name, name_lower, scraped_at, meta) VALUES (?, ?, ?, ?)",
            (name, name.lower(), datetime.utcnow().isoformat(), "{}"),
        )
        self.conn.commit()
        college_id = self.conn.execute(
            "SELECT id FROM colleges WHERE name_lower = ?", (name.lower(),)
        ).fetchone()[0]
        return college_id, True

    def is_already_scraped(self, name: str) -> bool:
        row = self.conn.execute(
            "SELECT id FROM colleges WHERE name_lower = ?", (name.lower(),)
        ).fetchone()
        if not row:
            return False
        count = self.conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE college_id = ?", (row[0],)
        ).fetchone()[0]
        return count > 0

    def scrape_and_store(self, college_name: str, force_refresh: bool = False) -> dict:
        """
        Main entry point.
        Returns a summary dict with status and chunk counts.
        """
        college_name = college_name.strip()
        log.info(f"=== Scraping: {college_name} ===")

        if self.is_already_scraped(college_name) and not force_refresh:
            college_id = self.conn.execute(
                "SELECT id FROM colleges WHERE name_lower = ?", (college_name.lower(),)
            ).fetchone()[0]
            count = self.conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE college_id = ?", (college_id,)
            ).fetchone()[0]
            log.info(f"  Already in DB ({count} chunks). Use force_refresh=True to re-scrape.")
            return {
                "status": "cached",
                "college": college_name,
                "chunks": count,
                "message": f"Data already available ({count} chunks). Ready for Q&A!",
            }

        college_id, _ = self._get_or_create_college(college_name)

        all_chunks = []

        # 1. Wikipedia
        wiki_chunks = scrape_wikipedia(college_name)
        all_chunks.extend(wiki_chunks)

        # 2. General web search
        web_chunks = scrape_via_duckduckgo(college_name)
        all_chunks.extend(web_chunks)

        if not all_chunks:
            return {
                "status": "error",
                "college": college_name,
                "chunks": 0,
                "message": "Could not fetch any data. Check network or college name.",
            }

        inserted = store_chunks(self.conn, college_id, all_chunks)
        total = self.conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE college_id = ?", (college_id,)
        ).fetchone()[0]

        log.info(f"  Stored {inserted} new chunks (total: {total})")

        sources = list({c["source"] for c in all_chunks})
        self.conn.execute(
            "UPDATE colleges SET meta = ? WHERE id = ?",
            (json.dumps({"sources": sources, "raw_scraped": len(all_chunks)}), college_id),
        )
        self.conn.commit()

        return {
            "status": "success",
            "college": college_name,
            "chunks": total,
            "sources": sources,
            "message": f"Scraped and stored {total} knowledge chunks from {len(sources)} source(s). Ready for Q&A!",
        }

    def list_colleges(self) -> list[dict]:
        """List all colleges currently in the DB."""
        rows = self.conn.execute(
            "SELECT name, scraped_at, meta FROM colleges"
        ).fetchall()
        result = []
        for name, scraped_at, meta_str in rows:
            cid = self.conn.execute(
                "SELECT id FROM colleges WHERE name = ?", (name,)
            ).fetchone()[0]
            count = self.conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE college_id = ?", (cid,)
            ).fetchone()[0]
            result.append({
                "college": name,
                "scraped_at": scraped_at,
                "chunks": count,
                "meta": json.loads(meta_str or "{}"),
            })
        return result

    def get_chunks(self, college_name: str, section: Optional[str] = None) -> list[dict]:
        """Retrieve all stored chunks for a college (optionally filtered by section)."""
        row = self.conn.execute(
            "SELECT id FROM colleges WHERE name_lower = ?", (college_name.lower(),)
        ).fetchone()
        if not row:
            return []
        college_id = row[0]

        if section:
            rows = self.conn.execute(
                "SELECT section, source, content FROM chunks WHERE college_id = ? AND section = ?",
                (college_id, section),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT section, source, content FROM chunks WHERE college_id = ?",
                (college_id,),
            ).fetchall()

        return [{"section": r[0], "source": r[1], "content": r[2]} for r in rows]

    def search(self, college_name: str, query: str, top_k: int = 5) -> list[dict]:
        """
        Vector similarity search: return top-k chunks most relevant to `query`.
        This is the retrieval step for RAG.
        """
        row = self.conn.execute(
            "SELECT id FROM colleges WHERE name_lower = ?", (college_name.lower(),)
        ).fetchone()
        if not row:
            return []
        college_id = row[0]

        query_vec = embedder.embed(query)

        rows = self.conn.execute(
            "SELECT section, source, content, embedding FROM chunks WHERE college_id = ?",
            (college_id,),
        ).fetchall()

        scored = []
        for section, source, content, emb_blob in rows:
            if emb_blob:
                chunk_vec = blob_to_vec(emb_blob)
                score = float(np.dot(query_vec, chunk_vec))
                scored.append((score, section, source, content))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            {"score": s, "section": sec, "source": src, "content": cnt}
            for s, sec, src, cnt in scored[:top_k]
        ]

    def close(self):
        self.conn.close()


# ─────────────────────────────────────────────
# CLI TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    college = sys.argv[1] if len(sys.argv) > 1 else "Indian Institute of Technology Bombay"
    scraper = CollegeScraper()
    result = scraper.scrape_and_store(college)
    print(json.dumps(result, indent=2))

    print("\n--- Sample search: 'admission process' ---")
    hits = scraper.search(college, "admission process", top_k=3)
    for h in hits:
        print(f"[{h['section']}] {h['content'][:200]}\n")

    scraper.close()