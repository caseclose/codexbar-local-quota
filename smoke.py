"""Integration smoke test on macOS with a supplied CodexBarCLI binary and synthetic data."""
import datetime as dt
import http.client
import json
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from serve_quota import Handler, Server

ROOT = Path(__file__).resolve().parent


def main(cli):
    with tempfile.TemporaryDirectory() as temporary, Server(("127.0.0.1", 0), Handler) as server:
        root = Path(temporary).resolve()
        providers = root / ".config/codexbar/providers"
        providers.mkdir(parents=True)
        plugin = providers / "local-quota.js"
        shutil.copyfile(ROOT / plugin.name, plugin)
        origin = f"http://127.0.0.1:{server.server_port}"
        config = providers.parent / "config.json"
        config.write_text(json.dumps({"version": 1, "providers": [{"id": "local-quota", "enabled": True,
                                "pluginSettings": {"BASE_URL": origin}}]}))
        server.feed_path = root / "quota.json"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        env = {"PATH": "/usr/bin:/bin", "CFFIXED_USER_HOME": str(root), "CODEXBAR_CONFIG": str(config),
               "CODEXBAR_DISABLE_KEYCHAIN_ACCESS": "1"}
        def command(*args):
            return subprocess.run([cli, *args], env=env, capture_output=True, text=True, timeout=20)
        listing = command("plugins", "list")
        assert listing.returncode == 0 and listing.stdout.strip().splitlines() == [
            f"local-quota\tLocal Quota\t{plugin}"], (listing.stdout.replace(str(root), "<fixture>"), listing.stderr.replace(str(root), "<fixture>"))
        fetch = ["plugins", "fetch", "local-quota", "--json"]
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        def instant(delta):
            return (now + dt.timedelta(seconds=delta)).strftime("%Y-%m-%dT%H:%M:%SZ")
        def publish(**overrides):
            data = dict(version=1, observedAt=instant(-2), used=25, limit=100, currency="USD")
            data.update(overrides)
            tmp = root / "next.json"
            tmp.write_text(json.dumps(data))
            tmp.replace(server.feed_path)
        def snapshot():
            result = command(*fetch)
            assert result.returncode == 0, result.stderr
            return json.loads(result.stdout)
        publish(resetsAt=instant(3600))
        denied = command(*fetch)
        assert denied.returncode != 0 and "approv" in denied.stderr.lower(), denied.stderr
        master, slave = pty.openpty()
        try:
            with subprocess.Popen([cli, *fetch], stdin=slave, stdout=slave, stderr=slave, env=env) as proc:
                os.close(slave)
                def expect(prompt):
                    output = b""
                    deadline = time.monotonic() + 15
                    while prompt.encode() not in output:
                        if time.monotonic() > deadline or proc.poll() is not None:
                            raise RuntimeError("Expected test approval prompt: " + repr(output))
                        if select.select([master], [], [], 0.25)[0]:
                            output += os.read(master, 8192)
                try:
                    expect("Type " + origin + " to confirm:")
                    os.write(master, (origin + "\n").encode())
                    expect("Approve?")
                    os.write(master, b"y\n")
                    assert proc.wait(timeout=20) == 0
                finally:
                    if proc.poll() is None:
                        proc.kill()
        finally:
            os.close(master)
        assert (root / "Library/Application Support/CodexBar/plugin-approvals.json").is_file()
        first = snapshot()
        assert first["primary"]["usedPercent"] == 25 and first["primary"]["resetsAt"] == instant(3600)
        rows = {r["label"]: r["value"] for r in first["details"][0]["rows"]}
        assert rows["Remaining"] == "75.00 USD" and rows["Observed at (UTC)"].startswith(instant(-2)[:-1])
        publish(observedAt=instant(-1200))
        assert command(*fetch).returncode != 0
        publish(used=125)
        fresh = snapshot()
        assert fresh["primary"]["usedPercent"] == 125 and fresh["primary"].get("resetsAt") is None
        assert fresh["details"][0]["rows"][0]["value"] == "-25.00 USD"
        publish(used=0, limit=0)
        assert snapshot().get("primary") is None
        publish(privateField="synthetic")
        def request(headers):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                conn.request("GET", "/v1/quota", headers=headers)
                response = conn.getresponse()
                return response.status, response.read()
            finally:
                conn.close()
        assert request({}) == (503, b'{"error":"quota unavailable"}')
        assert request({"Host": "example.invalid"})[0] == 403
        assert request({"Origin": "https://example.invalid"})[0] == 403
        print("PASS: isolated discovery and approval, fresh, stale, recovered, overage, omitted reset, "
              "zero allocation, source timestamp, redaction and loopback HTTP checks")
        server.shutdown()


if __name__ == "__main__":
    main(str(Path(sys.argv[1]).resolve()))
