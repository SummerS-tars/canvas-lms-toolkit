# Canvas LMS Toolkit

复旦 eLearning（Canvas LMS）自动化工具集 —— 两个配套的 [OpenClaw Skill](https://clawhub.com)，
合起来覆盖 **「拿 token → 用 token」** 的完整闭环。

- **认证**：绕过 SSO 会话过期，全自动轮换 API Token
- **使用**：调 Canvas REST API 查作业 / 下课件 / 交作业，并一键同步整个学期的课程资料

[English](README.en.md)

---

## 两个 Skill

| Skill | 作用 | 触发场景 | 依赖 |
|---|---|---|---|
| [`canvas-lms-idp-auto-refresh`](skills/canvas-lms-idp-auto-refresh/) | **写**：模拟机构 IDP（CAS/SAML）登录，RSA 加密密码，创建/清理 API Token | token 过期、401/404、「自动刷新 token」、「elearning 登录」 | 需要 venv（`requests` / `beautifulsoup4` / `pycryptodome` / `python-dotenv`） |
| [`canvas-lms`](skills/canvas-lms/) | **读**：Canvas API 用法 + 课程资料同步脚本 | 「查作业」「下载课件」「课程平台」「查截止日期」 | **零第三方依赖**（纯标准库） |

两者是单向依赖：`canvas-lms` 在 token 失效时会调用 `canvas-lms-idp-auto-refresh` 的刷新脚本；
后者完全不知道前者的存在。所以你可以只用其中一个。

## 目录结构

```
canvas-lms-toolkit/
├── README.md / README.en.md
├── LICENSE                       # MIT
├── docs/
│   └── project-background.md     # 复旦 eLearning 平台背景与典型场景
└── skills/
    ├── canvas-lms/
    │   ├── SKILL.md
    │   └── scripts/sync_course_materials.py
    └── canvas-lms-idp-auto-refresh/
        ├── SKILL.md
        ├── references/idp-adaptation.md   # 适配其他高校的详细指南
        └── scripts/
            ├── elearning_login.py         # 主入口
            ├── auth_session.py            # IDP 登录链
            ├── token_ops.py               # Token 创建 / 清理
            ├── diag_settings_tokens.py    # 只读诊断
            ├── requirements.txt
            └── .env.example
```

## 快速开始

### 1. 安装到 OpenClaw

把 `skills/` 下的两个目录放进你的 skills 目录（例如 `~/.openclaw/workspace/skills/`），
然后在配置的 skills 白名单里加上它们，否则模型看不到。
也可以直接 `cp -r skills/* <你的 skills 目录>/`。

### 2. 配置凭据（仅 `canvas-lms-idp-auto-refresh` 需要）

```bash
cd skills/canvas-lms-idp-auto-refresh/scripts
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env        # 填 ELEARNING_USERNAME / ELEARNING_PASSWORD
chmod 600 .env
```

### 3. 拿一个 token

```bash
# 先 dry-run 验证链路（只取公钥，不登录）
.venv/bin/python elearning_login.py --dry-run --debug

# 正式：登录 → 创建 token → 清理同 purpose 旧 token
.venv/bin/python elearning_login.py --cleanup-old-tokens
```

成功时 stdout 输出 `NEW_TOKEN=<token值>`，把它写进 `~/.config/canvas-lms-token`。
之后的懒刷新由 agent 按 `canvas-lms` 的 SKILL.md 自动处理。

### 4. 同步课程资料（可选）

```bash
cd ../../canvas-lms/scripts
python3 sync_course_materials.py --dry-run     # 先看计划
python3 sync_course_materials.py               # 正式同步（幂等）
```

课程库根目录默认 `~/CanvasCourses`，可用 `--lib` 或 `$CANVAS_LIB` 覆盖。
`COURSES` / `ASSIGN_DEST` 是按学期硬编码的，换学期要改。

## 安全

- `.env` 含凭据 —— **切勿提交**（已在 `.gitignore` 中）
- `debug_output/` 会包含**会话 Cookie 和明文 Token**（`cookies.txt` / `create_token.json`）—— 已 gitignore，分享前也请自行清除
- 密码在传输前用 IDP 提供的 RSA 公钥加密（PKCS1v1_5），与前端 JS 行为一致
- Token 带 purpose 标签，清理只按 purpose 匹配，不会误删手动创建的 Token
- 没有新 token id 时脚本会**拒绝清理**并退出（避免删光所有同 purpose token）

## 已知限制

| 限制 | 影响 |
|---|---|
| 验证码 / 限流 | 无法处理人机验证，需人工介入 |
| MFA / 2FA | 不支持（`requests` 无法做交互式流程） |
| SAML 2.0（非 CAS） | 不直接支持 |
| IDP 接口 / DOM 变更 | 可能失效；用 `--debug` 和 `diag_settings_tokens.py` 诊断 |

## 文档

- [项目背景与应用场景](docs/project-background.md) —— 复旦 eLearning 平台架构、典型用法、技术选型
- [IDP 适配指南](skills/canvas-lms-idp-auto-refresh/references/idp-adaptation.md) —— 适配其他高校的逐步流程

已在**复旦大学**（`id.fudan.edu.cn` → `elearning.fudan.edu.cn`）验证。

## 许可证

MIT
