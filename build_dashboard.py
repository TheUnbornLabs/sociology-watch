#!/usr/bin/env python3
"""
Build a single self-contained dashboard.html from the SQLite DB.
All item data is embedded as JSON; no network needed to view it.
Standard library only.
"""
import os
import json
import sqlite3
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "data", "sociology.db")
CONFIG_PATH = os.path.join(HERE, "config.json")
OUT_PATH = os.path.join(HERE, "dashboard.html")
INDEX_PATH = os.path.join(HERE, "index.html")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_items():
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT url, title, summary, source_type, source_name,
               theme, language, published, collected_at
        FROM items
        ORDER BY collected_at DESC, id DESC
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def build():
    cfg = load_config()
    items = load_items()
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")

    theme_meta = {t["key"]: {"label": t["label"], "color": t["color"]} for t in cfg["themes"]}
    lang_meta = {l["code"]: {"label": l["label"], "flag": l.get("flag", "")} for l in cfg["languages"]}
    source_meta = {k: v.get("label", k.title()) for k, v in cfg["sources"].items()}

    payload = {
        "site_title": cfg.get("site_title", "Sociology Watch"),
        "site_tagline": cfg.get("site_tagline", ""),
        "generated": generated,
        "themes": theme_meta,
        "languages": lang_meta,
        "sources": source_meta,
        "items": items,
    }
    data_json = json.dumps(payload, ensure_ascii=False)

    html = HTML_TEMPLATE.replace("/*__DATA__*/", data_json)
    # Write both dashboard.html (canonical name) and index.html (GitHub Pages root).
    for path in (OUT_PATH, INDEX_PATH):
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
    return OUT_PATH


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Sociology Watch</title>
<style>
  :root {
    --bg: #0b0e14; --panel: #131823; --panel-2: #1a2030; --border: #232b3d;
    --text: #e6e9f0; --muted: #8b93a7; --accent: #6ea8fe; --chip: #1e2536;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "Noto Sans CJK JP", sans-serif;
  }
  header {
    position: sticky; top: 0; z-index: 10;
    background: linear-gradient(180deg, rgba(11,14,20,.98), rgba(11,14,20,.92));
    backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--border); padding: 18px 22px 14px;
  }
  .titlebar { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
  h1 { font-size: 22px; margin: 0; letter-spacing: .3px; }
  .tagline { color: var(--muted); font-size: 13px; }
  .meta { margin-left: auto; color: var(--muted); font-size: 12px; text-align: right; }
  .controls { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; align-items: center; }
  input[type=search] {
    flex: 1 1 240px; min-width: 200px; background: var(--panel-2);
    border: 1px solid var(--border); color: var(--text);
    padding: 9px 12px; border-radius: 9px; font-size: 14px;
  }
  select, button.refresh {
    background: var(--panel-2); border: 1px solid var(--border); color: var(--text);
    padding: 9px 12px; border-radius: 9px; font-size: 14px; cursor: pointer;
  }
  button.refresh { background: var(--accent); color: #08111f; border: none; font-weight: 600; }
  button.refresh:hover { filter: brightness(1.08); }
  button.refresh:disabled { opacity: .6; cursor: default; }
  .rowlabel { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .6px; margin: 16px 0 8px; }
  .chips { display: flex; gap: 8px; flex-wrap: wrap; }
  .chip {
    background: var(--chip); border: 1px solid var(--border); color: var(--text);
    padding: 6px 12px; border-radius: 999px; font-size: 13px; cursor: pointer; user-select: none;
    display: inline-flex; align-items: center; gap: 7px;
  }
  .chip .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
  .chip.active { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent) inset; }
  .chip .count { color: var(--muted); font-size: 11px; }
  main { padding: 18px 22px 60px; max-width: 1180px; margin: 0 auto; }
  .summary { color: var(--muted); font-size: 13px; margin-bottom: 14px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
  .card {
    background: var(--panel); border: 1px solid var(--border); border-radius: 13px;
    padding: 14px 15px; display: flex; flex-direction: column; gap: 9px;
    transition: border-color .15s, transform .15s;
  }
  .card:hover { border-color: #34405c; transform: translateY(-2px); }
  .card .top { display: flex; gap: 7px; flex-wrap: wrap; align-items: center; }
  .badge {
    font-size: 11px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border);
    color: var(--text); display: inline-flex; align-items: center; gap: 5px; white-space: nowrap;
  }
  .badge .dot { width: 8px; height: 8px; border-radius: 50%; }
  .badge.src { color: var(--muted); }
  .card a.title { color: var(--text); text-decoration: none; font-weight: 600; font-size: 15px; line-height: 1.35; }
  .card a.title:hover { color: var(--accent); }
  .card .desc { color: var(--muted); font-size: 13px; }
  .card .foot { color: var(--muted); font-size: 11.5px; margin-top: auto; display: flex; gap: 8px; }
  .empty { text-align: center; color: var(--muted); padding: 60px 0; }
  a.host { color: var(--accent); text-decoration: none; }
  .toast {
    position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%);
    background: var(--panel-2); border: 1px solid var(--border); color: var(--text);
    padding: 11px 18px; border-radius: 10px; font-size: 14px; opacity: 0;
    transition: opacity .25s; pointer-events: none; z-index: 50;
  }
  .toast.show { opacity: 1; }
  footer { color: var(--muted); font-size: 12px; text-align: center; padding: 24px; border-top: 1px solid var(--border); }
</style>
</head>
<body>
<header>
  <div class="titlebar">
    <h1 id="siteTitle">Sociology Watch</h1>
    <span class="tagline" id="siteTagline"></span>
    <span class="meta" id="metaInfo"></span>
  </div>
  <div class="controls">
    <input type="search" id="search" placeholder="Search titles & summaries…" />
    <select id="sortSel">
      <option value="collected">Newest collected</option>
      <option value="published">Newest published</option>
      <option value="title">Title A–Z</option>
    </select>
    <button class="refresh" id="refreshBtn" title="Refresh">↻ Refresh</button>
  </div>
  <div class="rowlabel">Themes</div>
  <div class="chips" id="themeChips"></div>
  <div class="rowlabel">Languages</div>
  <div class="chips" id="langChips"></div>
  <div class="rowlabel">Sources</div>
  <div class="chips" id="sourceChips"></div>
</header>
<main>
  <div class="summary" id="summary"></div>
  <div class="grid" id="grid"></div>
  <div class="empty" id="empty" style="display:none">No items match these filters.</div>
</main>
<footer id="footer"></footer>
<div class="toast" id="toast"></div>

<script id="payload" type="application/json">/*__DATA__*/</script>
<script>
const DATA = JSON.parse(document.getElementById("payload").textContent);
const state = { themes: new Set(), langs: new Set(), sources: new Set(), q: "", sort: "collected" };

document.getElementById("siteTitle").textContent = DATA.site_title;
document.getElementById("siteTagline").textContent = DATA.site_tagline || "";

function hostOf(url){ try { return new URL(url).hostname.replace(/^www\./,""); } catch(e){ return ""; } }
function fmtDate(s){
  if(!s) return "";
  const d = new Date(s);
  if(isNaN(d)) return s;
  return d.toLocaleDateString(undefined,{year:"numeric",month:"short",day:"numeric"});
}
function counts(field){
  const m = {};
  for(const it of DATA.items){ m[it[field]] = (m[it[field]]||0)+1; }
  return m;
}

function buildChips(containerId, meta, field, stateSet, opts={}){
  const cont = document.getElementById(containerId);
  const cnt = counts(field);
  cont.innerHTML = "";
  for(const key of Object.keys(meta)){
    if(opts.skipZero && !cnt[key]) continue;
    const m = meta[key];
    const chip = document.createElement("span");
    chip.className = "chip";
    const label = (m.flag? m.flag+" ":"") + (m.label||m);
    let dot = "";
    if(m.color){ dot = `<span class="dot" style="background:${m.color}"></span>`; }
    chip.innerHTML = `${dot}<span>${label}</span><span class="count">${cnt[key]||0}</span>`;
    chip.onclick = () => {
      if(stateSet.has(key)) stateSet.delete(key); else stateSet.add(key);
      chip.classList.toggle("active");
      render();
    };
    cont.appendChild(chip);
  }
}

function passes(it){
  if(state.themes.size && !state.themes.has(it.theme)) return false;
  if(state.langs.size && !state.langs.has(it.language)) return false;
  if(state.sources.size && !state.sources.has(it.source_type)) return false;
  if(state.q){
    const hay = (it.title+" "+(it.summary||"")).toLowerCase();
    if(!hay.includes(state.q)) return false;
  }
  return true;
}

function sortItems(arr){
  const s = state.sort;
  const cp = arr.slice();
  if(s === "title") cp.sort((a,b)=> a.title.localeCompare(b.title));
  else if(s === "published") cp.sort((a,b)=> (new Date(b.published||0)) - (new Date(a.published||0)));
  else cp.sort((a,b)=> (new Date(b.collected_at||0)) - (new Date(a.collected_at||0)));
  return cp;
}

function render(){
  const filtered = sortItems(DATA.items.filter(passes));
  const grid = document.getElementById("grid");
  const empty = document.getElementById("empty");
  grid.innerHTML = "";
  document.getElementById("summary").textContent =
    `${filtered.length} of ${DATA.items.length} items shown`;
  empty.style.display = filtered.length ? "none" : "block";

  const frag = document.createDocumentFragment();
  for(const it of filtered.slice(0, 600)){
    const tm = DATA.themes[it.theme] || {label: it.theme, color:"#888"};
    const lm = DATA.languages[it.language] || {label: it.language, flag:""};
    const sm = DATA.sources[it.source_type] || it.source_type;
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="top">
        <span class="badge"><span class="dot" style="background:${tm.color}"></span>${tm.label}</span>
        <span class="badge">${(lm.flag||"")} ${lm.label}</span>
        <span class="badge src">${sm}${it.source_name? " · "+it.source_name : ""}</span>
      </div>
      <a class="title" href="${it.url}" target="_blank" rel="noopener">${escapeHtml(it.title)}</a>
      ${it.summary? `<div class="desc">${escapeHtml(it.summary)}</div>` : ""}
      <div class="foot">
        <a class="host" href="${it.url}" target="_blank" rel="noopener">${hostOf(it.url)}</a>
        ${it.published? "· "+fmtDate(it.published) : ""}
      </div>`;
    frag.appendChild(card);
  }
  grid.appendChild(frag);
}

function escapeHtml(s){
  return (s||"").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

function showToast(msg){
  const t = document.getElementById("toast");
  t.textContent = msg; t.classList.add("show");
  setTimeout(()=> t.classList.remove("show"), 3200);
}

// Context-aware refresh: live-collect on localhost, else just reload.
const onLocalhost = ["localhost","127.0.0.1"].includes(location.hostname);
document.getElementById("refreshBtn").onclick = async () => {
  const btn = document.getElementById("refreshBtn");
  if(onLocalhost){
    btn.disabled = true; btn.textContent = "↻ Collecting…";
    showToast("Running a live collection — this can take a minute…");
    try {
      const r = await fetch("/collect", {method:"POST"});
      const j = await r.json();
      showToast(`Done: ${j.new_items} new items. Reloading…`);
      setTimeout(()=> location.reload(), 1200);
    } catch(e){
      btn.disabled = false; btn.textContent = "↻ Refresh";
      showToast("Live collect failed (is server.py running?). Try reload.");
    }
  } else {
    showToast("Loading the latest daily copy…");
    setTimeout(()=> location.reload(), 500);
  }
};

document.getElementById("search").addEventListener("input", e => {
  state.q = e.target.value.trim().toLowerCase(); render();
});
document.getElementById("sortSel").addEventListener("change", e => {
  state.sort = e.target.value; render();
});

buildChips("themeChips", DATA.themes, "theme", state.themes);
buildChips("langChips", DATA.languages, "language", state.langs, {skipZero:true});
const srcMetaObj = {}; for(const k of Object.keys(DATA.sources)) srcMetaObj[k] = {label: DATA.sources[k]};
buildChips("sourceChips", srcMetaObj, "source_type", state.sources, {skipZero:true});

document.getElementById("metaInfo").innerHTML =
  `Updated ${fmtDate(DATA.generated)} · ${new Date(DATA.generated).toLocaleTimeString()}<br>${DATA.items.length} items`;
document.getElementById("footer").textContent =
  `Sociology Watch · generated ${DATA.generated} · free-source aggregator (Reddit + Google News)`;

render();
</script>
</body>
</html>"""


if __name__ == "__main__":
    path = build()
    print("Wrote", path)
