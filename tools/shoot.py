"""Drive the app in headless Chrome and save screenshots — the visual check for rig and actor work.

usage: python tools/shoot.py <steps.json> [--out shots] [--serve] [--port 8765] [--query "avatar=rpm-detailed"]

steps.json is a list of:
  {"ready": true}                      wait for the actor, hide the access screen, snap the camera
  {"js": "<expression>", "print": true}  evaluate (promises awaited); print the result
  {"wait": seconds}
  {"shot": "name", "crop": [x, y, w, h], "scale": 2}   screenshot (optional crop and upscale)

Headless Chrome renders WebGL in software at a few frames per second, so motion is slow; poll
for state in your JS rather than sleeping. Exits 1 if the page logged an error or exception.
"""

import argparse
import asyncio
import base64
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]
READY_JS = """(async () => {
  for (let i = 0; i < 900 && !window.director; i++) await new Promise(r => setTimeout(r, 100));
  if (!window.director) return 'actor never loaded';
  document.getElementById('access-screen').classList.add('hidden');
  director.nextIdleGlance = 1e9;
  director.stage.shotTime = 0.05;
  await new Promise(r => setTimeout(r, 4000));
  return avatar.capabilities;
})()"""
IGNORED_ERRORS = ("favicon.ico",)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(url: str, seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            OPENER.open(url, timeout=2).read()
            return True
        except Exception:
            time.sleep(0.3)
    return False


def kill_tree(proc):
    if proc and proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()


def save_png(data: bytes, path: str, crop=None, scale=1):
    if crop or scale != 1:
        from PIL import Image
        image = Image.open(io.BytesIO(data))
        if crop:
            x, y, w, h = crop
            image = image.crop((x, y, x + w, y + h))
        if scale != 1:
            image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
        image.save(path)
    else:
        with open(path, "wb") as f:
            f.write(data)


async def run(steps, url, out):
    logs, errors = [], []
    chrome = next((p for p in CHROME_PATHS if os.path.exists(p)), None)
    if not chrome:
        raise SystemExit("Chrome or Edge not found")
    port = free_port()
    profile = tempfile.mkdtemp(prefix="shoot-profile-")
    proc = subprocess.Popen([
        chrome, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
        "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
        "--window-size=1400,900", "--autoplay-policy=no-user-gesture-required",
        "--no-first-run", "--disable-sync", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_for(f"http://127.0.0.1:{port}/json/version", 20):
            raise SystemExit("Chrome's debugging port never answered")
        page = next(t for t in json.load(OPENER.open(f"http://127.0.0.1:{port}/json")) if t["type"] == "page")
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=2 ** 27, proxy=None) as ws:
            pending, counter = {}, [0]

            async def reader():
                async for raw in ws:
                    m = json.loads(raw)
                    if m.get("id") in pending:
                        pending.pop(m["id"]).set_result(m)
                    elif m.get("method") == "Runtime.consoleAPICalled":
                        p = m["params"]
                        text = " ".join(str(a.get("value", a.get("description", ""))) for a in p["args"])
                        logs.append(f"[console.{p['type']}] {text}")
                        if p["type"] == "error":
                            errors.append(text)
                    elif m.get("method") == "Runtime.exceptionThrown":
                        d = m["params"]["exceptionDetails"]
                        text = d.get("exception", {}).get("description", d.get("text"))
                        logs.append(f"[exception] {text}")
                        errors.append(text)
                    elif m.get("method") == "Log.entryAdded":
                        e = m["params"]["entry"]
                        text = f"{e['text']} {e.get('url', '')}"
                        if e["level"] == "error" and not any(s in text for s in IGNORED_ERRORS):
                            logs.append(f"[log.error] {text}")
                            errors.append(text)

            task = asyncio.create_task(reader())

            async def call(method, **params):
                counter[0] += 1
                future = asyncio.get_event_loop().create_future()
                pending[counter[0]] = future
                await ws.send(json.dumps({"id": counter[0], "method": method, "params": params}))
                return await asyncio.wait_for(future, 600)

            for domain in ("Runtime", "Log", "Page"):
                await call(f"{domain}.enable")
            await call("Page.navigate", url=url)

            for step in steps:
                if step.get("ready"):
                    step = {"js": READY_JS, "print": True}
                if "wait" in step:
                    await asyncio.sleep(step["wait"])
                elif "js" in step:
                    r = await call("Runtime.evaluate", expression=step["js"], awaitPromise=True, returnByValue=True)
                    result = r.get("result", {})
                    if "exceptionDetails" in result:
                        text = result["exceptionDetails"].get("exception", {}).get("description")
                        logs.append(f"[js-error] {step['js'][:80]!r} -> {text}")
                        errors.append(text)
                    elif step.get("print"):
                        logs.append(f"[js] {json.dumps(result.get('result', {}).get('value'))[:3000]}")
                elif "shot" in step:
                    r = await call("Page.captureScreenshot", format="png")
                    path = os.path.join(out, step["shot"] + ".png")
                    save_png(base64.b64decode(r["result"]["data"]), path, step.get("crop"), step.get("scale", 1))
                    logs.append(f"[shot] {path}")
            task.cancel()
    finally:
        kill_tree(proc)
        shutil.rmtree(profile, ignore_errors=True)
    return logs, errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("steps")
    parser.add_argument("--out", default="shots")
    parser.add_argument("--serve", action="store_true", help="start uvicorn for the run")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--query", default="", help="page query string, e.g. avatar=rpm-default")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    with open(args.steps) as f:
        steps = json.load(f)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server = None
    if args.serve:
        server = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(args.port), "--log-level", "warning"],
                                  cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_for(f"http://127.0.0.1:{args.port}/gestures", 30):
            raise SystemExit(f"app not reachable on port {args.port}")
        url = f"http://127.0.0.1:{args.port}/" + (f"?{args.query}" if args.query else "")
        logs, errors = asyncio.run(run(steps, url, args.out))
    finally:
        kill_tree(server)
    print("\n".join(logs))
    print(f"\n{len(errors)} error(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
