"""Diagnose why the LLM can't be reached.  Run from the project folder:  python scripts/llm_check.py
Steps: config -> DNS -> TCP connect -> a tiny real model call (timed). Never prints your key."""
import os, socket, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import llm_insights as L

L.load_env()
print(f"provider={L.provider()}  model={L.model_name()}  key_found={L.is_configured()}")
if not L.is_configured():
    sys.exit("No API key found: set GEMINI_API_KEY (and LLM_PROVIDER=gemini) or ANTHROPIC_API_KEY, then rerun.")
host = "generativelanguage.googleapis.com" if L.provider() == "gemini" else "api.anthropic.com"
print("proxy settings seen by Python:", urllib.request.getproxies() or "none")

t = time.time()
try:
    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    addrs = sorted({i[4][0] for i in infos})
    print(f"[1] DNS ok in {time.time()-t:.1f}s -> {len(addrs)} address(es): {', '.join(addrs[:4])}")
except OSError as e:
    sys.exit(f"[1] DNS FAILED ({e}). You are offline or DNS is blocked: check Wi-Fi / VPN.")

ok = False
for a in addrs:
    fam = socket.AF_INET6 if ":" in a else socket.AF_INET
    t = time.time()
    try:
        socket.socket(fam, socket.SOCK_STREAM)
        s = socket.create_connection((a, 443), timeout=8); s.close(); ok = True
        print(f"[2] TCP connect to {a} OK in {time.time()-t:.1f}s")
    except OSError as e:
        print(f"[2] TCP connect to {a} FAILED after {time.time()-t:.1f}s ({e})")
if not ok:
    sys.exit("[2] Cannot open a connection to Google/Anthropic on port 443 from Python. A firewall, antivirus, VPN or "
             "college/work proxy is blocking it. Try a mobile hotspot, turn off the VPN, allow python.exe in Windows "
             "Firewall, or set HTTPS_PROXY if your network needs a proxy.")

import json

def candidates(listing, limit=5):
    """Model ids that support generateContent, 'flash' models first (pure function, unit-tested)."""
    names = [m["name"].split("/", 1)[-1] for m in listing.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    names = [n for n in names if not any(x in n for x in ("embed", "image", "tts", "audio", "live", "vision", "robotics", "imagen", "veo"))]
    return (sorted([n for n in names if "flash" in n], reverse=True) + [n for n in names if "flash" not in n])[:limit]

def try_model(name, timeout):
    os.environ["LLM_MODEL"] = name
    t = time.time()
    try:
        r = L._call_api("Reply with the single word OK.", "ping", max_tokens=20, timeout=timeout)
        print(f"    {name}: WORKS in {time.time()-t:.1f}s -> {r.strip()[:40]!r}"); return True
    except L.LLMError as e:
        print(f"    {name}: failed after {time.time()-t:.1f}s -> {str(e)[:140]}"); return False

if __name__ == "__main__":
    cands = []
    if L.provider() == "gemini":
        print("[3] Asking Google which models your key can use (small request, 20s limit)...")
        t = time.time()
        try:
            req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                                         headers={"x-goog-api-key": L._api_key()})
            with urllib.request.urlopen(req, timeout=20, context=L._ssl_context()) as resp:
                cands = candidates(json.loads(resp.read().decode()))
            print(f"[3] OK in {time.time()-t:.1f}s. Usable models (flash first): {', '.join(cands) or 'none found'}")
        except Exception as e:
            print(f"[3] FAILED after {time.time()-t:.1f}s -> {str(getattr(e, 'reason', e))[:160]}")
            print("    Even a small request gets no answer: something on this network/computer blocks HTTPS requests to Google after the connection opens (antivirus web shield, proxy, VPN, college firewall). Try a phone hotspot.")
            sys.exit(1)
    configured = L.model_name()
    print(f"[4] Testing your configured model first, then the others (30s each). Configured: {configured}")
    if try_model(configured, 30):
        print(f"\nThe configured model works. Restart the app and try again."); sys.exit(0)
    for name in [c for c in cands if c != configured][:4]:
        if try_model(name, 30):
            print(f"\nFIX: set LLM_MODEL={name}  (PowerShell: $env:LLM_MODEL=\"{name}\"  or add a line to .env), then restart the app."); sys.exit(0)
    print("\nNo model answered. If step [3] worked but no model answers, the key's project may have no access/quota: open aistudio.google.com, create a new key, and try again.")
