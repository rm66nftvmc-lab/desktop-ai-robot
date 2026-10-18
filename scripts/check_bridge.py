"""Save an authenticated, content-free report from the local Bridge."""
import argparse
import http.cookiejar
import json
import os
from datetime import datetime
from pathlib import Path
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("invalid port")
    # Same precedence as the Windows launcher; never print the access key.
    anchor = Path(os.environ.get("ROBOT_DATA_ANCHOR") or
                  str(Path(os.environ.get("PROGRAMDATA", str(Path.home()))) / "DesktopAiRobot/data-dir.txt"))
    directory = os.environ.get("ROBOT_DATA_DIR") or (
        anchor.read_text(encoding="utf-8").strip() if anchor.is_file() else
        str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DesktopAiRobot"))
    data_dir = Path(directory)
    base = f"http://127.0.0.1:{args.port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    token = (data_dir / "access-token.txt").read_text(encoding="utf-8").strip()
    with opener.open(urllib.request.Request(base + "/api/login",
        data=json.dumps({"token": token}).encode(), headers={"Content-Type": "application/json"}), timeout=10) as response:
        response.read()
    with opener.open(base + "/api/diagnostics", timeout=30) as response:
        report = json.load(response)
    output = args.output or data_dir / f"robot-diagnostics-{datetime.now():%Y%m%d-%H%M%S}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Bridge:", report["bridge"], "| Device:", report["device"]["connected"], "| Task:", report["task"]["state"])
    maintenance = report.get("maintenance", {})
    if maintenance:
        print("Version:", maintenance["version"], "| Database:", maintenance["database"]["state"],
              "| Low disk space:", maintenance["low_disk_space"])
    print("Report saved:", output)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(f"Diagnostic check failed ({type(exc).__name__}). Check the local Bridge and data directory.") from None
