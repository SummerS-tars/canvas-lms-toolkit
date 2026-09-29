# Canvas LMS Toolkit

Automation toolkit for Fudan University's eLearning platform (Canvas LMS) — two companion
[OpenClaw Skills](https://clawhub.com) covering the full **"get a token → use the token"** loop.

- **Auth**: works around SSO session expiry to rotate Canvas API tokens automatically
- **Use**: call the Canvas REST API to read assignments, download course files, submit work,
  and sync a whole semester's course materials in one command

[中文文档](README.md)

---

## The Two Skills

| Skill | Purpose | Triggers on | Dependencies |
|---|---|---|---|
| [`canvas-lms-idp-auto-refresh`](skills/canvas-lms-idp-auto-refresh/) | **Write**: replay institutional IDP (CAS/SAML) login, RSA-encrypt the password, create/purge API tokens | token expired, 401/404, "自动刷新 token", "elearning login" | needs a venv (`requests` / `beautifulsoup4` / `pycryptodome` / `python-dotenv`) |
| [`canvas-lms`](skills/canvas-lms/) | **Read**: Canvas API recipes + course material sync script | "查作业", "下载课件", "课程平台", "查截止日期" | **zero third-party deps** (stdlib only) |

The dependency is one-way: `canvas-lms` calls the refresh script in `canvas-lms-idp-auto-refresh`
when the token dies; the latter knows nothing about the former. Either can be used alone.

## Repository Layout

```
canvas-lms-toolkit/
├── README.md / README.en.md
├── LICENSE                       # MIT
├── docs/
│   └── project-background.md     # Fudan eLearning background & use cases (Chinese)
└── skills/
    ├── canvas-lms/
    │   ├── SKILL.md
    │   └── scripts/sync_course_materials.py
    └── canvas-lms-idp-auto-refresh/
        ├── SKILL.md
        ├── references/idp-adaptation.md   # step-by-step guide for other institutions
        └── scripts/
            ├── elearning_login.py         # entry point
            ├── auth_session.py            # IDP login chain
            ├── token_ops.py               # token create / cleanup
            ├── diag_settings_tokens.py    # read-only diagnostic
            ├── requirements.txt
            └── .env.example
```

## Quick Start

### 1. Install into OpenClaw

Drop the two directories under `skills/` into your skills directory
(e.g. `~/.openclaw/workspace/skills/`) and add them to the skills allowlist —
otherwise the model never sees them. `cp -r skills/* <your-skills-dir>/` works too.

### 2. Configure credentials (only for `canvas-lms-idp-auto-refresh`)

```bash
cd skills/canvas-lms-idp-auto-refresh/scripts
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env        # fill in ELEARNING_USERNAME / ELEARNING_PASSWORD
chmod 600 .env
```

### 3. Get a token

```bash
# Dry-run first: only fetches the public key, no login
.venv/bin/python elearning_login.py --dry-run --debug

# Full flow: login → create token → cleanup old tokens with the same purpose
.venv/bin/python elearning_login.py --cleanup-old-tokens
```

On success `NEW_TOKEN=<value>` is printed to stdout — write it to `~/.config/canvas-lms-token`.
From then on the lazy refresh in `canvas-lms`'s SKILL.md handles expiry.

### 4. Sync course materials (optional)

```bash
cd ../../canvas-lms/scripts
python3 sync_course_materials.py --dry-run     # preview the plan
python3 sync_course_materials.py               # idempotent sync
```

The course library root defaults to `~/CanvasCourses`; override with `--lib` or `$CANVAS_LIB`.
`COURSES` / `ASSIGN_DEST` are hardcoded per semester — update them each term.

## Security

- `.env` holds credentials — **never commit it** (already gitignored)
- `debug_output/` contains **session cookies and a plaintext token** (`cookies.txt` / `create_token.json`) — gitignored; sanitize before sharing
- The password is RSA-encrypted (PKCS1v1_5) with the key served by the IDP, matching the frontend JS
- Tokens carry a purpose label; cleanup matches on purpose only, so manually created tokens survive
- If the new token's id can't be determined, the script **refuses to clean up** and exits (avoids deleting every token with that purpose)

## Known Limitations

| Limitation | Impact |
|---|---|
| CAPTCHA / rate limiting | Human verification can't be solved; manual intervention needed |
| MFA / 2FA | Unsupported (`requests` can't drive an interactive flow) |
| SAML 2.0 (non-CAS) | Not directly supported |
| IDP interface / DOM changes | May break; diagnose with `--debug` and `diag_settings_tokens.py` |

## Documentation

- [Project background & use cases](docs/project-background.md) — Fudan eLearning architecture, typical scenarios, design rationale (Chinese)
- [IDP adaptation guide](skills/canvas-lms-idp-auto-refresh/references/idp-adaptation.md) — step-by-step for other institutions (Chinese)

Verified against **Fudan University** (`id.fudan.edu.cn` → `elearning.fudan.edu.cn`).

## License

MIT
