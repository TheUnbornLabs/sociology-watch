# Sociology Watch

A tiny tool that gathers fresh items about sociology topics from across the
internet every day, sorts them by theme, and shows them on a clean dashboard you
can share as a public link.

It uses **only free, no-account sources** (Reddit + Google News), so it works
immediately with no API keys. Everything runs on Python's standard library — no
`pip install` needed.

---

## What it collects

- **Themes** (each is its own tab/filter): Social Inequality, Race & Ethnicity,
  Gender & Sexuality, Work & Labour, Migration, Social Movements.
- **Languages**: English, Spanish, German, French, Portuguese, Japanese — each
  uses its *own* translated search terms and that country's news edition.
- **Sources**: Reddit (per-theme subreddits), Google News, and academic-flavoured
  news queries. Optional YouTube / X are supported behind config flags + keys.

All items are stored in a local SQLite database (`data/sociology.db`),
de-duplicated by URL, so history accumulates over time.

---

## Run it on your PC (Windows)

Open PowerShell in this folder and run:

```powershell
# 1. Collect today's items (takes ~2 minutes)
python collect.py

# 2. Start the local dashboard
python server.py
```

Then open **http://localhost:8000** in your browser.

- The **↻ Refresh** button does a *live* collection when you're on localhost.
- Filter by theme, language, and source; use the search box; sort newest-first.

You don't even need the server to view results — `dashboard.html` is a single
self-contained file you can double-click to open.

---

## Make it update automatically + share a link

This repo includes a GitHub Actions workflow (`.github/workflows/daily.yml`) that
runs the collector **in the cloud every day** and commits the refreshed data back,
so the site stays current **without your PC being on**. Hosted on GitHub Pages,
anyone can open the link on their phone — no install, no steps.

See `DEPLOY.md` for the one-time setup (it's mostly automated via the GitHub CLI;
you just do a single browser login).

On the hosted site, the ↻ button simply reloads the latest daily snapshot.

---

## Customizing

Everything lives in **`config.json`**:

- `themes` — add/remove themes, their colours, subreddits, and per-language queries.
- `languages` — toggle `"enabled": true/false`, or add a new language + news edition.
- `sources` — turn sources on/off; add API keys for YouTube / X if you want them.

**Tip:** sociology terms are broad, so news/Reddit results are noisier than a
narrow topic would be. To sharpen relevance, tighten the queries in `config.json`
(e.g. add quoted phrases `"social inequality"` or `site:` filters).

---

## Files

| File | What it does |
|------|--------------|
| `config.json` | All settings: themes, languages, queries, sources, keys |
| `collect.py` | The collector (stdlib only). Fetches, de-dupes, stores, rebuilds dashboard |
| `build_dashboard.py` | Turns the database into `dashboard.html` / `index.html` |
| `server.py` | Local web server with the live-refresh endpoint |
| `data/sociology.db` | SQLite database of all collected items |
| `dashboard.html` / `index.html` | The shareable dashboard (data embedded) |
| `.github/workflows/daily.yml` | Daily cloud collection + auto-commit |

---

## Known limitations (honest notes)

- **Reddit rate-limits** rapid RSS requests (HTTP 429). The collector paces
  Reddit calls and retries with backoff, but from shared cloud IPs (GitHub
  Actions) Reddit may still throttle some feeds. News/academic are the bulk of
  the data and are reliable.
- **Relevance**: broad sociology queries surface some off-topic news. Tighten
  queries in `config.json` if needed.
- **Google News** returns redirect URLs (`news.google.com/...`) that resolve to
  the publisher when clicked — expected behaviour.
