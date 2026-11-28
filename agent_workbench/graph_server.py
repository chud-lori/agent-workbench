"""Read-only web view of the brain graph: a localhost server, or one self-contained HTML export."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import webbrowser
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import graph
from .brain import _fts_query
from .config import WorkbenchConfig

WEB_DIR = Path(__file__).resolve().parent / "web"
VENDOR_SCRIPT = "vendor/force-graph.min.js"
STATIC = {
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    f"/{VENDOR_SCRIPT}": (VENDOR_SCRIPT, "text/javascript; charset=utf-8"),
}
# force-graph injects two <style> elements at load, empty first and then filled; these
# hashes (the empty string, then each stylesheet) let CSP allow exactly those.
VENDOR_STYLE_HASHES = (
    "'sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU='",
    "'sha256-jtRRMYY2VbEXuBKbHvqM1/fPT8vazFrEooXdvwUK4y8='",
    "'sha256-9xjtvxMT1ApHlgn9ohbh2FNfvK5Tqtzy94BjfXBeMSY='",
)
SERVED_CSP = (
    "default-src 'none'; script-src 'self'; "
    f"style-src 'self' {' '.join(VENDOR_STYLE_HASHES)}; "
    "connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": SERVED_CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
NOTE_PATH = re.compile(r"/note/(\d{1,12})")
SEARCH_LIMIT = 200


def serve(config: WorkbenchConfig, port: int = 0, open_browser: bool = True) -> int:
    if not config.brain_path.exists():
        print(f"No brain at {config.brain_path}; store a note first.")
        return 1
    server = make_server(config, port)
    url = f"http://127.0.0.1:{server.server_address[1]}/?token={server.token}"
    print(f"Serving the brain read-only at {url}\nPress Ctrl-C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def make_server(config: WorkbenchConfig, port: int = 0) -> ThreadingHTTPServer:
    """Bound to 127.0.0.1 only; the token and the brain path ride on the server object."""
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    server.token = secrets.token_urlsafe(32)
    server.brain_path = config.brain_path
    bound = server.server_address[1]
    server.allowed_hosts = {f"127.0.0.1:{bound}", f"localhost:{bound}"}
    return server


def export_html(config: WorkbenchConfig, out: str) -> dict[str, Any]:
    """One HTML file with the page, the renderer and every note inlined; it opens offline."""
    if not config.brain_path.exists():
        return {"error": f"no brain at {config.brain_path}"}
    conn = graph.connect_readonly(config.brain_path)
    try:
        data = graph.build(conn, include_resolved=True, include_superseded=True, with_content=True)
    finally:
        conn.close()
    css = (WEB_DIR / "app.css").read_text(encoding="utf-8")
    scripts = [(WEB_DIR / name).read_text(encoding="utf-8") for name in (VENDOR_SCRIPT, "app.js")]
    for text, tag in ((css, "</style"), *((script, "</script") for script in scripts)):
        if tag in text.lower():
            raise ValueError(f"an inlined asset contains {tag!r} and would close its own element")
    csp = (
        "default-src 'none'; "
        f"script-src {' '.join(_hash(text) for text in scripts)}; "
        f"style-src {_hash(css)} {' '.join(VENDOR_STYLE_HASHES)}; "
        "img-src data:; base-uri 'none'; form-action 'none'"
    )
    head = (
        f'<meta http-equiv="Content-Security-Policy" content="{csp}">\n'
        f"<style>{css}</style>"
    )
    body = (
        f'<script type="application/json" id="graph-data">{embed_json(data)}</script>\n'
        + "\n".join(f"<script>{text}</script>" for text in scripts)
    )
    page = _page(head, body)
    target = Path(out).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    return {"path": str(target), "notes": len(data["nodes"]), "edges": len(data["edges"])}


def embed_json(data: Any) -> str:
    """JSON safe inside a <script> element: no '<', '>' or '&' can close it or open a comment."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for raw, escaped in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        text = text.replace(raw, escaped)
    return text


def _page(head: str, body: str) -> str:
    template = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    return template.replace("<!--head-->", head).replace("<!--scripts-->", body)


def _hash(text: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode() + "'"


class _Handler(BaseHTTPRequestHandler):
    server_version = "agent-workbench-graph"
    sys_version = ""

    def do_GET(self) -> None:
        self._respond(send_body=True)

    def do_HEAD(self) -> None:
        self._respond(send_body=False)

    def _refuse_method(self) -> None:
        self._send(405, b"method not allowed\n", "text/plain; charset=utf-8", extra={"Allow": "GET, HEAD"})

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_CONNECT = _refuse_method

    def log_message(self, format: str, *args: Any) -> None:
        # The request line carries the token; keep it out of the terminal scrollback.
        pass

    def _respond(self, send_body: bool) -> None:
        if self.headers.get("Host") not in self.server.allowed_hosts:
            return self._send(403, b"forbidden host\n", "text/plain; charset=utf-8", send_body)
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        supplied = (query.get("token") or [""])[0]
        if not hmac.compare_digest(supplied.encode(), self.server.token.encode()):
            return self._send(403, b"missing or wrong token\n", "text/plain; charset=utf-8", send_body)
        try:
            status, body, content_type = self._route(url.path, query)
        except sqlite3.Error as exc:
            status, body, content_type = 500, _json({"error": f"could not read the brain: {exc}"}), "application/json"
        self._send(status, body, content_type, send_body)

    def _route(self, path: str, query: dict[str, list[str]]) -> tuple[int, bytes, str]:
        if path == "/":
            tags = (
                f'<link rel="stylesheet" href="app.css?token={self.server.token}">',
                f'<script src="{VENDOR_SCRIPT}?token={self.server.token}"></script>\n'
                f'<script src="app.js?token={self.server.token}"></script>',
            )
            return 200, _page(*tags).encode("utf-8"), "text/html; charset=utf-8"
        if path in STATIC:
            name, content_type = STATIC[path]
            return 200, (WEB_DIR / name).read_bytes(), content_type
        if path == "/graph.json":
            with closing(graph.connect_readonly(self.server.brain_path)) as conn:
                data = graph.build(conn, include_resolved=True, include_superseded=True)
            return 200, _json(data), "application/json"
        if path == "/search.json":
            terms = (query.get("q") or [""])[0]
            if not terms.strip():
                return 200, _json({"ids": []}), "application/json"
            with closing(graph.connect_readonly(self.server.brain_path)) as conn:
                rows = conn.execute(
                    "select rowid from notes where notes match ? order by bm25(notes) limit ?",
                    (_fts_query(terms), SEARCH_LIMIT),
                ).fetchall()
            return 200, _json({"ids": [row[0] for row in rows]}), "application/json"
        match = NOTE_PATH.fullmatch(path)
        if match:
            with closing(graph.connect_readonly(self.server.brain_path)) as conn:
                found = graph.note(conn, int(match.group(1)))
            if found is None:
                return 404, _json({"error": "note not found"}), "application/json"
            return 200, _json(found), "application/json"
        return 404, b"not found\n", "text/plain; charset=utf-8"

    def _send(
        self, status: int, body: bytes, content_type: str, send_body: bool = True, extra: dict[str, str] | None = None
    ) -> None:
        self.send_response(status)
        for name, value in {**SECURITY_HEADERS, **(extra or {})}.items():
            self.send_header(name, value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)


def _json(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")
