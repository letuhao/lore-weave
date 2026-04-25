#!/usr/bin/env python3
"""
Tiny CORS proxy for LM Studio (or any local LLM server).

Run this alongside LM Studio. It listens on :5501 and forwards everything
to :1234 with `Access-Control-Allow-Origin: *` added to all responses.

Usage:
  python cors_proxy.py
  # then in CELL_SCENE_v2_lmstudio.html, set URL to:
  #   http://localhost:5501/v1/chat/completions
  # (instead of :1234)

Stop with Ctrl+C.

No external deps — uses Python stdlib only (3.7+).
"""

import http.server
import urllib.request
import urllib.error
import sys

UPSTREAM = "http://localhost:1234"
LISTEN_PORT = 5501


class CorsProxy(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        self._proxy("GET")

    def do_POST(self):
        self._proxy("POST")

    def _proxy(self, method):
        target = UPSTREAM + self.path
        body = None
        if method == "POST":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""

        req = urllib.request.Request(target, data=body, method=method)
        # Forward content-type
        ct = self.headers.get("Content-Type")
        if ct:
            req.add_header("Content-Type", ct)

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                self.send_response(resp.status)
                for header, value in resp.getheaders():
                    if header.lower() in ("transfer-encoding", "connection",
                                          "access-control-allow-origin",
                                          "access-control-allow-headers",
                                          "access-control-allow-methods"):
                        continue
                    self.send_header(header, value)
                self._cors_headers()
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self._cors_headers()
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Proxy error: {e}".encode())

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "3600")

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[proxy] {fmt % args}\n")


def main():
    httpd = http.server.HTTPServer(("127.0.0.1", LISTEN_PORT), CorsProxy)
    print(f"CORS proxy listening on  http://localhost:{LISTEN_PORT}")
    print(f"Forwarding to            {UPSTREAM}")
    print(f"In demo: set URL to      http://localhost:{LISTEN_PORT}/v1/chat/completions")
    print(f"Stop with Ctrl+C")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
