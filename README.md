# RedNote MCP (`rednote.com` MCP Server)

[English](#rednote-mcp-rednotecom-mcp-server) | [中文说明](#rednote-mcp-中文说明)

An MCP (Model Context Protocol) server and login utility tailored for **RedNote (`https://www.rednote.com`)** — the overseas/North American web edition of Xiaohongshu.

> **Credits & Acknowledgements**  
> The tool definitions, interface design, and core workflow of this project are inspired by and adapted from [**xpzouying/xiaohongshu-mcp**](https://github.com/xpzouying/xiaohongshu-mcp) created by [**@xpzouying**](https://github.com/xpzouying). Special thanks to the original author for their pioneering work in the Xiaohongshu MCP ecosystem!

---

## Why This Adaptation?

The original [`xpzouying/xiaohongshu-mcp`](https://github.com/xpzouying/xiaohongshu-mcp) hardcodes `https://www.xiaohongshu.com`. However, for overseas and North American accounts (e.g., `CA` / `US`), scanning the login QR code on `xiaohongshu.com` automatically redirects the browser to **`https://www.rednote.com`** and issues authentication cookies (`web_session`, `id_token`) under the `.rednote.com` domain. Because cookies are not shared across `.xiaohongshu.com` and `.rednote.com`, requests to `xiaohongshu.com` remain in an unauthenticated guest state.

This project connects directly to **`https://www.rednote.com`** and defaults to **non-headless mode (visible browser window)** to minimize anti-bot triggers and allow easy manual verification when needed.

---

## Key Features

- **Native `rednote.com` Support**: Login, home feed, search, note details, user profiles, and interactions all operate directly on `https://www.rednote.com`.
- **Non-Headless by Default**: Launches a visible Chromium window by default (can be switched to headless mode via `REDNOTE_HEADLESS=true`).
- **Supports Both `stdio` and `streamable-http`**: Can be mounted directly via MCP `stdio` without managing a separate background HTTP daemon.

---

## Available MCP Tools

| Tool Name | Description |
| :--- | :--- |
| `check_login_status` | Check RedNote login status and return the current user's nickname and ID |
| `get_login_qrcode` | Fetch a login QR code and wait in the background to automatically save cookies |
| `delete_cookies` | Delete local `cookies.json` to reset login state |
| `list_feeds` | Fetch recommended notes from the RedNote home feed |
| `search_feeds` | Search RedNote notes by keyword (requires login) |
| `get_feed_detail` | Fetch full details, images, and engagement metrics for a specific note |
| `user_profile` | Fetch user profile info and published notes |
| `post_comment_to_feed` | Post a comment on a note |
| `reply_comment_in_feed` | Reply to a specific comment |
| `like_feed` | Like a note |
| `favorite_feed` | Favorite/bookmark a note |
| `publish_content` | Entry point guide for publishing image/text notes |
| `publish_with_video` | Entry point guide for publishing video notes |

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Log In

Run the login script and scan the QR code (or sign in via phone number) in the opened browser window using the RedNote app. Once logged in, cookies are automatically saved to `cookies.json` (git-ignored):

```bash
./login.sh
```

To check login status only:

```bash
./login.sh --check-only
```

### 3. Configure MCP (`mcp_config.json`)

```json
{
  "mcpServers": {
    "xiaohongshu": {
      "command": "/path/to/start_server.sh",
      "args": []
    }
  }
}
```

### Environment Variables (Optional)

- `REDNOTE_HEADLESS`: Set to `true` to run Chromium in headless mode (defaults to `false` for visible window mode).
- `CHROMIUM_BIN`: Custom path to the Chromium/Chrome executable.
- `COOKIES_PATH`: Custom path to `cookies.json`.

---

## Acknowledgements

- Original Project: [**xpzouying/xiaohongshu-mcp**](https://github.com/xpzouying/xiaohongshu-mcp)
- Original Author: [**@xpzouying**](https://github.com/xpzouying)

---
---

# RedNote MCP 中文说明

针对北美/海外区小红书账号（自动跳转至 **`https://www.rednote.com`**）适配的 MCP (Model Context Protocol) 服务端与登录工具。

> **致谢与原作者说明**  
> 本项目的工具设计、接口规范及核心思路源自 [**@xpzouying**](https://github.com/xpzouying) 开发的开源项目 [**xpzouying/xiaohongshu-mcp**](https://github.com/xpzouying/xiaohongshu-mcp)。感谢原作者在小红书 MCP 生态上的开创性工作！

## 为什么需要这个适配版？

原版 [`xpzouying/xiaohongshu-mcp`](https://github.com/xpzouying/xiaohongshu-mcp) 默认访问 `https://www.xiaohongshu.com`。对于海外区/北美区（如 `CA`/`US`）小红书账号，扫码登录后会被重定向至 `https://www.rednote.com`，登录 Cookie（`web_session`、`id_token`）均签发在 `.rednote.com` 域名下，导致访问 `xiaohongshu.com` 时始终处于未登录的游客状态。

本项目直接对接 **`https://www.rednote.com`**，并默认启用**非无头模式（可见浏览器窗口）**，降低风控拦截概率并支持手动处理安全验证。

## 快速开始

1. **安装依赖**：`pip install -r requirements.txt`
2. **扫码登录**：运行 `./login.sh`，在弹出的浏览器窗口中使用 RedNote App 扫码登录，成功后会自动保存 `cookies.json`。
3. **配置 MCP**：在 `mcp_config.json` 中将 `command` 指向 `/path/to/start_server.sh`。
