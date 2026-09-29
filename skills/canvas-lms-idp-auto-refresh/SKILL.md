---
name: canvas-lms-idp-auto-refresh
description: 通过模拟机构 IDP（CAS/SAML）登录自动刷新 Canvas LMS API Token。适用场景：(1) Canvas API 返回 401 需要重新认证，(2) 为部署在机构 SSO（尤其是使用 id.fudan.edu.cn 风格 IDP 的中国高校）后的 Canvas LMS 搭建自动化 Token 生命周期管理，(3) 用户询问"canvas token 过期"、"自动刷新 token"、"elearning 登录"、"IDP 登录"等问题。处理 RSA 加密密码认证、SSO Ticket 交换、Token 创建及旧 Token 清理。Auto-refresh Canvas LMS API tokens via institutional IDP (CAS/SAML) login. Use when: (1) Canvas API returns 401 and you need to re-authenticate, (2) setting up automated token lifecycle for any Canvas LMS deployment behind an institutional SSO (especially Chinese universities using id.fudan.edu.cn style IDP), (3) user asks about "canvas token expired", "自动刷新token", "elearning login", "IDP登录". Handles RSA-encrypted password auth, SSO ticket exchange, token creation and old token cleanup.
---

# Canvas LMS — IDP Token 自动刷新

通过模拟机构 IDP（CAS/SAML）登录、使用 RSA 加密凭据，自动化 Canvas API Token 刷新。

> English documentation: [README.en.md](README.en.md)

## 工作原理

```
入口 URL → CAS/IDP（lck + authChainCode）→ RSA 加密密码 → authExecute
  → loginToken（JWT）→ authnEngine → SSO ticket → Canvas 会话 → 创建 API Token
  → （可选）按 purpose 删除旧 Token → 输出 NEW_TOKEN=xxx
```

脚本处理完整的 IDP 链路：Cookie 管理、JavaScript 重定向交接、CSRF 提取以及 Canvas API Token 的增删操作。

## 快速开始

### 1. 安装依赖

```bash
cd scripts/
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

依赖包：`requests`、`beautifulsoup4`、`pycryptodome`、`python-dotenv`。

### 2. 配置凭据

将 `.env.example` 复制为 `.env` 并填写：

```bash
cp scripts/.env.example scripts/.env
```

必填字段：
- `ELEARNING_USERNAME` —— 学号/工号
- `ELEARNING_PASSWORD` —— 密码

可选（默认为复旦大学 eLearning）：
- `ELEARNING_ENTRY_URL` —— CAS 入口地址
- `ELEARNING_IDP_BASE_URL` —— IDP 基础 URL
- `ELEARNING_ENTITY_ID` —— SP 实体 ID
- `ELEARNING_TOKEN_PURPOSE` —— 创建 Token 的标签（默认："OpenClaw Auto Refresh Token"）
- `ELEARNING_CLEANUP_OLD_TOKENS` —— 自动删除同 purpose 的旧 Token（默认：false）

### 3. 运行

```bash
# 完整流程：登录 → 创建 Token → 清理旧 Token
cd scripts && .venv/bin/python elearning_login.py --cleanup-old-tokens

# 调试模式（详细 HTTP 日志 + 保存调试产物）
cd scripts && .venv/bin/python elearning_login.py --debug --cleanup-old-tokens

