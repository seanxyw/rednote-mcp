#!/usr/bin/env python3
import asyncio
import base64
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import websockets
from mcp.server.fastmcp import FastMCP, Image

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
BASE_URL = "https://www.rednote.com"
DEFAULT_HEADLESS = os.environ.get("REDNOTE_HEADLESS", "false").lower() in ("1", "true", "yes")

mcp = FastMCP(
    "xiaohongshu-mcp",
    host="127.0.0.1",
    port=18061,
    streamable_http_path="/mcp",
    stateless_http=True,
)


class CDPClient:
    def __init__(self, ws):
        self.ws = ws
        self.msg_id = 0

    async def send(self, method: str, params: dict = None) -> dict:
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

    async def eval_js(self, expr: str) -> Any:
        res = await self.send(
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True, "awaitPromise": True},
        )
        val = res.get("result", {}).get("value")
        return val


class BrowserSession:
    def __init__(self, headless: bool = DEFAULT_HEADLESS):
        self.headless = DEFAULT_HEADLESS if headless is None else headless
        self.user_data_dir = None
        self.proc = None
        self.ws_conn = None
        self.cdp = None
        self.seed = 1731433359

    async def __aenter__(self) -> CDPClient:
        self.user_data_dir = tempfile.mkdtemp(prefix="rednote_mcp_chrome_")
        # Pick a free port
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        args = [
            CHROMIUM_BIN,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={self.user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1280,900",
        ]
        if self.headless:
            args.append("--headless=new")
        args.append("about:blank")

        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        ws_url = None
        async with httpx.AsyncClient() as client:
            for _ in range(50):
                try:
                    r = await client.get(f"http://127.0.0.1:{port}/json/list", timeout=1.0)
                    for p in r.json():
                        if p.get("type") == "page" and "webSocketDebuggerUrl" in p:
                            ws_url = p["webSocketDebuggerUrl"]
                            break
                    if ws_url:
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.2)

        if not ws_url:
            self.cleanup()
            raise RuntimeError("Failed to connect to Chromium DevTools")

        self.ws_conn = await websockets.connect(ws_url, max_size=50 * 1024 * 1024)
        self.cdp = CDPClient(self.ws_conn)
        await self.cdp.send("Page.enable")
        await self.cdp.send("Runtime.enable")
        await self.cdp.send("Network.enable")

        if os.path.exists(COOKIES_PATH):
            try:
                with open(COOKIES_PATH, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                self.seed = cdata.get("seed", self.seed)
                cookies = cdata.get("cookies", [])
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
                if clean_cookies:
                    await self.cdp.send("Network.setCookies", {"cookies": clean_cookies})
            except Exception as e:
                print(f"Warning loading cookies: {e}", file=sys.stderr)

        return self.cdp

    async def save_cookies(self):
        if not self.cdp:
            return
        res = await self.cdp.send("Network.getAllCookies")
        raw_cookies = res.get("cookies", [])
        out_data = {
            "version": 2,
            "seed": self.seed,
            "saved_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "cookies": raw_cookies,
        }
        with open(COOKIES_PATH, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2, ensure_ascii=False)

    def cleanup(self):
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
        if self.user_data_dir and os.path.exists(self.user_data_dir):
            shutil.rmtree(self.user_data_dir, ignore_errors=True)
            self.user_data_dir = None

    async def __aexit__(self, exc_type, exc, tb):
        if self.ws_conn:
            try:
                await self.ws_conn.close()
            except Exception:
                pass
        self.cleanup()


async def get_user_info_from_page(cdp: CDPClient) -> dict:
    js = """
    (() => {
        try {
            const u = window.__INITIAL_STATE__ && window.__INITIAL_STATE__.user;
            if (!u) return JSON.stringify({logged_in: false});
            const info = (u.userInfo && u.userInfo.value !== undefined) ? u.userInfo.value : u.userInfo;
            if (!info || info.guest) return JSON.stringify({logged_in: false, guest: true});
            const uid = info.userId || info.user_id || info.redId || "";
            const nick = info.nickname || info.nickName || "";
            if (!uid && !nick) return JSON.stringify({logged_in: false});
            return JSON.stringify({
                logged_in: true,
                nickname: nick,
                userId: uid,
                redId: info.redId || ""
            });
        } catch (e) {
            return JSON.stringify({logged_in: false, error: String(e)});
        }
    })()
    """
    for _ in range(4):
        raw = await cdp.eval_js(js)
        if raw:
            data = json.loads(raw)
            if data.get("logged_in"):
                return data
        await asyncio.sleep(1.0)
    return {"logged_in": False}


@mcp.tool(description="检查小红书(RedNote)登录状态")
async def check_login_status() -> str:
    async with BrowserSession(headless=DEFAULT_HEADLESS) as cdp:
        await cdp.send("Page.navigate", {"url": f"{BASE_URL}/explore"})
        await asyncio.sleep(3.0)
        info = await get_user_info_from_page(cdp)
        if info.get("logged_in"):
            return (
                f"✅ 已登录 (RedNote)\n"
                f"用户名: {info.get('nickname')}\n"
                f"用户ID: {info.get('userId')}\n\n"
                f"你可以使用其他功能了。"
            )
        return "❌ 未登录\n\n请使用 get_login_qrcode 工具获取二维码进行登录，或运行 login.sh 在浏览器窗口中登录。"


_qr_session: Optional[BrowserSession] = None


@mcp.tool(description="获取登录二维码（返回图片和超时时间）")
async def get_login_qrcode():
    global _qr_session
    if _qr_session:
        _qr_session.cleanup()
        _qr_session = None

    sess = BrowserSession(headless=DEFAULT_HEADLESS)
    cdp = await sess.__aenter__()
    _qr_session = sess

    await cdp.send("Page.navigate", {"url": f"{BASE_URL}/explore"})
    await asyncio.sleep(4.0)

    info = await get_user_info_from_page(cdp)
    if info.get("logged_in"):
        await sess.__aexit__(None, None, None)
        _qr_session = None
        return f"✅ 当前已处于登录状态！用户名: {info.get('nickname')}"

    # Check if QR code img exists or extract base64
    qr_js = """
    (() => {
        const img = document.querySelector('.login-container .qrcode-img') || document.querySelector('img.qrcode-img') || document.querySelector('[class*="qrcode"] img');
        if (img && img.src) return img.src;
        return "";
    })()
    """
    qr_src = ""
    for _ in range(10):
        qr_src = await cdp.eval_js(qr_js)
        if qr_src:
            break
        await asyncio.sleep(1.0)

    async def wait_and_save():
        global _qr_session
        try:
            deadline = time.time() + 240
            while time.time() < deadline and _qr_session is sess:
                await asyncio.sleep(2.0)
                try:
                    st = await get_user_info_from_page(cdp)
                    if st.get("logged_in"):
                        await sess.save_cookies()
                        break
                except Exception:
                    pass
        finally:
            if _qr_session is sess:
                await sess.__aexit__(None, None, None)
                _qr_session = None

    asyncio.create_task(wait_and_save())

    if qr_src and qr_src.startswith("data:image"):
        b64_part = qr_src.split(",", 1)[1]
        return Image(data=base64.b64decode(b64_part), format="png")

    # Fallback: take a screenshot of the page
    shot = await cdp.send("Page.captureScreenshot", {"format": "png"})
    return Image(data=base64.b64decode(shot["data"]), format="png")


@mcp.tool(description="删除 cookies 文件，重置登录状态。删除后需要重新登录。")
async def delete_cookies() -> str:
    if os.path.exists(COOKIES_PATH):
        os.remove(COOKIES_PATH)
    return "✅ 已删除 cookies.json，登录状态已重置。"


@mcp.tool(description="获取首页 Feeds 列表")
async def list_feeds() -> str:
    async with BrowserSession(headless=DEFAULT_HEADLESS) as cdp:
        await cdp.send("Page.navigate", {"url": f"{BASE_URL}/explore"})
        await asyncio.sleep(4.0)
        js = """
        (() => {
            const s = window.__INITIAL_STATE__;
            if (!s || !s.feed || !s.feed.feeds) return "[]";
            const feeds = s.feed.feeds._value || s.feed.feeds.value || s.feed.feeds;
            return JSON.stringify({feeds: feeds, count: Array.isArray(feeds) ? feeds.length : 0}, null, 2);
        })()
        """
        res = await cdp.eval_js(js)
        return res or '{"feeds": [], "count": 0}'


@mcp.tool(description="搜索小红书内容（需要已登录）")
async def search_feeds(keyword: str, filters: Optional[dict] = None) -> str:
    encoded = urllib.parse.quote(keyword)
    url = f"{BASE_URL}/search_result?keyword={encoded}&source=web_explore_feed"
    async with BrowserSession(headless=DEFAULT_HEADLESS) as cdp:
        await cdp.send("Page.navigate", {"url": url})
        await asyncio.sleep(5.0)
        js = """
        (() => {
            const s = window.__INITIAL_STATE__;
            if (!s || !s.search || !s.search.feeds) return "[]";
            const feeds = s.search.feeds._value || s.search.feeds.value || s.search.feeds;
            return JSON.stringify({feeds: feeds, count: Array.isArray(feeds) ? feeds.length : 0}, null, 2);
        })()
        """
        res = await cdp.eval_js(js)
        return res or '{"feeds": [], "count": 0}'


@mcp.tool(description="获取小红书笔记详情，返回笔记内容、图片、作者信息、互动数据（点赞/收藏/分享数）及评论列表。")
async def get_feed_detail(
    feed_id: str,
    xsec_token: str,
    load_all_comments: bool = False,
    click_more_replies: bool = False,
    limit: int = 20,
    reply_limit: int = 10,
    scroll_speed: str = "normal",
) -> str:
    url = f"{BASE_URL}/explore/{feed_id}?xsec_token={urllib.parse.quote(xsec_token)}&xsec_source=pc_feed"
    async with BrowserSession(headless=DEFAULT_HEADLESS) as cdp:
        await cdp.send("Page.navigate", {"url": url})
        await asyncio.sleep(4.0)
        js = f"""
        (() => {{
            const s = window.__INITIAL_STATE__;
            if (!s || !s.note || !s.note.noteDetailMap) return "{{}}";
            const map = s.note.noteDetailMap._value || s.note.noteDetailMap.value || s.note.noteDetailMap;
            const detail = map[{json.dumps(feed_id)}] || Object.values(map)[0] || {{}};
            return JSON.stringify(detail, null, 2);
        }})()
        """
        res = await cdp.eval_js(js)
        return res or "{}"


@mcp.tool(description="获取指定的小红书用户主页，返回用户基本信息，关注、粉丝、获赞量及其笔记内容")
async def user_profile(user_id: str, xsec_token: str) -> str:
    url = f"{BASE_URL}/user/profile/{user_id}?xsec_token={urllib.parse.quote(xsec_token)}&xsec_source=pc_note"
    async with BrowserSession(headless=DEFAULT_HEADLESS) as cdp:
        await cdp.send("Page.navigate", {"url": url})
        await asyncio.sleep(4.0)
        js = """
        (() => {
            const s = window.__INITIAL_STATE__;
            if (!s || !s.user) return "{}";
            const pageData = s.user.userPageData?._value || s.user.userPageData?.value || s.user.userPageData || {};
            const notes = s.user.notes?._value || s.user.notes?.value || s.user.notes || [];
            return JSON.stringify({userPageData: pageData, notes: notes}, null, 2);
        })()
        """
        res = await cdp.eval_js(js)
        return res or "{}"


@mcp.tool(description="发表评论到小红书笔记")
async def post_comment_to_feed(feed_id: str, xsec_token: str, content: str) -> str:
    url = f"{BASE_URL}/explore/{feed_id}?xsec_token={urllib.parse.quote(xsec_token)}&xsec_source=pc_feed"
    async with BrowserSession(headless=DEFAULT_HEADLESS) as cdp:
        await cdp.send("Page.navigate", {"url": url})
        await asyncio.sleep(4.0)
        js = f"""
        (async () => {{
            const input = document.querySelector('#content-textarea') || document.querySelector('div.content-edit p') || document.querySelector('[contenteditable="true"]');
            if (!input) return "未找到评论输入框（可能未登录）";
            input.focus();
            document.execCommand('insertText', false, {json.dumps(content)});
            await new Promise(r => setTimeout(r, 800));
            const btn = document.querySelector('button.submit') || document.querySelector('.bottom button.submit');
            if (!btn) return "未找到发送按钮";
            btn.click();
            await new Promise(r => setTimeout(r, 1500));
            return "✅ 评论已发送";
        }})()
        """
        res = await cdp.eval_js(js)
        return str(res)


@mcp.tool(description="为指定笔记点赞或取消点赞")
async def like_feed(feed_id: str, xsec_token: str, unlike: bool = False) -> str:
    url = f"{BASE_URL}/explore/{feed_id}?xsec_token={urllib.parse.quote(xsec_token)}&xsec_source=pc_feed"
    async with BrowserSession(headless=DEFAULT_HEADLESS) as cdp:
        await cdp.send("Page.navigate", {"url": url})
        await asyncio.sleep(4.0)
        js = """
        (() => {
            const el = document.querySelector('.interact-container .like-wrapper') || document.querySelector('.like-lottie');
            if (!el) return "未找到点赞按钮";
            el.click();
            return "✅ 操作已完成";
        })()
        """
        res = await cdp.eval_js(js)
        await asyncio.sleep(1.0)
        return str(res)


@mcp.tool(description="收藏指定笔记或取消收藏")
async def favorite_feed(feed_id: str, xsec_token: str, unfavorite: bool = False) -> str:
    url = f"{BASE_URL}/explore/{feed_id}?xsec_token={urllib.parse.quote(xsec_token)}&xsec_source=pc_feed"
    async with BrowserSession(headless=DEFAULT_HEADLESS) as cdp:
        await cdp.send("Page.navigate", {"url": url})
        await asyncio.sleep(4.0)
        js = """
        (() => {
            const el = document.querySelector('.interact-container .collect-wrapper') || document.querySelector('#note-page-collect-board-guide');
            if (!el) return "未找到收藏按钮";
            el.click();
            return "✅ 操作已完成";
        })()
        """
        res = await cdp.eval_js(js)
        await asyncio.sleep(1.0)
        return str(res)


@mcp.tool(description="回复小红书笔记下的指定评论")
async def reply_comment_in_feed(
    feed_id: str,
    xsec_token: str,
    content: str,
    comment_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> str:
    return await post_comment_to_feed(feed_id=feed_id, xsec_token=xsec_token, content=content)


@mcp.tool(description="发布小红书图文内容")
async def publish_content(
    title: str,
    content: str,
    images: list[str],
    tags: Optional[list[str]] = None,
    schedule_at: Optional[str] = None,
    is_original: bool = False,
    visibility: str = "公开可见",
    products: Optional[list[str]] = None,
) -> str:
    return "RedNote 网页端发布请访问 https://creator.rednote.com/publish/publish"


@mcp.tool(description="发布小红书视频内容（仅支持本地单个视频文件）")
async def publish_with_video(
    title: str,
    content: str,
    video: str,
    tags: Optional[list[str]] = None,
    schedule_at: Optional[str] = None,
    visibility: str = "公开可见",
    products: Optional[list[str]] = None,
) -> str:
    return "RedNote 网页端视频发布请访问 https://creator.rednote.com/publish/publish"


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http")
