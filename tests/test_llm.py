"""LLM insights tests. Run: python -m unittest tests.test_llm
The HTTP layer is tested against a local fake server; LiveCall runs only if ANTHROPIC_API_KEY is set."""
import json, os, sys, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_fd, _db = tempfile.mkstemp(suffix=".db"); os.close(_fd)
os.environ["DB_PATH"] = _db
for _k, _v in (("LLM_PROVIDER", "anthropic"), ("LLM_MODEL", ""), ("GEMINI_API_KEY", "")):
    os.environ[_k] = _v                                  # keep a real local .env (Gemini key) out of these offline tests
_REAL_KEY = os.environ.get("ANTHROPIC_API_KEY")       # remember a real key (live test) before faking one
import llm_insights as L   # noqa: E402
import app as A            # noqa: E402

GOOD = {"spending_summary": "You spent Rs. 40,000, mostly on Rent.", "income_patterns": "Income is regular.",
        "insights": [{"title": "Rent is large", "detail": "Rent is 62% of spend.", "type": "warning"},
                     {"title": "x", "detail": "y", "type": "bogus"}],
        "recommendations": [{"action": "Review rent share", "reason": "It is the biggest category."}], "caveats": ["Short history."]}


def records():
    r = lambda d, t, a, c, who, raw="": {"id": 1, "date": d, "type": t, "amount": a, "category": c,
                                          "receiver_payer": who, "raw_narration": raw, "notes": "secret note"}
    out = []
    for m in ("2026-07", "2026-08", "2026-09"):
        out += [r(m + "-01", "earning", 60000, "Salary", "Acme Technologies Pvt Ltd", "NEFT-SALARY-ACC 123456789012"),
                r(m + "-03", "expense", 25000, "Rent", "Ramesh Kumar Sharma", "UPI-RAMESH@OKSBI-RENT"),
                r(m + "-10", "expense", 4000, "Food", "Swiggy")]
    return out


class Context(unittest.TestCase):
    def test_context_has_figures_but_no_names_or_narrations(self):
        txt = json.dumps(L.build_context(records()))
        self.assertIn('"Rent"', txt); self.assertIn('"months": 3', txt)
        for leaked in ("Ramesh", "Acme", "Swiggy", "123456789012", "OKSBI", "secret note"):
            self.assertNotIn(leaked, txt)

class Parse(unittest.TestCase):
    def test_parses_fenced_json_and_sanitises(self):
        d = L.parse_response("Here you go:\n```json\n" + json.dumps(GOOD) + "\n```")
        self.assertEqual(d["insights"][1]["type"], "info"); self.assertEqual(len(d["recommendations"]), 1)
    def test_bad_format_raises(self):
        for bad in ("no json at all", '{"foo": 1}', "{broken"):
            with self.assertRaises(L.LLMError): L.parse_response(bad)

