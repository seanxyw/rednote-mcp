# RedNote MCP (`rednote.com` 小红书海外版 MCP Server)

针对北美/海外区小红书账号（自动跳转至 **`https://www.rednote.com`**）适配的 MCP (Model Context Protocol) 服务端与登录工具。

## 为什么需要这个适配版？

原版 `xiaohongshu-mcp` 硬编码访问 `https://www.xiaohongshu.com`。对于海外区/北美区（如 `CA`/`US`）小红书账号，扫码登录后会被重定向至 `https://www.rednote.com`，登录 Cookie（`web_session`、`id_token`）均签发在 `.rednote.com` 域名下，导致访问 `xiaohongshu.com` 时始终处于未登录的游客状态。

本项目直接对接 **`https://www.rednote.com`**，并默认启用**非无头模式（可见浏览器窗口）**，降低风控拦截概率并支持手动处理安全验证。

---

## 核心特性

- **原生支持 `rednote.com`**：所有登录、推荐流、搜索、笔记详情、用户主页及互动操作均基于 `https://www.rednote.com`。
- **默认非无头模式（Non-Headless）**：默认弹出真实可见的 Chromium 窗口（可通过环境变量 `REDNOTE_HEADLESS=true` 切换回无头模式）。
- **同时支持 `stdio` 与 `streamable-http`**：可直接通过 MCP `stdio` 协议挂载，无需单独维护常驻后台端口。

---

## 包含工具列表 (MCP Tools)

| 工具名 | 说明 |
| :--- | :--- |
| `check_login_status` | 检查 RedNote 登录状态并返回当前登录昵称与用户 ID |
| `get_login_qrcode` | 获取登录二维码并在后台等待扫码自动保存 Cookie |
| `delete_cookies` | 删除本地 `cookies.json` 重置登录状态 |
| `list_feeds` | 获取 RedNote 首页推荐流笔记列表 |
| `search_feeds` | 按关键词搜索 RedNote 笔记（需已登录） |
| `get_feed_detail` | 获取指定笔记完整详情、图片列表、互动数据 |
| `user_profile` | 获取指定用户主页信息及发布的笔记列表 |
| `post_comment_to_feed` | 对指定笔记发表评论 |
| `reply_comment_in_feed` | 回复指定评论 |
| `like_feed` | 点赞笔记 |
| `favorite_feed` | 收藏笔记 |
| `publish_content` | 图文发布入口指引 |
| `publish_with_video` | 视频发布入口指引 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 登录账号

运行登录脚本，在弹出的浏览器窗口中使用 RedNote App 扫码或手机号登录，登录成功后会自动将凭证保存至 `cookies.json`（已加入 `.gitignore`，不会上传到 Git）：

```bash
./login.sh
```

仅检查当前登录状态：

```bash
./login.sh --check-only
```

### 3. 配置 MCP (`mcp_config.json`)

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

### 环境变量（可选）

- `REDNOTE_HEADLESS`：设为 `true` 时使用无头模式，默认 `false`（可见窗口模式）。
