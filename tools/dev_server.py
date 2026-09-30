#!/usr/bin/env python3
"""Lokaler Testserver für ./frontend mit derselben strengen CSP wie produktiv (nur an 127.0.0.1).

Aufruf:  python3 tools/dev_server.py [port]      dann  http://localhost:8769
Wenn die Seite hier ohne Konsolenfehler läuft, läuft sie auch hinter der Produktions-Konfiguration.
"""
import http.server
import os
import sys
from functools import partial

CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "font-src 'none'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8769
    print(f"http://localhost:{port}  (Strg+C beendet)")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=WEB)).serve_forever()
