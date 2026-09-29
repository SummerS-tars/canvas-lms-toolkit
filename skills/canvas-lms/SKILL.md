---
name: canvas-lms
description: Interact with Fudan University's Canvas LMS (elearning.fudan.edu.cn) via API. Use when the user asks to check assignments, download course files, view announcements, browse course modules, or any task involving the eLearning platform. Triggers on "elearning", "canvas", "课程平台", "查作业", "下载课件", "查课程", "查截止日期".
---

# Canvas LMS API

Fudan eLearning platform powered by Canvas LMS.

> 配套 skill：[`canvas-lms-idp-auto-refresh`](../canvas-lms-idp-auto-refresh/) —— 负责 token 的获取与轮换。
> 本 skill 只负责**使用** token 调 Canvas API。

## Setup

Base URL: `https://elearning.fudan.edu.cn`

Token 文件：`~/.config/canvas-lms-token`（单一 token，无 backup）。

### Token 懒加载刷新机制

1. 读取 token → 调用 `/api/v1/users/self` 验证（**只看 HTTP status，不读 body**）
2. `200` → 直接用该 token
3. `401` **或 `404`** → 自动刷新（见下方，注意 404 也算失效）
4. 刷新也失败 → 告知用户需手动检查（密码变更、验证码风控等）

**刷新方式**（sibling skill 的脚本，相对本文件上级目录）：

```bash
cd ../canvas-lms-idp-auto-refresh/scripts
.venv/bin/python elearning_login.py --cleanup-old-tokens 2>/dev/null
```

脚本输出 `NEW_TOKEN=xxx`，提取后写入 `~/.config/canvas-lms-token`，再重试原请求。

**关键点：**

- ⚠️ **未认证时 Canvas 返回 `404` 而不是 `401`**（body: `The specified resource does not exist.`）—— 失效判断不能只认 401
- 遇到 401/404 **先自查请求头有没有拼对**，再怀疑 token；token 没问题就别重登（会堆一堆无用 token）
- 每次 session 首次调用时验证一次即可，同一 session 内不重复验证
- 刷新约需 2-3 秒，静默完成；成功对用户透明，失败才通知
- 不要记录或回显 token 原文

所有请求带 header：

```
Authorization: Bearer <token>
```

## API Reference

### User

```bash
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/users/self"
```

### Courses

```bash
# All courses (default includes current enrollment)
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/courses?per_page=50"

# Single course with details
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/courses/$CID"
```

### Files (list & download)

```bash
# List files
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/courses/$CID/files?per_page=50"

# Download file (use file['url'] from listing, or construct):
curl -L -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/courses/$CID/files/$FID/download" -o "output.ext"
```

> ⚠️ API 返回的 `url` 是**预签名**的（自带 `?verifier=...`）—— 用它下载时**不要再带 `Authorization` 头**，
> 否则 S3 报 `400 InvalidArgument: Either the Signature query string parameter or the Authorization header should be specified, not both`。
>
> ⚠️ 返回的 `filename` 是 percent-encoded，本地命名请用 `display_name`。

### Assignments

```bash
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/courses/$CID/assignments?per_page=50"
```

Key fields: `name`, `due_at`, `workflow_state` (published/draft), `submission_types`, `description`.

### Modules

```bash
# List modules
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/courses/$CID/modules?per_page=50"

# List items in a module
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/courses/$CID/modules/$MID/items?per_page=50"
```

### Announcements

```bash
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/courses/$CID/announcements?per_page=20"
```

### Submissions

```bash
# Check own submission status
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/courses/$CID/assignments/$AID/submissions/self"

# List all submissions for a course
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/courses/$CID/students/submissions?per_page=50"
```

## Known Course IDs（示例，自行更新）

以下是某学期的实际课程，学期变化时需替换：

| Course ID | Course |
|---|---|
| 114614 | CS30016.01 算法设计与分析 |
| 114669 | CS30055.01 云计算与虚拟化技术 |
| 114531 | CS40026.01 信息物理融合系统 |
| 115347 | GECC10032.02 经济与社会 |

> 部分课程可能**不在 Canvas 上**（如操作系统H），不要因为查不到就判定为权限问题。

## Course Materials Sync（`scripts/sync_course_materials.py`）

一条命令完成「拉课件 + 生成课程信息 + 生成作业原文档」，幂等。

```bash
cd scripts
python3 sync_course_materials.py                   # 同步全部
python3 sync_course_materials.py --course 114614   # 只同步一门（可重复传）
python3 sync_course_materials.py --dry-run         # 只看计划，不下载
python3 sync_course_materials.py --lib ~/MyCourses # 指定课程库根目录
python3 sync_course_materials.py --overwrite-assignments  # 重写已存在的原文档
```

行为：

- 拉各课 `files` / `assignments` → 课件落到 `<课程库>/<课程目录>/3_课件`（有少量覆盖规则：教材 → `2_课程资料/书`、实验链接 → `4_Lab`、群二维码 → `1_课程信息`）
- 重写 `<课程库>/<课程目录>/1_课程信息/Canvas课程信息.md`（内容没变则跳过）
- 为 `ASSIGN_DEST` 里登记的作业生成 `<作业名>-原文档.md`；**已存在的不覆盖**，除非加 `--overwrite-assignments`
- 幂等：重复跑输出 `新增 0 … 跳过 N`
- 课程库根目录默认 `~/CanvasCourses`，可用 `--lib` 或 `$CANVAS_LIB` 覆盖
- 脚本内 `COURSES` / `ASSIGN_DEST` 是**按学期硬编码**的，新学期要改；未登记落点的作业会在末尾以 `⚠ 未配置落点的作业` 提示
- ⚠️ 脚本**只读 token，不自动重登**。401/404 时跑 sibling skill 的 `elearning_login.py` 写回 `NEW_TOKEN`

## Common Tasks

### Check upcoming deadlines across all courses

Query each course's assignments, filter `due_at` > now, sort by deadline.

### Download course files

Prefer `scripts/sync_course_materials.py`. 手工方式：list files via API → filter by type → download → organize.

### Submit assignments

Canvas 文件提交是三步流程（`upload URL` → 上传文件 → 创建 submission）：

1. `POST /api/v1/courses/:cid/assignments/:aid/submissions/self/files`（带 `name` / `size` / `content_type`）→ 拿 `upload_url` + `upload_params`
2. 把 `upload_params` + 文件 POST 到 `upload_url` —— **不要带 `Authorization` 头** → `303`，从 `Location` 取 `file_id`
3. `POST /api/v1/courses/:cid/assignments/:aid/submissions`，`submission[submission_type]=online_upload` + `submission[file_ids][]=<id>`

只在用户明确要求时执行。

## Caveats

- `announcements` endpoint 可能因课程权限返回空或报错
- 大文件先下到本地临时目录，再移动到目标位置
- 文件下载 URL 预签名，不可带 `Authorization`（见上）
- Rate limit: Canvas 通常每用户每分钟 1000 请求
