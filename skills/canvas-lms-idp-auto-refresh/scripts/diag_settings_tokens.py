#!/usr/bin/env python3
"""只读诊断：登录后抓取 /profile/settings，保存到 debug_output/，并跑 token 解析。

不做任何写操作（不创建 / 不删除 token）。
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

from auth_session import AppConfig, DEFAULT_ENTITY_ID, DEFAULT_ENTRY_URL, DEFAULT_IDP_BASE, DEFAULT_SETTINGS_REFERER, DEFAULT_TIMEOUT, DEFAULT_TOKEN_API, ElearningAuthClient
from elearning_login import load_config_from_env
from token_ops import extract_existing_tokens_from_settings, extract_token_form_info

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger("diag")

OUT = Path("debug_output")


def main() -> int:
    config = load_config_from_env(allow_missing_credentials=False)
    auth = ElearningAuthClient(config)
    auth.login_and_prepare_session(dry_run=False)

    res = auth.session.get(config.settings_referer, timeout=config.timeout_seconds)
    LOGGER.info("GET %s -> HTTP %s, %s bytes", config.settings_referer, res.status_code, len(res.text))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "settings_page.html").write_text(res.text, encoding="utf-8")

    text = res.text
    print("has 'access_token' class:", bool(re.search(r'class="[^"]*access_token', text)))
    print("has 'purpose' td:", bool(re.search(r'<td[^>]*class="[^"]*purpose', text)))
    print("has delete_key_link:", "delete_key_link" in text)
    print("has show_token_link:", "show_token_link" in text)
    print("occurrences /api/v1/users/self/tokens/:",
          len(re.findall(r"/api/v1/users/self/tokens/", text)))
    print("<tr count:", len(re.findall(r"<tr", text)))
    print("token form info:", bool(extract_token_form_info(text)))

    tokens = extract_existing_tokens_from_settings(text)
    print("parsed tokens:", len(tokens))
    for t in tokens[:5]:
        print("  ", t.purpose, t.token_id, t.delete_url[:80])

    # 打印几个 <tr> 开头片段，帮助定位 DOM 结构
    rows = re.findall(r"<tr[\s\S]{0,400}?</tr>", text)
    with_tokenish = [r for r in rows if "token" in r.lower()]
    (OUT / "diag_rows_sample.txt").write_text(
        "\n\n=====\n\n".join(with_tokenish[:6]), encoding="utf-8"
    )
    print("tokenish <tr> count:", len(with_tokenish), "(sample -> debug_output/diag_rows_sample.txt)")

    (OUT / "diag_result.json").write_text(
        json.dumps({"parsed": len(tokens), "tokenish_rows": len(with_tokenish)}, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
