"""Install the optional local macOS dashboard reader from this checkout."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import plistlib
import shutil
import socket
import subprocess
import tempfile

HOME = Path.home()
ROOT = Path(__file__).resolve().parent
SUPPORT = HOME / "Library/Application Support/Local Quota Page"
DOMAIN = f"gui/{os.getuid()}"
PREFIX = "io.github.caseclose.local-quota."
CONFIG = HOME / ".config/codexbar/config.json"

def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        f.write(data)
    os.replace(f.name, path)

def job(name, args):
    label = PREFIX + name
    plist = HOME / "Library/LaunchAgents" / (label + ".plist")
    spec = dict(Label=label, ProgramArguments=list(map(str, args)), RunAtLoad=True, KeepAlive=True,
                ThrottleInterval=15, LimitLoadToSessionType="Aqua", Umask=63)
    write_atomic(plist, plistlib.dumps(spec))
    subprocess.run(["launchctl", "bootstrap", DOMAIN, str(plist)], check=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--feed", type=Path, default=SUPPORT / "quota.json",
                        help="Optional normalized feed used when the dashboard URL is blank")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Invalid port")
    os.umask(0o077)
    SUPPORT.mkdir(parents=True, exist_ok=True)
    own_bridge = subprocess.run(["launchctl","print",DOMAIN+"/"+PREFIX+"http"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not own_bridge:
        with socket.socket() as probe:
            try: probe.bind(("127.0.0.1", args.port))
            except OSError: parser.error("Port in use. Choose --port or stop the previous feed server first.")
    app = SUPPORT / "Local Quota Page Reader.app"
    with tempfile.TemporaryDirectory(dir=SUPPORT) as tmp:
        staged = Path(tmp) / app.name
        contents = staged / "Contents"
        exe = contents / "MacOS/PageReader"
        exe.parent.mkdir(parents=True)
        (contents / "Resources").mkdir()
        shutil.copyfile(ROOT/"page-reader/detect.js", contents/"Resources/detect.js")
        info = dict(CFBundleIdentifier="io.github.caseclose.local-quota.reader", CFBundleExecutable=exe.name,
                    CFBundleName="Local Quota Page Reader", CFBundlePackageType="APPL", CFBundleVersion="1", LSUIElement=True)
        (contents/"Info.plist").write_bytes(plistlib.dumps(info))
        subprocess.run(["xcrun","swiftc","-O",str(ROOT/"page-reader/main.swift"),"-o",str(exe)], check=True)
        subprocess.run(["codesign","--force","--sign","-",str(staged)], check=True)
        for name in ("http","reader"):
            subprocess.run(["launchctl","bootout",DOMAIN+"/"+PREFIX+name],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if app.exists(): app.rename(Path(tmp)/"previous.app")
        staged.rename(app)
    bridge = SUPPORT/"serve_quota.py"
    write_atomic(bridge,(ROOT/"serve_quota.py").read_bytes())
    write_atomic(CONFIG.parent/"providers/local-quota.js",(ROOT/"local-quota.js").read_bytes())
    with CONFIG.with_suffix(".json.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {"version":1,"providers":[]}
        providers = cfg.setdefault("providers",[])
        item = next((p for p in providers if p["id"]=="local-quota"),None)
        if item is None:
            item = {"id":"local-quota"}
            providers.append(item)
        item["enabled"] = True
        item.setdefault("pluginSettings",{})["BASE_URL"] = f"http://127.0.0.1:{args.port}"
        write_atomic(CONFIG,(json.dumps(cfg,indent=2)+"\n").encode())
    job("http", ["/usr/bin/python3","-B",bridge,"--file",args.feed.expanduser().resolve(),
                 "--page-state",SUPPORT/"page.json","--port",args.port])
    job("reader", [app/"Contents/MacOS/PageReader"])
    print("Installed. In CodexBar > Settings > Plugins > Local Quota, enter your dashboard URL.")
    print(f"Approve http://127.0.0.1:{args.port} in CodexBar if prompted.")

if __name__ == "__main__":
    main()
