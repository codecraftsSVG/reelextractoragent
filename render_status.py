"""Render deployment status probe.

Reads the Render API key from .env (renderapikey=...) without printing it or
any other secret, then reports service status, latest deploys, env var NAMES
(values are write-only in the API), and the live /health + /jobs responses.

Usage:
    python render_status.py [--service NAME_OR_SLUG] [--url BASE_URL]
"""
import json
import os
import sys
import urllib.request
import urllib.parse

BASE = "https://api.render.com/v1"
DEFAULT_SERVICE = "reelextractoragent"  # live URL slug prefix (-wr3s suffix)
DEFAULT_URL = "https://reelextractoragent-wr3s.onrender.com"


def _load_key() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, ".env"), os.path.join(here, ".env.render")):
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("renderapikey="):
                    return line.split("=", 1)[1].strip()
    raise SystemExit("renderapikey= not found in .env or .env.render")


def _get(url: str, key: str, **params):
    """GET JSON; returns (parsed, raw_text). Never raises."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
        return json.loads(raw), raw
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _norm_url(base: str) -> str:
    base = base.strip()
    if not base.startswith("http"):
        base = "https://" + base
    return base.rstrip("/")


def _pick(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d.get(k)
    return default


def main() -> int:
    slug = DEFAULT_SERVICE
    live_url = DEFAULT_URL
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--service" and i + 1 < len(argv):
            slug = argv[i + 1]
        if a == "--url" and i + 1 < len(argv):
            live_url = argv[i + 1]

    key = _load_key()
    print("[keys] loaded renderapikey from .env (value hidden)")

    services, raw = _get(f"{BASE}/services", key, limit=50)
    if not isinstance(services, list):
        print(f"[!!] GET /services failed: {raw[:500]}")
        return 1

    hit = None
    for entry in services:
        s = entry.get("service", entry) if isinstance(entry, dict) else {}
        name = str(_pick(s, "name", default=""))
        url = str(_pick(s, "url", "serviceUrl", default=""))
        if slug.lower() in name.lower() or slug.lower() in url.lower():
            hit = s
            break
    if not hit:
        print(f"[!!] no service matching '{slug}'. Known services:")
        for entry in services:
            s = entry.get("service", entry) if isinstance(entry, dict) else {}
            print("   -", _pick(s, "name"), "->", _pick(s, "url", "serviceUrl"))
        return 1

    sid = hit.get("id")
    print(f"[service] {_pick(hit, 'name')} ({sid})")
    print(f"  type={_pick(hit, 'type')} plan={_pick(hit, 'plan')}")
    print(f"  repo={_pick(hit, 'repo')} branch={_pick(hit, 'repoBranch', 'branch')}")
    print(f"  status={_pick(hit, 'status', 'serviceStatus', 'currentStatus')} "
          f"(raw keys: {sorted(hit.keys())})")
    print(f"  url={_pick(hit, 'url', 'serviceUrl', default=live_url)}")
    print(f"  created={_pick(hit, 'createdAt')} updated={_pick(hit, 'updatedAt')}")
    sd = hit.get("serviceDetails") or {}
    if sd:
        print(f"  serviceDetails.status={_pick(sd, 'serviceStatus', 'status')} "
              f"health={_pick(sd, 'healthStatus', 'health')}")

    # Latest deploys
    deploys, draw = _get(f"{BASE}/services/{sid}/deploys", key, limit=5)
    print("[deploys] latest 5:")
    if isinstance(deploys, list) and deploys:
        for d in deploys:
            if isinstance(d, dict) and "deploy" in d:
                d = d["deploy"]
            if isinstance(d, dict) and "status" not in d:
                # Unknown shape - dump keys once so the script stays debuggable
                print(f"  (unexpected deploy fields: {sorted(d.keys())})")
            commit = _pick(d, "commit", "commitId", default="")
            if isinstance(commit, dict):
                commit = _pick(commit, "id", "sha", "commitId", default="")
            print(f"  {_pick(d, 'id', default='?')} | status={_pick(d, 'status')} "
                  f"| created={_pick(d, 'createdAt')} "
                  f"| commit={str(commit)[:8]} "
                  f"| {str(_pick(d, 'statusDetails', 'message', default=''))[:120]}")
    else:
        print(f"  (none / unparseable) raw: {draw[:400]}")

    # Env var NAMES only (values are write-only in the API; never print them)
    envs, eraw = _get(f"{BASE}/services/{sid}/env-vars", key)
    try:
        items = envs if isinstance(envs, list) else (envs or {}).get("envVars", [])
        names = []
        for item in items:
            if not isinstance(item, dict):
                continue
            env_var = item.get("envVar", item)
            if isinstance(env_var, dict):
                name = env_var.get("key") or env_var.get("name")
                if name:
                    names.append(str(name))
        names.sort()
        print(f"[env-vars] {len(names)} keys set: {', '.join(names)}")
        for want in ("GEMINI_API_KEY", "COOKIES_TXT", "DATABASE_URL", "PYTHONUNBUFFERED"):
            print(f"  {'OK     ' if want in names else 'MISSING'} {want}")
    except Exception as e:
        print(f"[env-vars] could not list: {e} | raw: {eraw[:300]}")

    # Live endpoints
    base = _norm_url(str(_pick(hit, "url", "serviceUrl", default=live_url)))
    print(f"[live] base URL: {base} (waiting up to 90s for cold-start wake up)")
    for path in ("/health", "/jobs"):
        code, body = None, ""
        try:
            req = urllib.request.Request(base + path)
            with urllib.request.urlopen(req, timeout=90) as r:
                code = r.status
                body = r.read().decode("utf-8", "replace")[:600]
        except Exception as e:
            body = f"{type(e).__name__}: {e}"
        print(f"[live] GET {base}{path} -> {code} {body}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