class HttpLayer(unittest.TestCase):
    def test_request_shape_and_response_parsing(self):
        seen = {}
        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                seen["headers"] = {k.lower(): v for k, v in self.headers.items()}; seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                out = json.dumps({"content": [{"type": "text", "text": json.dumps(GOOD)}]}).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
            def log_message(self, *a): pass
        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        old = (L.API_URL, os.environ.get("ANTHROPIC_API_KEY"))
        L.API_URL = f"http://127.0.0.1:{srv.server_port}/v1/messages"; os.environ["ANTHROPIC_API_KEY"] = "test-key-123"
        try:
            text = L._call_api("SYS", "USER")
        finally:
            srv.shutdown(); L.API_URL = old[0]
            if old[1] is None: os.environ.pop("ANTHROPIC_API_KEY", None)
            else: os.environ["ANTHROPIC_API_KEY"] = old[1]
        self.assertEqual(seen["headers"]["x-api-key"], "test-key-123")
        self.assertEqual(seen["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(seen["body"]["system"], "SYS"); self.assertEqual(seen["body"]["messages"][0]["content"], "USER")
        self.assertEqual(seen["body"]["model"], L.model_name()); self.assertIn("spending_summary", text)

class Endpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = A.app.test_client()
        tok = cls.c.post("/api/signup", json={"username": "llmuser", "password": "secret1"}).get_json()["token"]
        cls.H = {"Authorization": "Bearer " + tok}
        cls.c.post("/api/masters", json={"categories": [], "subcategories": [], "receivers": [], "payers": [], "opening_balance": 0}, headers=cls.H)
    def setUp(self):
        self._key = os.environ.get("ANTHROPIC_API_KEY"); L._cache.clear(); L._last_call.clear()
    def tearDown(self):
        if self._key is None: os.environ.pop("ANTHROPIC_API_KEY", None)
        else: os.environ["ANTHROPIC_API_KEY"] = self._key
    def _add(self):
        for r in records():
            self.c.post("/api/records", json={"type": r["type"], "amount": r["amount"], "category": r["category"], "receiver_payer": r["receiver_payer"], "date": r["date"]}, headers=self.H)
    def test_requires_login(self):
        self.assertEqual(self.c.post("/api/llm/insights").status_code, 401)
    def test_not_configured_gives_503_and_status_has_no_key(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.assertEqual(self.c.post("/api/llm/insights", headers=self.H).status_code, 503)
        os.environ["ANTHROPIC_API_KEY"] = "sk-secret-value"
        s = self.c.get("/api/llm/status", headers=self.H); self.assertTrue(s.get_json()["configured"])
        self.assertNotIn("sk-secret-value", s.get_data(as_text=True))
    def test_no_data_error(self):
        os.environ["ANTHROPIC_API_KEY"] = "k"
        tok = self.c.post("/api/signup", json={"username": "emptyuser", "password": "secret1"}).get_json()["token"]
        H2 = {"Authorization": "Bearer " + tok}
        self.c.post("/api/masters", json={"categories": [], "subcategories": [], "receivers": [], "payers": [], "opening_balance": 0}, headers=H2)
        r = self.c.post("/api/llm/insights", headers=H2); self.assertEqual(r.status_code, 502); self.assertIn("transactions", r.get_json()["error"])
    def test_generate_cache_and_error_hides_key(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-secret-value"; self._add()
        calls = []
        orig = L._call_api; L._call_api = lambda s, u, **k: (calls.append(u), json.dumps(GOOD))[1]
        try:
            r = self.c.post("/api/llm/insights", headers=self.H).get_json()
            self.assertEqual(r["insights"][0]["type"], "warning"); self.assertFalse(r["cached"])
            self.assertTrue(self.c.post("/api/llm/insights", headers=self.H).get_json()["cached"]); self.assertEqual(len(calls), 1)
            self.assertNotIn("Ramesh", calls[0]); self.assertNotIn("sk-secret-value", json.dumps(r))
            L._call_api = lambda s, u, **k: (_ for _ in ()).throw(L.LLMError("LLM API error (HTTP 401)."))
            L._last_call.clear(); bad = self.c.post("/api/llm/insights", json={"force": True}, headers=self.H)
            self.assertEqual(bad.status_code, 502); self.assertNotIn("sk-secret-value", bad.get_data(as_text=True))
        finally:
            L._call_api = orig


class ChatContext(unittest.TestCase):
    def test_chat_context_has_month_by_category_but_no_names(self):
        ctx = L.build_chat_context(records()); txt = json.dumps(ctx)
        self.assertEqual(ctx["spending_by_month_and_category"]["2026-08"]["Rent"], 25000)
        self.assertIn("persona", ctx); self.assertIn("income_streams", ctx)
        for leaked in ("Ramesh", "Acme", "Swiggy", "123456789012", "OKSBI", "secret note"):
            self.assertNotIn(leaked, txt)
    def test_clean_messages(self):
        m = L._clean_messages([{"role": "assistant", "content": "hi"}, {"role": "user", "content": "  q1  "},
                               {"role": "assistant", "content": "a"}, {"role": "user", "content": "x" * 900}, {"role": "system", "content": "evil"}])
        self.assertEqual([x["role"] for x in m], ["user", "assistant", "user"]); self.assertEqual(len(m[2]["content"]), L.MAX_CHAT_CHARS)
        for bad in ([], [{"role": "assistant", "content": "a"}], [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}], "nope", None):
            with self.assertRaises(L.LLMError): L._clean_messages(bad)
    def test_history_is_limited(self):
        msgs = []
        for i in range(10): msgs += [{"role": "user", "content": f"q{i}"}, {"role": "assistant", "content": f"a{i}"}]
        msgs.append({"role": "user", "content": "last"})
        out = L._clean_messages(msgs); self.assertLessEqual(len(out), L.MAX_CHAT_MESSAGES); self.assertEqual(out[0]["role"], "user"); self.assertEqual(out[-1]["content"], "last")

class ChatHttp(unittest.TestCase):
    def test_messages_are_sent_as_conversation(self):
        seen = {}
        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                out = json.dumps({"content": [{"type": "text", "text": "You spent Rs. 4,000 on Food."}]}).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
            def log_message(self, *a): pass
        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        old = (L.API_URL, os.environ.get("ANTHROPIC_API_KEY")); L.API_URL = f"http://127.0.0.1:{srv.server_port}/v1/messages"; os.environ["ANTHROPIC_API_KEY"] = "k"
        try:
            text = L._call_api("SYS", None, max_tokens=600, messages=[{"role": "user", "content": "Q"}, {"role": "assistant", "content": "A"}, {"role": "user", "content": "Q2"}])
        finally:
            srv.shutdown(); L.API_URL = old[0]
            if old[1] is None: os.environ.pop("ANTHROPIC_API_KEY", None)
            else: os.environ["ANTHROPIC_API_KEY"] = old[1]
        self.assertEqual([m["content"] for m in seen["body"]["messages"]], ["Q", "A", "Q2"]); self.assertEqual(seen["body"]["max_tokens"], 600)
        self.assertIn("Food", text)

class ChatEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = A.app.test_client()
        tok = cls.c.post("/api/signup", json={"username": "chatuser", "password": "secret1"}).get_json()["token"]; cls.H = {"Authorization": "Bearer " + tok}
        cls.c.post("/api/masters", json={"categories": [], "subcategories": [], "receivers": [], "payers": [], "opening_balance": 0}, headers=cls.H)
        for r in records():
            cls.c.post("/api/records", json={"type": r["type"], "amount": r["amount"], "category": r["category"], "receiver_payer": r["receiver_payer"], "date": r["date"]}, headers=cls.H)
    def setUp(self):
        self._key = os.environ.get("ANTHROPIC_API_KEY"); L._last_chat.clear(); self._orig = L._call_api
    def tearDown(self):
        L._call_api = self._orig
        if self._key is None: os.environ.pop("ANTHROPIC_API_KEY", None)
        else: os.environ["ANTHROPIC_API_KEY"] = self._key
    def test_login_and_config_required(self):
        self.assertEqual(self.c.post("/api/llm/chat", json={"messages": []}).status_code, 401)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.assertEqual(self.c.post("/api/llm/chat", json={"messages": [{"role": "user", "content": "hi"}]}, headers=self.H).status_code, 503)
    def test_reply_is_grounded_and_private(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-secret-value"; seen = {}
        def fake(system, user, **k): seen.update(system=system, msgs=k.get("messages")); return "Food was Rs. 4,000 in 2026-08."
        L._call_api = fake
        r = self.c.post("/api/llm/chat", json={"messages": [{"role": "user", "content": "How much on food in August?"}]}, headers=self.H)
        self.assertEqual(r.status_code, 200); self.assertIn("4,000", r.get_json()["reply"])
        self.assertIn('"2026-08"', seen["system"]); self.assertNotIn("Ramesh", seen["system"]); self.assertNotIn("sk-secret-value", r.get_data(as_text=True))
        self.assertEqual(seen["msgs"][-1]["content"], "How much on food in August?")
    def test_bad_payload_and_api_errors(self):
        os.environ["ANTHROPIC_API_KEY"] = "k"; L._call_api = lambda s, u, **k: "ok"
        self.assertEqual(self.c.post("/api/llm/chat", json={"messages": "x"}, headers=self.H).status_code, 502)
        L._last_chat.clear(); L._call_api = lambda s, u, **k: (_ for _ in ()).throw(L.LLMError("LLM API error (HTTP 500)."))
        self.assertEqual(self.c.post("/api/llm/chat", json={"messages": [{"role": "user", "content": "q"}]}, headers=self.H).status_code, 502)
    def test_rate_limit(self):
        os.environ["ANTHROPIC_API_KEY"] = "k"; L._call_api = lambda s, u, **k: "ok"; body = {"messages": [{"role": "user", "content": "q"}]}
        self.assertEqual(self.c.post("/api/llm/chat", json=body, headers=self.H).status_code, 200)
        self.assertEqual(self.c.post("/api/llm/chat", json=body, headers=self.H).status_code, 502)


class _Env:
    """Temporarily set/unset env vars."""
    def __init__(self, **kw): self.kw = kw
    def __enter__(self):
        self.old = {k: os.environ.get(k) for k in self.kw}
        for k, v in self.kw.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

class GeminiProvider(unittest.TestCase):
    CLEAR = dict(LLM_PROVIDER=None, LLM_MODEL=None, ANTHROPIC_API_KEY=None, GEMINI_API_KEY=None, GOOGLE_API_KEY=None)
    def test_provider_selection(self):
        with _Env(**self.CLEAR):
            self.assertEqual(L.provider(), "anthropic"); self.assertFalse(L.is_configured())
        with _Env(**{**self.CLEAR, "GEMINI_API_KEY": "g"}):
            self.assertEqual(L.provider(), "gemini"); self.assertTrue(L.is_configured()); self.assertEqual(L.model_name(), L.DEFAULT_MODELS["gemini"])
        with _Env(**{**self.CLEAR, "GEMINI_API_KEY": "g", "ANTHROPIC_API_KEY": "a"}):
            self.assertEqual(L.provider(), "anthropic")                      # both set -> Anthropic unless LLM_PROVIDER says otherwise
        with _Env(**{**self.CLEAR, "GEMINI_API_KEY": "g", "ANTHROPIC_API_KEY": "a", "LLM_PROVIDER": "gemini", "LLM_MODEL": "my-model"}):
            self.assertEqual((L.provider(), L.model_name()), ("gemini", "my-model"))
        with _Env(**{**self.CLEAR, "LLM_PROVIDER": "gemini", "ANTHROPIC_API_KEY": "a"}):
            self.assertFalse(L.is_configured())                              # provider gemini but no Gemini key
    def _server(self, reply, status=200):
        seen = {}
        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                seen["path"] = self.path; seen["headers"] = {k.lower(): v for k, v in self.headers.items()}
                seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                out = json.dumps(reply).encode(); self.send_response(status); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
            def log_message(self, *a): pass
        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv, seen
    def _call(self, reply, status=200, **kw):
        srv, seen = self._server(reply, status); old = L.GEMINI_URL
        L.GEMINI_URL = f"http://127.0.0.1:{srv.server_port}/v1beta/models/{{model}}:generateContent"
        try:
            with _Env(**{**self.CLEAR, "GEMINI_API_KEY": "gem-key-1", "LLM_MODEL": "test-model"}):
                return L._call_api("SYS", None, **kw), seen
        finally:
            srv.shutdown(); L.GEMINI_URL = old
    def test_request_shape_and_thought_parts_skipped(self):
        text, seen = self._call({"candidates": [{"content": {"parts": [{"text": "hidden", "thought": True}, {"text": "Hello "}, {"text": "world"}]}}]},
                                max_tokens=600, json_mode=True,
                                messages=[{"role": "user", "content": "Q"}, {"role": "assistant", "content": "A"}, {"role": "user", "content": "Q2"}])
        self.assertEqual(text, "Hello world")
        self.assertEqual(seen["path"], "/v1beta/models/test-model:generateContent"); self.assertEqual(seen["headers"]["x-goog-api-key"], "gem-key-1")
        self.assertNotIn("gem-key-1", seen["path"])                                                       # key is in a header, never the URL
        b = seen["body"]; self.assertEqual(b["systemInstruction"]["parts"][0]["text"], "SYS")
        self.assertEqual([c["role"] for c in b["contents"]], ["user", "model", "user"]); self.assertEqual(b["contents"][2]["parts"][0]["text"], "Q2")
        self.assertEqual(b["generationConfig"]["responseMimeType"], "application/json"); self.assertGreaterEqual(b["generationConfig"]["maxOutputTokens"], 600)
    def test_blocked_and_empty_and_http_error(self):
        with self.assertRaises(L.LLMError) as e: self._call({"promptFeedback": {"blockReason": "SAFETY"}})
        self.assertIn("SAFETY", str(e.exception))
        with self.assertRaises(L.LLMError): self._call({"candidates": [{"content": {"parts": []}}]})
        with self.assertRaises(L.LLMError) as e: self._call({"error": {"message": "API key not valid"}}, status=400)
        self.assertIn("HTTP 400", str(e.exception)); self.assertNotIn("gem-key-1", str(e.exception))
    def test_status_endpoint_reports_provider_without_key(self):
        c = A.app.test_client(); tok = c.post("/api/signup", json={"username": "gemstatus", "password": "secret1"}).get_json()["token"]
        with _Env(**{**self.CLEAR, "GEMINI_API_KEY": "gem-key-1"}):
            r = c.get("/api/llm/status", headers={"Authorization": "Bearer " + tok}); d = r.get_json()
        self.assertEqual((d["provider"], d["configured"]), ("gemini", True)); self.assertNotIn("gem-key-1", r.get_data(as_text=True))


class EnvFile(unittest.TestCase):
    def test_load_env_handles_windows_encodings(self):
        text = "# comment\nLLM_PROVIDER=gemini\nGEMINI_API_KEY=\"abc123\"\n"
        for name, data in (("utf8", text.encode("utf-8")), ("bom", text.encode("utf-8-sig")), ("utf16", text.encode("utf-16"))):
            path = os.path.join(tempfile.gettempdir(), f"envtest_{name}")
            open(path, "wb").write(data)
            with _Env(LLM_PROVIDER=None, GEMINI_API_KEY=None):
                L.load_env(path)
                self.assertEqual((os.environ.get("LLM_PROVIDER"), os.environ.get("GEMINI_API_KEY")), ("gemini", "abc123"), name)
            os.remove(path)
    def test_real_env_vars_win_over_file(self):
        path = os.path.join(tempfile.gettempdir(), "envtest_win"); open(path, "w").write("GEMINI_API_KEY=from-file\n")
        with _Env(GEMINI_API_KEY="from-env"):
            L.load_env(path); self.assertEqual(os.environ["GEMINI_API_KEY"], "from-env")
        os.remove(path)


class NetworkErrors(unittest.TestCase):
    def _raise(self, exc):
        orig = urllib.request.urlopen
        def boom(*a, **k): raise exc
        urllib.request.urlopen = boom
        try:
            with _Env(ANTHROPIC_API_KEY="sk-secret-value", LLM_PROVIDER=None, GEMINI_API_KEY=None):
                with self.assertRaises(L.LLMError) as e: L._call_api("S", "U")
            return str(e.exception)
        finally:
            urllib.request.urlopen = orig
    def test_reason_and_hint_are_shown_and_key_is_not(self):
        m = self._raise(urllib.error.URLError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"))
        self.assertIn("CERTIFICATE_VERIFY_FAILED", m); self.assertIn("certifi", m); self.assertNotIn("sk-secret-value", m)
        m = self._raise(urllib.error.URLError("[Errno 11001] getaddrinfo failed")); self.assertIn("DNS", m)
        m = self._raise(TimeoutError("timed out")); self.assertIn("timed out", m); self.assertIn("firewall", m)

@unittest.skipUnless(_REAL_KEY, "set ANTHROPIC_API_KEY to run the live API test")
class LiveCall(unittest.TestCase):
    def test_live(self):
        os.environ["ANTHROPIC_API_KEY"] = _REAL_KEY; L._cache.clear(); L._last_call.clear(); L._last_chat.clear()
        r = L.generate(1, records(), force=True)
        self.assertTrue(r["spending_summary"]); self.assertTrue(r["recommendations"])
        c = L.chat(1, records(), [{"role": "user", "content": "How much did I spend on Rent in 2026-08?"}])
        self.assertTrue(c["reply"])

if __name__ == "__main__":
    unittest.main()
