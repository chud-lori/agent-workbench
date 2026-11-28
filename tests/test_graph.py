from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from agent_workbench import brain, graph, graph_server, mcp_server
from agent_workbench.config import WorkbenchConfig

REPO = Path(__file__).resolve().parents[1]
VENDOR = Path(graph_server.__file__).resolve().parent / "web" / "vendor"
FORCE_GRAPH_SHA256 = "f59db59ba92ff5a76ed93d7a4d77a703b176260e5d9cd29f4f8eb4f6c369a629"
PAYLOAD = "</script><script>alert(1)</script> \u2028 <!-- & -->"


def _graph(config: WorkbenchConfig, **kwargs):
    conn = graph.connect_readonly(config.brain_path)
    try:
        return graph.build(conn, **kwargs)
    finally:
        conn.close()


def _cites(data) -> set[tuple[int, int]]:
    return {(edge["source"], edge["target"]) for edge in data["edges"] if edge["type"] == "cites"}


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = WorkbenchConfig(workbench_home=Path(tmp.name))

    def remember(self, content: str, **kwargs) -> int:
        return brain.remember(content, config=self.config, **kwargs)["id"]

    def test_references_resolve_to_directed_edges(self) -> None:
        a = self.remember("queue workers retry three times", kind="fact")
        b = self.remember(f"cap retries, see fact#{a} and brain#{a} again", kind="decision")
        c = self.remember(f"gotcha: retries stampede, per decision#{b}", kind="gotcha")
        data = _graph(self.config)
        self.assertEqual(_cites(data), {(b, a), (c, b)})
        by_id = {node["id"]: node for node in data["nodes"]}
        self.assertEqual(by_id[a]["cited_by"], 1)
        self.assertNotIn("content", by_id[a])
        self.assertEqual(data["stats"]["most_cited"][0]["id"], a)

    def test_unknown_ids_are_counted_not_linked(self) -> None:
        a = self.remember("cites a note that never existed: gotcha#9999")
        data = _graph(self.config)
        self.assertEqual(data["edges"], [])
        self.assertEqual(data["stats"]["dangling"], {"count": 1, "sample": [{"from": a, "to": 9999}]})

    def test_a_note_citing_itself_adds_no_edge(self) -> None:
        a = self.remember("first note")
        brain.amend(a, f"see brain#{a}", config=self.config)
        data = _graph(self.config)
        self.assertEqual(data["edges"], [])
        self.assertEqual(data["stats"]["orphans"]["sample"], [a])

    def test_superseded_notes_are_hidden_by_default(self) -> None:
        old = self.remember("deploys go to the blue cluster", kind="fact")
        new = self.remember("deploys go to the green cluster", kind="fact", supersedes=[old])
        citer = self.remember(f"the old claim was fact#{old}")
        default = _graph(self.config)
        self.assertNotIn(old, {node["id"] for node in default["nodes"]})
        self.assertEqual(default["edges"], [])
        self.assertEqual(default["stats"]["dangling"]["count"], 0)
        everything = _graph(self.config, include_superseded=True)
        self.assertIn({"source": new, "target": old, "type": "supersedes"}, everything["edges"])
        self.assertIn((citer, old), _cites(everything))

    def test_resolved_notes_are_hidden_by_default(self) -> None:
        done = self.remember("todo: rotate the staging key", kind="todo")
        brain.resolve(done, config=self.config)
        self.assertEqual(_graph(self.config)["nodes"], [])
        self.assertTrue(_graph(self.config, include_resolved=True)["nodes"][0]["resolved"])

    def test_only_note_kinds_count_as_references(self) -> None:
        a = self.remember("a fact")
        self.remember(f"rule#{a} and issue#{a} and somebrain#{a} are not note links")
        self.assertEqual(_graph(self.config)["edges"], [])

    def test_project_filter(self) -> None:
        self.remember("api note", project="api")
        self.remember("web note", project="web")
        self.assertEqual([node["project"] for node in _graph(self.config, project="api")["nodes"]], ["api"])

    def test_readonly_connection_cannot_write(self) -> None:
        self.remember("anything")
        conn = graph.connect_readonly(self.config.brain_path)
        self.addCleanup(conn.close)
        with self.assertRaises(sqlite3.OperationalError):
            conn.execute("delete from notes")

    def test_stats_tool_is_listed_and_reports_orphans(self) -> None:
        self.assertIn("brain_graph", mcp_server.TOOLS)
        self.assertIn("warning", graph.stats(config=self.config))
        lone = self.remember("nobody links here")
        report = graph.stats(config=self.config)
        self.assertEqual(report["orphans"], {"count": 1, "sample": [lone]})
        self.assertNotIn("nodes", report)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.config = WorkbenchConfig(workbench_home=Path(cls.tmp.name))
        cls.first = brain.remember("plain first note", config=cls.config)["id"]
        cls.hostile = brain.remember(f"pasted log {PAYLOAD} cites brain#{cls.first}", config=cls.config)["id"]
        cls.server = graph_server.make_server(cls.config)
        cls.port = cls.server.server_address[1]
        cls.token = cls.server.token
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def request(self, path: str, method: str = "GET", host: str | None = None, token: bool = True):
        if token:
            path += ("&" if "?" in path else "?") + f"token={self.token}"
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.putrequest(method, path, skip_host=True)
        conn.putheader("Host", host or f"127.0.0.1:{self.port}")
        conn.endheaders()
        response = conn.getresponse()
        return response, response.read()

    def test_binds_loopback_only(self) -> None:
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_every_request_needs_the_token(self) -> None:
        for path in ("/", "/app.js", "/graph.json", f"/note/{self.first}", "/search.json?q=note"):
            self.assertEqual(self.request(path, token=False)[0].status, 403, path)
            wrong = path + ("&" if "?" in path else "?") + "token=wrong"
            self.assertEqual(self.request(wrong, token=False)[0].status, 403, wrong)
            self.assertEqual(self.request(path)[0].status, 200, path)

    def test_foreign_host_is_refused(self) -> None:
        for host in ("evil.example", f"evil.example:{self.port}", "127.0.0.1:1", f"localhost.evil.example:{self.port}"):
            self.assertEqual(self.request("/graph.json", host=host)[0].status, 403, host)
        self.assertEqual(self.request("/graph.json", host=f"localhost:{self.port}")[0].status, 200)

    def test_only_get_and_head_are_allowed(self) -> None:
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            response, _ = self.request("/graph.json", method=method)
            self.assertEqual(response.status, 405, method)
        response, body = self.request("/graph.json", method="HEAD")
        self.assertEqual((response.status, body), (200, b""))

    def test_security_headers(self) -> None:
        response, _ = self.request("/")
        csp = response.getheader("Content-Security-Policy")
        for directive in ("default-src 'none'", "script-src 'self'", "frame-ancestors 'none'", "base-uri 'none'"):
            self.assertIn(directive, csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.getheader("Referrer-Policy"), "no-referrer")

    def test_note_body_is_json_text_not_html(self) -> None:
        response, body = self.request(f"/note/{self.hostile}")
        self.assertEqual(response.getheader("Content-Type"), "application/json")
        self.assertIn(PAYLOAD, json.loads(body)["content"])

    def test_note_id_must_be_an_integer(self) -> None:
        for path in ("/note/abc", "/note/1.5", "/note/-1", f"/note/{self.first}/x", "/note/"):
            self.assertEqual(self.request(path)[0].status, 404, path)
        self.assertEqual(self.request("/note/424242")[0].status, 404)

    def test_static_files_are_an_allowlist(self) -> None:
        for path in ("/index.html", "/graph.py", "/../graph.py", "/vendor/../../graph.py", "/web/app.js", "/vendor/SOURCE.txt"):
            self.assertEqual(self.request(path)[0].status, 404, path)

    def test_graph_json_carries_no_bodies(self) -> None:
        data = json.loads(self.request("/graph.json")[1])
        self.assertEqual(_cites(data), {(self.hostile, self.first)})
        self.assertTrue(all("content" not in node for node in data["nodes"]))

    def test_search_uses_the_fts_index(self) -> None:
        self.assertEqual(json.loads(self.request("/search.json?q=pasted")[1])["ids"], [self.hostile])
        self.assertEqual(json.loads(self.request("/search.json?q=")[1])["ids"], [])

    def test_page_loads_assets_with_the_token(self) -> None:
        page = self.request("/")[1].decode()
        self.assertIn(f'src="app.js?token={self.token}"', page)
        self.assertNotIn("<!--scripts-->", page)


class ExportTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.config = WorkbenchConfig(workbench_home=self.base / "state")
        brain.remember(f"pasted log {PAYLOAD}", config=self.config)

    def test_export_embeds_hostile_text_safely(self) -> None:
        out = self.base / "graph.html"
        graph_server.export_html(self.config, str(out))
        page = out.read_text(encoding="utf-8")
        self.assertNotIn("alert(1)</script>", page)
        self.assertNotIn("\u2028", page)
        self.assertEqual(page.lower().count("<script"), 3)
        embedded = re.search(r'<script type="application/json" id="graph-data">(.*?)</script>', page, re.S).group(1)
        self.assertIn(PAYLOAD, json.loads(embedded)["nodes"][0]["content"])

    def test_export_csp_allows_exactly_the_inlined_scripts(self) -> None:
        out = self.base / "graph.html"
        graph_server.export_html(self.config, str(out))
        page = out.read_text(encoding="utf-8")
        csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', page).group(1)
        self.assertNotIn("unsafe", csp)
        inline = re.findall(r"<script>(.*?)</script>", page, re.S)
        self.assertEqual(len(inline), 2)
        for script in inline:
            self.assertIn(graph_server._hash(script), csp)

    def _cli(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, AGENT_WORKBENCH_STATE_DIR=str(self.config.workbench_home))
        return subprocess.run(
            [sys.executable, str(REPO / "run_cli.py"), "graph", *args], capture_output=True, text=True, env=env, timeout=60
        )

    def test_cli_export_warns_that_it_holds_every_note(self) -> None:
        result = self._cli("--export", str(self.base / "g.html"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("full text of every exported note", result.stdout)
        self.assertTrue((self.base / "g.html").exists())

    def test_graph_command_has_no_bind_address_option(self) -> None:
        result = self._cli("--host", "0.0.0.0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)


class VendorTests(unittest.TestCase):
    def test_renderer_is_the_pinned_build(self) -> None:
        digest = hashlib.sha256((VENDOR / "force-graph.min.js").read_bytes()).hexdigest()
        self.assertEqual(digest, FORCE_GRAPH_SHA256)
        self.assertIn("MIT License", (VENDOR / "force-graph.LICENSE").read_text())
        self.assertIn("force-graph@1.52.0", (VENDOR / "SOURCE.txt").read_text())

    def test_csp_style_hashes_match_what_the_renderer_injects(self) -> None:
        bundle = (VENDOR / "force-graph.min.js").read_text(encoding="utf-8")
        injected = [
            json.loads(literal)
            for literal in re.findall(r'createTextNode\(t\)\)\}\}\(("(?:[^"\\]|\\.)*")\)', bundle)
        ]
        self.assertEqual(len(injected), 2)
        expected = {graph_server._hash(css) for css in ["", *injected]}
        self.assertEqual(set(graph_server.VENDOR_STYLE_HASHES), expected)

    def test_page_script_never_parses_html(self) -> None:
        app = (VENDOR.parent / "app.js").read_text(encoding="utf-8")
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            self.assertNotIn(sink, app)


if __name__ == "__main__":
    unittest.main()
