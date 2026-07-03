# Minimal fake OAuth 2.1 authorization server for the P3-M4 live smoke.
# Binds 0.0.0.0 so the agent-registry CONTAINER can reach it at host.docker.internal:PORT.
# /token returns a canned token response for both authorization_code and refresh_token grants.
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8791


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = self.rfile.read(n).decode()
        form = parse_qs(body)
        grant = form.get("grant_type", [""])[0]
        # echo the grant so the smoke can assert PKCE/refresh params arrived
        access = "AT-refresh" if grant == "refresh_token" else "AT-authcode"
        resp = {"access_token": access, "refresh_token": "RT-1", "token_type": "Bearer", "expires_in": 3600}
        out = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()
