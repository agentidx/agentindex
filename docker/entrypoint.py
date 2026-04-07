#!/usr/bin/env python3
"""Nerq Trust Oracle — Local MCP server proxy."""
import json
import os
import sys
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

API_URL = os.environ.get("NERQ_API_URL", "https://nerq.ai")
PORT = int(os.environ.get("PORT", "8080"))


class NerqHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/v1/"):
            self._proxy()
        elif self.path == "/health":
            self._json({"status": "ok", "api": API_URL})
        else:
            self._json({"name": "Nerq Trust Oracle", "version": "1.0.0",
                         "endpoints": ["/v1/preflight?target=X", "/v1/discover?q=X",
                                       "/v1/recommend?task=X", "/health"]})

    def do_POST(self):
        if self.path.startswith("/v1/"):
            self._proxy()
        else:
            self.send_error(404)

    def _proxy(self):
        url = f"{API_URL}{self.path}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NerqTrustOracle/1.0"})
            if self.command == "POST":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else None
                req = urllib.request.Request(url, data=body,
                    headers={"Content-Type": "application/json", "User-Agent": "NerqTrustOracle/1.0"})
            resp = urllib.request.urlopen(req, timeout=15)
            data = resp.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self._json({"error": str(e)}, 502)

    def _json(self, obj, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def log_message(self, fmt, *args):
        print(f"[nerq] {args[0]}")


if __name__ == "__main__":
    print(f"Nerq Trust Oracle running on port {PORT}")
    print(f"API: {API_URL}")
    HTTPServer(("0.0.0.0", PORT), NerqHandler).serve_forever()
