#!/usr/bin/env python3
"""
Sociology Watch -- daily collector.

Pulls fresh items about sociology themes from FREE, no-API-key sources
(Reddit RSS, Google News RSS, academic-flavoured news queries), stores them
de-duplicated in a local SQLite DB, and (when run as the main module) rebuilds
the self-contained dashboard.html.

Standard library ONLY. No pip installs required.
"""

import sys
import os
import io
import json
import time
import sqlite3
import logging
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# UTF-8 safety: make sure non-Latin scripts (e.g. Japanese) never crash logging
# or stdout on Windows consoles that default to cp1252.
# ---------------------------------------------------------------------------
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
DB_PATH = os.path.join(HERE, "data", "sociology.db")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("sociology-watch")


# ---------------------------------------------------------------------------
# Config + DB
# ---------------------------------------------------------------------------
def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            url          TEXT UNIQUE NOT NULL,
            title        TEXT NOT NULL,
            summary      TEXT,
            source_type  TEXT NOT NULL,
            source_name  TEXT,
            theme        TEXT NOT NULL,
            language     TEXT NOT NULL,
            published    TEXT,
            collected_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_theme ON items(theme)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lang ON items(language)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_published ON items(published)")
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# HTTP + feed parsing
# ---------------------------------------------------------------------------
def fetch_url(url, cfg, retries=0):
    """Fetch a URL. On HTTP 429/503, back off (honouring Retry-After) and retry."""
    headers = {
        "User-Agent": cfg["collection"]["user_agent"],
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        "Accept-Language": "en, *;q=0.5",
    }
    timeout = cfg["collection"]["request_timeout_seconds"]
    attempt = 0
    while True:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < retries:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    wait = float(retry_after)
                except (TypeError, ValueError):
                    wait = 4.0 * (2 ** attempt)  # 4s, 8s, 16s ...
                wait = min(wait, 30.0)
                log.info("    %s -> backing off %.0fs (attempt %d/%d)", exc.code, wait, attempt + 1, retries)
                time.sleep(wait)
                attempt += 1
                continue
            raise


