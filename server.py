#!/usr/bin/env python3
"""
Tiny local server for Sociology Watch.

- Serves dashboard.html at /  (and any static file in this folder)
- POST /collect  -> runs a live collection, rebuilds the dashboard, returns JSON

Standard library only. Run:  python server.py   then open http://localhost:8000
"""
import os
import sys
import json
import http.server
import socketserver

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8000"))

for _s in ("stdout", "stderr"):
    _stream = getattr(sys, _s, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def do_GET(self):
        if self.path in ("/", ""):
            self.path = "/dashboard.html"
        return super().do_GET()

    def do_POST(self):
        if self.path.rstrip("/") == "/collect":
            self.handle_collect()
        else:
            self.send_error(404, "Not found")

    def handle_collect(self):
        # Run the collector in-process so the user needs no extra terminal.
        sys.path.insert(0, HERE)
        try:
            import importlib
            import collect as collector
            importlib.reload(collector)
            cfg = collector.load_config()
            conn = collector.init_db()
            stats = collector.run_collection(cfg, conn)
            total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            conn.close()
            import build_dashboard
            importlib.reload(build_dashboard)
            build_dashboard.build()
            body = json.dumps({
                "ok": True,
                "new_items": stats["new"],
                "feeds_ok": stats["fetched"],
                "feeds_failed": stats["failed"],
                "total": total,
            }).encode("utf-8")
            self.send_response(200)
        except Exception as exc:  # noqa: BLE001
            body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
            self.send_response(500)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("  [server] " + (fmt % args) + "\n")


def main():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Sociology Watch server running -> http://localhost:{PORT}")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
