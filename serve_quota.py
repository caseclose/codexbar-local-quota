#!/usr/bin/env python3
"""Serve one normalized quota on IPv4 loopback. Python 3.8+, no dependencies."""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import stat
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlsplit

MAX_BYTES = 65536
FIELDS = {"version", "used", "limit", "observedAt", "resetsAt", "currency"}


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z", value):
        raise ValueError("timestamp")
    dt.datetime.fromisoformat(value[:-1] + "+00:00")


def read_feed(path):
    if path is None:
        return {"version": 1, "used": 25, "limit": 100, "currency": "USD",
                "observedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    return validate_feed(read_json(path))


def read_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("regular file required")
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("size")
    return json.loads(raw)


def validate_feed(obj):
    if (not isinstance(obj, dict) or set(obj) - FIELDS or type(obj.get("version")) is not int
            or obj["version"] != 1):
        raise ValueError("schema")
    for key in ("used", "limit"):
        n = obj.get(key)
        if type(n) not in (int, float) or not math.isfinite(n) or n < 0:
            raise ValueError("amount")
    timestamp(obj.get("observedAt"))
    if obj.get("resetsAt") is not None:
        timestamp(obj["resetsAt"])
    if obj.get("currency") is not None and not re.fullmatch(r"[A-Z]{3}", obj["currency"]):
        raise ValueError("currency")
    return obj


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True

    def get_request(self):
        conn, addr = super().get_request()
        conn.settimeout(3)
        return conn, addr


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.headers.get_all("Host") != [f"127.0.0.1:{self.server.server_port}"] or "Origin" in self.headers:
            self.reply(403, {"error": "local requests only"})
        elif urlsplit(self.path).path == "/v1/page":
            self.page_snapshot()
        elif self.path != "/v1/quota":
            self.reply(404, {"error": "not found"})
        else:
            try:
                data = read_feed(self.server.feed_path)
            except (OSError, ValueError, TypeError, OverflowError, RecursionError):
                self.reply(503, {"error": "quota unavailable"})
                return
            self.reply(200, data)

    def page_snapshot(self):
        params = parse_qs(urlsplit(self.path).query)
        urls = params.get("url", [])
        if len(urls) != 1 or len(urls[0]) > 2048:
            self.reply(400, {"state": "invalid"})
            return
        path = getattr(self.server, "page_state", None)
        if not path:
            self.reply(200, {"state": "not-installed"})
            return
        try:
            record = read_json(path)
            if not isinstance(record, dict) or record.get("page") != urls[0]:
                result = {"state": "loading"}
            elif record.get("state") == "ready":
                result = {"state": "ready", "quota": validate_feed(record["quota"])}
            else:
                state = record.get("state")
                result = {"state": state if state in ("loading", "signin", "invalid", "unrecognized", "unavailable") else "unavailable"}
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            result = {"state": "loading"}
        self.reply(200, result)

    def reply(self, status, data):
        body = json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="Read this normalized JSON file on every request")
    source.add_argument("--demo", action="store_true", help="Serve synthetic data for testing")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--page-state", type=Path, help="Optional local WebKit reader snapshot")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1–65535")
    with Server(("127.0.0.1", args.port), Handler) as server:
        server.feed_path = args.file
        server.page_state = args.page_state
        print(f"http://127.0.0.1:{server.server_port}/v1/quota" + (" (synthetic demo)" if args.demo else ""), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