# Dry-run：只测试到公钥获取为止（不执行登录）
cd scripts && .venv/bin/python elearning_login.py --dry-run --debug
```

成功后，脚本将 `NEW_TOKEN=<token值>` 输出到标准输出。

### 4. 与 Token 懒加载集成

对于调用 Canvas API 的 Agent，实现懒刷新（lazy-refresh）模式：

1. 从文件中读取已保存的 Token
2. 通过 `GET /api/v1/users/self` 校验 Token —— 仅检查 HTTP 状态码（不读取响应体）
3. 返回 200 → 使用该 Token
4. 返回 401 → 运行刷新脚本，捕获 `NEW_TOKEN=`，保存到文件，重试
5. 刷新也失败 → 提醒用户（密码已更改、触发验证码等）

**关键规则：**
- 每次会话只校验一次，不要每次 API 调用都校验
- 仅在收到明确的 401 响应时重新校验
- 不要记录或暴露原始 Token 值
- 刷新过程约需 2-3 秒，静默运行

## 安全说明

- `.env` 包含凭据 —— **切勿提交到 git**（`.env` 默认已加入 .gitignore）
- `debug_output/` 可能包含会话 Cookie 和加密载荷 —— **分享前请清除敏感信息**
- 脚本使用 PKCS1v1_5 RSA 加密传输密码（与 IDP 的 JS 前端保持一致）
- Token 创建时带有 purpose 标签，便于生命周期管理
- 同 purpose 的旧 Token 可自动删除，避免 Token 堆积
- 清理逻辑用 BeautifulSoup 按行解析 `/profile/settings`（`tr.access_token`），逐行取自己的 `delete_key_link[rel]`。**不要用 `<tr>...</tr>` 正则** —— 行内含嵌套 `<table class="subtable">`，非贪婪正则会截断，导致永远找不到删除链接。
- 删除链接 `rel` 里的 id 段可能是**不透明串**（如 `tokens/QfGJ2`），不等于 `show_token_link[rel]` 里的数字 id —— 保留「当前 token」要用数字 id 比对，删除则用 delete 链接的 `rel`
- `scripts/diag_settings_tokens.py` 是**只读**诊断：登录后抓 settings 页面、报告解析命中数，不创建也不删除任何东西

## 已知限制

| 限制 | 影响 | 缓解措施 |
|---|---|---|
| 验证码/限流 | 脚本无法解决人机验证 | 提醒用户，需手动干预 |
| MFA/2FA | 需要 `requests` 不支持的交互式流程 | 不支持，提醒用户 |
| IDP 接口变更 | JSON 字段名或 HTML 结构可能变化 | 调试输出（`--debug`）会捕获原始响应以供诊断 |
| 公钥格式变更 | 脚本支持 PEM、Base64-DER、modulus+exponent | 如出现新格式，请扩展 `parse_public_key_payload()` |

## 故障排查

使用 `--debug` 将调试产物保存至 `debug_output/`：

| 现象 | 检查项 |
|---|---|
| `未能从入口响应中解析到 lck` | `debug_output/entry_response.html` —— 查找 `context_CAS_...` |
| `queryAuthMethods 未找到 userAndPwd` | `debug_output/query_auth_methods.json` —— 检查 `moduleCode` 字段 |
| `未从 authExecute 提取到 loginToken` | `debug_output/auth_execute.json` —— 检查 `code`/`message` |
| `未拿到关键会话 Cookie` | 检查 `auth_execute.json` 是否有报错，`authn_engine_response.html` 是否有验证码 |
| Token API 返回 401/422 | `debug_output/cookies.txt` 中查找 `_csrf_token` / `_normandy_session` |
| 清理失败 | `debug_output/cleanup_summary.json` 中查找 `failed` 条目 |
| `清理模式：未找到可删除旧 token` 但 settings 页面确实有 token | DOM 结构漂移。跑 `scripts/diag_settings_tokens.py` 只读抓页面 → `debug_output/settings_page.html`，再核对 `td.purpose` / `a.delete_key_link`。解析必须用 DOM（bs4），**不要用 `<tr>...</tr>` 正则** |

## 适配其他高校

本 IDP 流程基于中国许多高校通用的 CAS/SAML 模式。适配步骤：

1. **修改 `.env` 中的 URL**：`ELEARNING_ENTRY_URL`、`ELEARNING_IDP_BASE_URL`、`ELEARNING_ENTITY_ID`
2. **先用 `--dry-run` 测试**，验证 `lck`/`authChainCode` 是否能正常提取
3. **如 IDP 使用不同认证方式**：修改 `auth_session.py` 中的 `pick_auth_chain_code()`
4. **如密码加密方式不同**：修改 `encrypt_password_rsa()` 和 `parse_public_key_payload()`

已测试：复旦大学（id.fudan.edu.cn → elearning.fudan.edu.cn）。
