#!/usr/bin/env python3
import asyncio
import glob
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
import httpx
import websockets

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_chromium_bin() -> str:
    env_bin = os.environ.get("CHROMIUM_BIN")
    if env_bin and os.path.exists(env_bin):
        return env_bin
    cache_pattern = os.path.expanduser(
        "~/Library/Caches/xiaohongshu-mcp/browser/*/Chromium.app/Contents/MacOS/Chromium"
    )
    matches = sorted(glob.glob(cache_pattern), reverse=True)
    if matches:
        return matches[0]
    chrome_app = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if os.path.exists(chrome_app):
        return chrome_app
    return "chromium"


CHROMIUM_BIN = _find_chromium_bin()
COOKIES_PATH = os.environ.get("COOKIES_PATH", os.path.join(SCRIPT_DIR, "cookies.json"))
TARGET_URL = "https://www.rednote.com/explore"


class CDPClient:
    def __init__(self, ws):
        self.ws = ws
        self.msg_id = 0

    async def send(self, method: str, params: dict = None):
        self.msg_id += 1
        curr_id = self.msg_id
        payload = {"id": curr_id, "method": method}
        if params:
            payload["params"] = params
        await self.ws.send(json.dumps(payload))
        while True:
            raw = await self.ws.recv()
            data = json.loads(raw)
            if data.get("id") == curr_id:
                if "error" in data:
                    raise RuntimeError(f"CDP error in {method}: {data['error']}")
                return data.get("result", {})


async def check_user_state(cdp: CDPClient):
    js = """
    (() => {
        try {
            const u = window.__INITIAL_STATE__ && window.__INITIAL_STATE__.user;
            if (!u) return JSON.stringify({logged_in: false, reason: "no_initial_state", href: location.href});
            const info = (u.userInfo && u.userInfo.value !== undefined) ? u.userInfo.value : u.userInfo;
            const loggedInViaFlag = (u.loggedIn && u.loggedIn.value !== undefined) ? u.loggedIn.value : u.loggedIn;
            if (!info || info.guest) {
                return JSON.stringify({logged_in: false, reason: "guest", href: location.href, loggedInFlag: loggedInViaFlag});
            }
            const uid = info.userId || info.user_id || info.redId || "";
            const nick = info.nickname || info.nickName || "";
            if (!uid && !nick) {
                return JSON.stringify({logged_in: false, reason: "empty_uid_nick", href: location.href});
            }
            return JSON.stringify({
                logged_in: true,
                nickname: nick,
                userId: uid,
                redId: info.redId || "",
                href: location.href
            });
        } catch (e) {
            return JSON.stringify({logged_in: false, reason: String(e)});
        }
    })()
    """
    res = await cdp.send("Runtime.evaluate", {"expression": js, "returnByValue": True})
    val = res.get("result", {}).get("value")
    if not val:
        return {"logged_in": False, "reason": "no_eval_value"}
    return json.loads(val)


async def main():
    headless = "--check-only" in sys.argv
    user_data_dir = tempfile.mkdtemp(prefix="rednote_chrome_")
    port = 19222

    args = [
        CHROMIUM_BIN,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--window-size=1280,900",
    ]
    if headless:
        args.append("--headless=new")
    args.append("about:blank")

    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # Wait for DevTools endpoint
        ws_url = None
        async with httpx.AsyncClient() as client:
            for _ in range(50):
                try:
                    r = await client.get(f"http://127.0.0.1:{port}/json/list", timeout=1.0)
                    pages = r.json()
                    for p in pages:
                        if p.get("type") == "page" and "webSocketDebuggerUrl" in p:
                            ws_url = p["webSocketDebuggerUrl"]
                            break
                    if ws_url:
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.2)

        if not ws_url:
            print("Failed to connect to Chromium DevTools", file=sys.stderr)
            return 1

        seed = 1731433359
        if os.path.exists(COOKIES_PATH):
            try:
                with open(COOKIES_PATH, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                seed = cdata.get("seed", seed)
                cookies = cdata.get("cookies", [])
            except Exception as e:
                print(f"Warning: failed to read existing cookies.json: {e}")
                cookies = []
        else:
            cookies = []

        async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
            cdp = CDPClient(ws)
            await cdp.send("Page.enable")
            await cdp.send("Runtime.enable")
            await cdp.send("Network.enable")

            if cookies:
                clean_cookies = []
                for c in cookies:
                    cc = {
                        "name": c["name"],
                        "value": c["value"],
                        "domain": c["domain"],
                        "path": c.get("path", "/"),
                        "secure": c.get("secure", False),
                        "httpOnly": c.get("httpOnly", False),
                    }
                    if c.get("expires", -1) > 0:
                        cc["expires"] = c["expires"]
                    clean_cookies.append(cc)
                await cdp.send("Network.setCookies", {"cookies": clean_cookies})

            print(f"正在打开 {TARGET_URL} ...")
            await cdp.send("Page.navigate", {"url": TARGET_URL})
            await asyncio.sleep(4.0)

            state = await check_user_state(cdp)
            if state.get("logged_in"):
                print(f"✅ 已登录 RedNote! 昵称: {state.get('nickname')} (ID: {state.get('userId')})")
                return 0

            if headless:
                print(f"❌ 未登录 RedNote (状态: {state})")
                return 2

            print("请在弹出的浏览器窗口中使用 RedNote 扫码或输入手机号登录（最多等待 5 分钟）...")
            deadline = time.time() + 300
            while time.time() < deadline:
                await asyncio.sleep(2.0)
                try:
                    state = await check_user_state(cdp)
                except Exception:
                    # Page might be navigating
                    continue
                if state.get("logged_in"):
                    print(f"🎉 检测到登录成功! 昵称: {state.get('nickname')} (ID: {state.get('userId')})")
                    await asyncio.sleep(2.0)
                    all_cookies_res = await cdp.send("Network.getAllCookies")
                    raw_cookies = all_cookies_res.get("cookies", [])
                    out_data = {
                        "version": 2,
                        "seed": seed,
                        "saved_at": datetime.now(timezone.utc).astimezone().isoformat(),
                        "cookies": raw_cookies,
                    }
                    with open(COOKIES_PATH, "w", encoding="utf-8") as f:
                        json.dump(out_data, f, indent=2, ensure_ascii=False)
                    print(f"✅ 已保存 {len(raw_cookies)} 条 Cookie 到 {COOKIES_PATH}")
                    return 0

            print("❌ 等待登录超时")
            return 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