def _localname(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _find_text(elem, *names):
    for child in elem:
        if _localname(child.tag).lower() in names:
            return (child.text or "").strip()
    return ""


def _find_link(elem):
    # RSS: <link>http...</link>  ;  Atom: <link href="http..." rel="alternate"/>
    fallback = ""
    for child in elem:
        if _localname(child.tag).lower() != "link":
            continue
        href = child.get("href")
        if href:
            rel = (child.get("rel") or "alternate").lower()
            if rel == "alternate":
                return href.strip()
            fallback = fallback or href.strip()
        elif child.text:
            return child.text.strip()
    return fallback


def strip_html(text, limit=320):
    if not text:
        return ""
    out = []
    depth = 0
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">":
            if depth:
                depth -= 1
        elif depth == 0:
            out.append(ch)
    import html as _html
    cleaned = _html.unescape("".join(out)).strip()
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > limit:
        cleaned = cleaned[: limit - 1].rstrip() + "…"
    return cleaned


def parse_feed(raw, max_items):
    """Parse RSS 2.0 or Atom into a list of dicts. Returns [] on parse failure."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        log.warning("    feed parse error: %s", exc)
        return []

    entries = []
    for elem in root.iter():
        if _localname(elem.tag).lower() in ("item", "entry"):
            entries.append(elem)

    results = []
    for elem in entries[:max_items]:
        title = _find_text(elem, "title")
        link = _find_link(elem)
        summary = _find_text(elem, "description", "summary", "content")
        published = _find_text(elem, "pubdate", "published", "updated", "date")
        if not title or not link:
            continue
        results.append(
            {
                "title": strip_html(title, 240),
                "url": link,
                "summary": strip_html(summary, 320),
                "published": published,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Source builders
# ---------------------------------------------------------------------------
def google_news_url(query, edition):
    q = urllib.parse.quote(query)
    return (
        "https://news.google.com/rss/search?q="
        f"{q}&hl={edition['hl']}&gl={edition['gl']}&ceid={edition['ceid']}"
    )


def reddit_url(subreddit, time_window):
    return f"https://www.reddit.com/r/{subreddit}/.rss?sort=new&t={time_window}"


# ---------------------------------------------------------------------------
# Persisting
# ---------------------------------------------------------------------------
def save_items(conn, items, *, source_type, source_name, theme, language):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inserted = 0
    for it in items:
        try:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO items
                    (url, title, summary, source_type, source_name,
                     theme, language, published, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    it["url"],
                    it["title"],
                    it.get("summary", ""),
                    source_type,
                    source_name,
                    theme,
                    language,
                    it.get("published", ""),
                    now,
                ),
            )
            inserted += cur.rowcount
        except sqlite3.Error as exc:
            log.warning("    db insert error: %s", exc)
    conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# Per-source collectors (each isolated so one outage never stops the rest)
# ---------------------------------------------------------------------------
def collect_feed(conn, cfg, url, *, source_type, source_name, theme, language, stats,
                 delay=None, retries=0):
    label = f"[{source_type}/{language}/{theme}] {source_name}"
    try:
        raw = fetch_url(url, cfg, retries=retries)
        items = parse_feed(raw, cfg["collection"]["max_items_per_feed"])
        new = save_items(
            conn,
            items,
            source_type=source_type,
            source_name=source_name,
            theme=theme,
            language=language,
        )
        stats["fetched"] += 1
        stats["new"] += new
        log.info("  ok   %-46s  %2d found, %2d new", label, len(items), new)
    except urllib.error.HTTPError as exc:
        stats["failed"] += 1
        log.warning("  FAIL %-46s  HTTP %s", label, exc.code)
    except Exception as exc:  # noqa: BLE001 - isolate every source
        stats["failed"] += 1
        log.warning("  FAIL %-46s  %s", label, exc)
    finally:
        time.sleep(delay if delay is not None else cfg["collection"]["polite_delay_seconds"])


def run_collection(cfg, conn):
    stats = {"fetched": 0, "new": 0, "failed": 0}
    themes = cfg["themes"]
    langs = [l for l in cfg["languages"] if l.get("enabled")]
    sources = cfg["sources"]
    tw = cfg["collection"]["reddit_time_window"]

    # --- Reddit (English subreddits; language-agnostic, tagged 'en') ---
    # Reddit rate-limits rapid RSS hits, so we pace these and retry on 429.
    if sources["reddit"]["enabled"]:
        log.info("Reddit ...")
        reddit_delay = cfg["collection"].get("reddit_delay_seconds", 3.0)
        for theme in themes:
            for sub in theme.get("subreddits", []):
                collect_feed(
                    conn, cfg, reddit_url(sub, tw),
                    source_type="reddit", source_name=f"r/{sub}",
                    theme=theme["key"], language="en", stats=stats,
                    delay=reddit_delay, retries=4,
                )

    # --- Google News, per language x theme ---
    if sources["news"]["enabled"]:
        log.info("Google News ...")
        for lang in langs:
            for theme in themes:
                q = theme["queries"].get(lang["code"])
                if not q:
                    continue
                collect_feed(
                    conn, cfg, google_news_url(q, lang["news_edition"]),
                    source_type="news", source_name="Google News",
                    theme=theme["key"], language=lang["code"], stats=stats,
                )

    # --- Academic-flavoured news query, per language x theme ---
    if sources["academic"]["enabled"]:
        log.info("Academic mentions ...")
        academic_terms = {
            "en": "(research OR study OR sociologist OR university OR journal)",
            "es": "(investigación OR estudio OR sociólogo OR universidad)",
            "de": "(Forschung OR Studie OR Soziologe OR Universität)",
            "fr": "(recherche OR étude OR sociologue OR université)",
            "pt": "(pesquisa OR estudo OR sociólogo OR universidade)",
            "ja": "(研究 OR 調査 OR 社会学者 OR 大学)",
        }
        for lang in langs:
            terms = academic_terms.get(lang["code"], academic_terms["en"])
            for theme in themes:
                q = theme["queries"].get(lang["code"])
                if not q:
                    continue
                collect_feed(
                    conn, cfg, google_news_url(f"{q} {terms}", lang["news_edition"]),
                    source_type="academic", source_name="Academic mentions",
                    theme=theme["key"], language=lang["code"], stats=stats,
                )

    # --- Optional sources behind flags + keys ---
    if sources.get("youtube", {}).get("enabled"):
        collect_youtube(conn, cfg, stats)
    else:
        log.info("YouTube ... skipped (disabled / no API key)")

    if sources.get("twitter", {}).get("enabled"):
        log.info("X/Twitter ... enabled in config but collector not implemented; skipping")
    else:
        log.info("X/Twitter ... skipped (disabled / no token)")

    return stats


def collect_youtube(conn, cfg, stats):
    """Optional: YouTube Data API v3 search. Only runs if enabled + api_key set."""
    key = cfg["sources"]["youtube"].get("api_key", "").strip()
    if not key:
        log.info("YouTube ... enabled but api_key empty; skipping")
        return
    log.info("YouTube ...")
    langs = [l for l in cfg["languages"] if l.get("enabled")]
    for lang in langs:
        for theme in cfg["themes"]:
            q = theme["queries"].get(lang["code"])
            if not q:
                continue
            params = urllib.parse.urlencode({
                "part": "snippet", "q": q, "type": "video",
                "order": "date", "maxResults": 10,
                "relevanceLanguage": lang["code"], "key": key,
            })
            url = f"https://www.googleapis.com/youtube/v3/search?{params}"
            try:
                raw = fetch_url(url, cfg)
                data = json.loads(raw)
                items = []
                for entry in data.get("items", []):
                    vid = entry.get("id", {}).get("videoId")
                    sn = entry.get("snippet", {})
                    if not vid:
                        continue
                    items.append({
                        "title": sn.get("title", ""),
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "summary": sn.get("description", ""),
                        "published": sn.get("publishedAt", ""),
                    })
                new = save_items(conn, items, source_type="youtube",
                                 source_name="YouTube", theme=theme["key"],
                                 language=lang["code"])
                stats["fetched"] += 1
                stats["new"] += new
                log.info("  ok   YouTube %s/%s  %d new", lang["code"], theme["key"], new)
            except Exception as exc:  # noqa: BLE001
                stats["failed"] += 1
                log.warning("  FAIL YouTube %s/%s  %s", lang["code"], theme["key"], exc)
            time.sleep(cfg["collection"]["polite_delay_seconds"])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    started = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info("Sociology Watch collection starting %s", started.isoformat(timespec="seconds"))
    cfg = load_config()
    conn = init_db()
    stats = run_collection(cfg, conn)

    total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    conn.close()

    log.info("-" * 60)
    log.info("Feeds fetched OK: %d   |   failed: %d", stats["fetched"], stats["failed"])
    log.info("New items this run: %d   |   total in DB: %d", stats["new"], total)

    # Rebuild the static dashboard from the DB.
    try:
        import build_dashboard
        build_dashboard.build()
        log.info("dashboard.html rebuilt.")
    except Exception as exc:  # noqa: BLE001
        log.warning("dashboard build failed: %s", exc)

    log.info("Done in %.1fs", (datetime.now(timezone.utc) - started).total_seconds())


if __name__ == "__main__":
    main()
