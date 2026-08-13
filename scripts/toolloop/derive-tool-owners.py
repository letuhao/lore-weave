"""Build an AUTHORITATIVE tool -> provider -> repo-service map.

Never from the tool-name prefix: a consumer-local tool's name can lie about its owner, and a
prefix owner table misattributes it silently. The gateway's own AI_GATEWAY_PROVIDERS gives
provider=<url>; the URL's hostname IS the repo service; each provider's own tools/list says
exactly which tools it serves.

Inputs are dumped from Bash into files first — subprocess(shell=True) on Windows is cmd.exe,
which mangles `sh -c 'echo $VAR'` and silently yields an empty string.
"""
import json, io, os, sys, urllib.request

SP = os.path.dirname(os.path.abspath(__file__))
raw = io.open(os.path.join(SP, "providers.txt"), encoding="utf-8").read().strip()
itok = io.open(os.path.join(SP, "itok.txt"), encoding="utf-8").read().strip()
USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"

ports = {}
for line in io.open(os.path.join(SP, "ports.txt"), encoding="utf-8"):
    if "\t" not in line:
        continue
    name, p = line.rstrip("\n").split("\t", 1)
    if not name.startswith("infra-"):
        continue          # lw-iso-* is a separate stack; never mix the two
    for chunk in p.split(","):
        chunk = chunk.strip()
        if "0.0.0.0:" in chunk and "->" in chunk:
            ports[(name, chunk.split("->", 1)[1].split("/", 1)[0])] = \
                chunk.split("0.0.0.0:", 1)[1].split("->", 1)[0]

providers, owner = {}, {}
for part in raw.split(","):
    if "=" not in part:
        continue
    name, url = (x.strip() for x in part.split("=", 1))
    hostpart = url.split("//", 1)[1]
    svc = hostpart.split(":", 1)[0]
    cport = hostpart.split(":", 1)[1].split("/", 1)[0]
    container = "infra-" + svc + "-1"
    hport = ports.get((container, cport))
    providers[name] = {"url": url, "service": svc, "container": container, "host_port": hport}
    if not hport:
        print(f"  {name:16s} {svc:28s} NO PUBLISHED PORT")
        continue
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode()
    req = urllib.request.Request(
        f"http://localhost:{hport}/mcp", data=body,
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream",
                 "X-Internal-Token": itok, "X-User-Id": USER})
    def _post(path):
        rq = urllib.request.Request(
            f"http://localhost:{hport}{path}", data=body,
            headers={"Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream",
                     "X-Internal-Token": itok, "X-User-Id": USER})
        with urllib.request.urlopen(rq, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    try:
        try:
            txt = _post("/mcp")
        except urllib.error.HTTPError as e:
            # 307 /mcp -> /mcp/ ; urllib will not re-POST across a redirect on its own.
            if e.code in (307, 308):
                txt = _post("/mcp/")
            else:
                raise
        if "data: " in txt:                       # SSE framing
            txt = "\n".join(l[6:] for l in txt.splitlines() if l.startswith("data: "))
        tools = json.loads(txt).get("result", {}).get("tools", [])
    except Exception as exc:
        print(f"  {name:16s} {svc:28s} ERROR {type(exc).__name__}: {exc}")
        tools = []
    for t in tools:
        owner[t["name"]] = {"provider": name, "service": svc}
    print(f"  {name:16s} {svc:28s} tools={len(tools)}")

io.open(os.path.join(SP, "owners.json"), "w", encoding="utf-8").write(
    json.dumps({"providers": providers, "owner": owner}, indent=1))
print("total tools mapped:", len(owner))
