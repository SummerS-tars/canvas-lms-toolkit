#!/usr/bin/env python3
"""Canvas 课程资料同步 (course materials sync).

Fetch course files + assignments from Fudan Canvas LMS and write them into a
local course library.

The course library root defaults to `~/CanvasCourses` and can be overridden with
`--lib <dir>` or the `CANVAS_LIB` environment variable.

Usage:
    python3 sync_course_materials.py                  # sync everything
    python3 sync_course_materials.py --lib ~/MyCourses
    python3 sync_course_materials.py --course 114614  # one course only
    python3 sync_course_materials.py --dry-run        # show plan, download nothing
    python3 sync_course_materials.py --overwrite-assignments   # rewrite 原文档.md

配置：`COURSES` / `ASSIGN_DEST` 是例子用的某学期硬编码，换成你自己的课程即可。

Token: read from ~/.config/canvas-lms-token. On 401/404 run the sibling
       canvas-lms-idp-auto-refresh skill's elearning_login.py --cleanup-old-tokens
       and save the printed NEW_TOKEN back to that file.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

BASE_URL = 'https://elearning.fudan.edu.cn'
TOKEN_FILE = Path.home() / '.config' / 'canvas-lms-token'
# Course library root: ~/CanvasCourses by default, overridable via --lib / CANVAS_LIB
LIB = Path(os.environ.get('CANVAS_LIB') or (Path.home() / 'CanvasCourses'))
CST = timezone(timedelta(hours=8))

# Sibling skill that refreshes the token when Canvas returns 401/404.
REFRESH_SCRIPT = (Path(__file__).resolve().parents[2]
                  / 'canvas-lms-idp-auto-refresh' / 'scripts' / 'elearning_login.py')

# cid -> (display name, course folder, per-file destination overrides)
# 下面是某学期的实际配置，学期变化时自行替换。
COURSES = {
    '114614': ('CS30016.01 算法设计与分析', '1_算法设计与分析', {}),
    '114669': ('CS30055.01 云计算与虚拟化技术', '2_云计算与虚拟化技术', {}),
    '114531': ('CS40026.01 信息物理融合系统', '3_信息物理融合系统', {
        'LeeSeshia_DigitalV2_3.pdf': '2_课程资料/书',
        '实验资料下载链接.txt': '4_Lab',
    }),
    '115347': ('GECC10032.02 经济与社会', '4_经济与社会', {
        '课程微信群二维码.png': '1_课程信息',
    }),
}
DEFAULT_DEST = '3_课件'

# assignment id -> (destination dir relative to course folder, output file name)
# Files that already exist are kept unless --overwrite-assignments is passed.
ASSIGN_DEST = {
    '134994': ('5_Project/大作业1', '大作业1-原文档.md'),
    '136043': ('5_Project/大作业2', '大作业2-原文档.md'),
    '136637': ('4_Lab/实验1', '实验1-原文档.md'),
}

BQ_START, BQ_END = '\x01', '\x02'


# ────────────────────────── Canvas API ──────────────────────────

def api(path):
    token = TOKEN_FILE.read_text().strip()
    req = urllib.request.Request(
        f'{BASE_URL}/api/v1{path}',
        headers={'Authorization': f'Bearer {token}', 'User-Agent': 'openclaw-canvas-sync'},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code in (401, 404):
            sys.exit(f'❌ Canvas API {e.code} on {path} — token 可能失效。请运行\n'
                     f'   .venv/bin/python {REFRESH_SCRIPT} --cleanup-old-tokens\n'
                     f'   并把输出的 NEW_TOKEN 写入 {TOKEN_FILE}')
        raise


def download(url, dest):
    req = urllib.request.Request(url, headers={'User-Agent': 'curl/8'})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    dest.write_bytes(data)
    return len(data)


# ────────────────────────── HTML → Markdown ──────────────────────────

class Html2Md(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.lists, self.counters = [], [], []
        self.li_depth, self.href = 0, None

    def _e(self, s):
        self.out.append(s)

    def handle_starttag(self, tag, attrs):
        t, a = tag.lower(), dict(attrs)
        if t == 'p':
            if self.li_depth == 0:
                self._e('\n\n')
        elif t == 'br':
            self._e('\n')
        elif t == 'hr':
            self._e('\n\n---\n\n')
        elif t in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._e('\n\n' + '#' * int(t[1]) + ' ')
        elif t in ('strong', 'b'):
            self._e('**')
        elif t in ('em', 'i'):
            self._e('*')
        elif t == 'code':
            self._e('`')
        elif t == 'blockquote':
            self._e('\n\n' + BQ_START)
        elif t in ('ul', 'ol'):
            self._e('\n\n')
            self.lists.append(t)
            self.counters.append(0)
        elif t == 'li':
            self.li_depth += 1
            self._e('\n' + '  ' * max(0, len(self.lists) - 1))
            if self.lists and self.lists[-1] == 'ol':
                self.counters[-1] += 1
                self._e(f'{self.counters[-1]}. ')
            else:
                self._e('- ')
        elif t == 'tr':
            self._e('\n| ')
        elif t == 'a':
            self.href = a.get('href')
            self._e('[')
        elif t == 'img':
            self._e('![]')

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in ('p', 'div'):
            if self.li_depth == 0:
                self._e('\n\n')
        elif t in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._e('\n\n')
        elif t in ('strong', 'b'):
            self._e('**')
        elif t in ('em', 'i'):
            self._e('*')
        elif t == 'code':
            self._e('`')
        elif t == 'blockquote':
            self._e(BQ_END + '\n\n')
        elif t in ('ul', 'ol'):
            self.lists and self.lists.pop()
            self.counters and self.counters.pop()
            self._e('\n\n')
        elif t == 'li':
            self.li_depth = max(0, self.li_depth - 1)
            self._e('\n')
        elif t == 'a':
            self._e(f']({self.href})' if self.href and not self.href.startswith('#') else ']')
            self.href = None

    def handle_data(self, data):
        self._e(data.replace('\n', ' '))


def html_to_md(h):
    p = Html2Md()
    p.feed(h or '')
    out, depth = [], 0
    for line in ''.join(p.out).split('\n'):
        while line.startswith(BQ_START):
            depth += 1
            line = line[1:]
        end = BQ_END in line
        line = line.replace(BQ_END, '').rstrip()
        out.append(('> ' * depth + line) if line.strip() else '')
        if end:
            depth = max(0, depth - 1)
    s = re.sub(r'^\s*- +', '- ', '\n'.join(out), flags=re.M)
    s = re.sub(r'[ \t]+\n', '\n', s)
    return re.sub(r'\n{3,}', '\n\n', s).strip()


# ────────────────────────── helpers ──────────────────────────

def dt(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00')).astimezone(CST) if s else None


def human(n):
    n = n or 0
    for u in ('B', 'KB', 'MB'):
        if n < 1024:
            return f'{n:.1f} {u}'
        n /= 1024
    return f'{n:.1f} GB'


def write_if_changed(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding='utf-8') == text:
        print(f'  = {path.relative_to(LIB)} (unchanged)')
        return False
    path.write_text(text, encoding='utf-8')
    print(f'  ✎ {path.relative_to(LIB)}')
    return True


def course_info_md(cid, name, assignments, files, synced_at):
    uniq, seen = [], set()
    for f in files:
        n = f.get('display_name') or ''
        if n not in seen:
            seen.add(n)
            uniq.append(f)
    L = [f'# {name}', '',
         f'- Canvas 课程 ID：`{cid}`',
         f'- 课程页：{BASE_URL}/courses/{cid}',
         f'- 同步时间：{synced_at}', '',
         f'## 作业（{len(assignments)}）']
    if not assignments:
        L.append('- （暂无）')
    for a in assignments:
        due = dt(a.get('due_at'))
        L.append(f"- **{a.get('name')}** — 截止 `{due.strftime('%Y-%m-%d %H:%M (GMT+8)') if due else '无截止时间'}`，"
                 f"{a.get('points_possible')} 分")
        for ln in html_to_md(a.get('description')).split('\n'):
            if ln.strip():
                L.append(f'  > {ln}')
        L.append('')
    L += ['## 模块（0）', '- （暂无）', '', f'## Canvas 文件（{len(uniq)}）']
    for f in uniq:
        L.append(f"- {f.get('display_name')}（{human(f.get('size'))}）")
    L.append('')
    return '\n'.join(L)


def assignment_md(a, cid, course_name):
    due, unlock, lock = dt(a.get('due_at')), dt(a.get('unlock_at')), dt(a.get('lock_at'))
    exts = ', '.join(a.get('allowed_extensions') or []) or '—'
    subs = ', '.join(a.get('submission_types') or []) or '—'
    L = [f"# {a.get('name')}", '',
         '| 项 | 内容 |', '|---|---|',
         f'| 课程 | {course_name}（Canvas 课程 ID `{cid}`） |',
         f"| 作业 ID | {a.get('id')} |",
         f"| 截止时间 | **{due.strftime('%Y-%m-%d %H:%M') if due else '—'}**"
         f"（北京时间；Canvas 记为 {a.get('due_at')}） |"]
    if unlock:
        L.append(f"| 开放时间 | {unlock.strftime('%Y-%m-%d %H:%M')} |")
    if lock:
        L.append(f"| 锁定时间 | {lock.strftime('%Y-%m-%d %H:%M')} |")
    L += [f"| 分值 | {a.get('points_possible')} 分 |",
          f'| 提交方式 | Canvas 在线提交（`{subs}`，允许扩展名 `{exts}`） |',
          f"| 来源 | {a.get('html_url')} |", '', '---', '', html_to_md(a.get('description')), '']
    return '\n'.join(L)


# ────────────────────────── main ──────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--course', action='append', help='only sync this course id (repeatable)')
    ap.add_argument('--lib', help='course library root (default: ~/CanvasCourses or $CANVAS_LIB)')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--overwrite-assignments', action='store_true',
                    help='rewrite existing <作业名>-原文档.md files')
    args = ap.parse_args()

    if args.lib:
        global LIB
        LIB = Path(args.lib).expanduser()

    cids = args.course or list(COURSES)
    synced_at = datetime.now(CST).strftime('%Y-%m-%d %H:%M')
    stats = {'new': 0, 'skip': 0, 'doc': 0}

    for cid in cids:
        name, folder, overrides = COURSES[cid]
        print(f'\n== {cid} {name}')
        files = api(f'/courses/{cid}/files?per_page=100')
        assignments = api(f'/courses/{cid}/assignments?per_page=100')
        course_root = LIB / folder

        seen = set()
        for f in files:
            fname = f.get('display_name') or ''
            if fname in seen:
                continue
            seen.add(fname)
            dest = course_root / overrides.get(fname, DEFAULT_DEST) / fname
            if dest.exists() and dest.stat().st_size == f.get('size'):
                stats['skip'] += 1
                continue
            if args.dry_run:
                print(f'  + would download {dest.relative_to(LIB)} ({human(f.get("size"))})')
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            n = download(f['url'], dest)
            stats['new'] += 1
            print(f'  ↓ {dest.relative_to(LIB)} ({human(n)})')
            time.sleep(0.3)

        if not args.dry_run:
            if write_if_changed(course_root / '1_课程信息' / 'Canvas课程信息.md',
                                course_info_md(cid, name, assignments, files, synced_at)):
                stats['doc'] += 1
            for a in assignments:
                spec = ASSIGN_DEST.get(str(a.get('id')))
                if not spec:
                    continue
                dest_dir, fname = spec
                out = course_root / dest_dir / fname
                if out.exists() and not args.overwrite_assignments:
                    continue
                if write_if_changed(out, assignment_md(a, cid, name)):
                    stats['doc'] += 1

        unknown = [a.get('name') for a in assignments if str(a.get('id')) not in ASSIGN_DEST]
        if unknown:
            print('  ⚠ 未配置落点的作业：' + '; '.join(unknown))

    print(f"\n完成：新增 {stats['new']} 个文件，跳过 {stats['skip']} 个已存在，"
          f"更新 {stats['doc']} 个说明文档。")


if __name__ == '__main__':
    main()
