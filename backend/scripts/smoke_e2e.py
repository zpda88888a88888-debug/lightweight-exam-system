#!/usr/bin/env python3
"""端到端冒烟脚本：对「真实运行中的服务」跑一遍管理员与考生主干流程。

它对应用测试方案第 10 阶段 8 的 E2E 主干流程（管理员建考试 → 导入名单 →
生成邀请码 → 发布 → 考生登录答题 → 交卷 → 导出成绩），
但用 HTTP 直连代替浏览器，因此不依赖前端即可验证后端真实部署可用。

用法：
    # 1) 启动服务
    EXAM_DB_PATH=/tmp/smoke.db ADMIN_PASSWORD=changeme \
        .venv/bin/uvicorn app.main:app --port 8123
    # 2) 另开终端执行
    .venv/bin/python scripts/smoke_e2e.py --base-url http://127.0.0.1:8123
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

PASSED = 0


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    json_body: dict | None = None,
    raw_body: bytes | None = None,
    content_type: str = "application/json",
) -> tuple[int, object]:
    url = f"{base_url.rstrip('/')}{path}"
    data = raw_body
    headers = {"Content-Type": content_type}
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            text = body.decode("utf-8")
            if "application/json" in resp.headers.get("Content-Type", ""):
                return resp.status, json.loads(text)
            return resp.status, text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(text)
        except json.JSONDecodeError:
            return exc.code, text


def check(label: str, condition: bool, extra: object = "") -> None:
    global PASSED
    if condition:
        PASSED += 1
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label}  {extra}")
        raise SystemExit(f"冒烟失败：{label}")


def main() -> int:
    parser = argparse.ArgumentParser(description="后端端到端冒烟")
    parser.add_argument("--base-url", default="http://127.0.0.1:8123")
    parser.add_argument("--admin-user", default="admin")
    parser.add_argument("--admin-password", default="changeme")
    args = parser.parse_args()

    base = args.base_url
    print(f"目标服务：{base}")

    print("\n[1] 健康检查")
    status, body = request(base, "GET", "/api/health")
    check("GET /api/health → 200", status == 200, body)
    check("返回 ok", isinstance(body, dict) and body.get("ok") is True, body)

    print("\n[2] 管理员登录")
    status, body = request(
        base,
        "POST",
        "/api/admin/login",
        json_body={"username": args.admin_user, "password": args.admin_password},
    )
    check("登录成功", status == 200, body)
    admin_token = body["token"]

    status, body = request(
        base, "POST", "/api/admin/login", json_body={"username": "admin", "password": "wrong"}
    )
    check("错误密码被拒绝", status == 401, status)

    print("\n[3] 题库：新增题目")
    question_ids = []
    for i in range(3):
        status, body = request(
            base,
            "POST",
            "/api/admin/questions",
            token=admin_token,
            json_body={
                "type": "single",
                "stem": f"冒烟题 {i + 1}",
                "options": [
                    {"key": "A", "text": "选项A"},
                    {"key": "B", "text": "选项B"},
                ],
                "answer": ["A"],
                "score": 10,
                "tags": ["冒烟"],
                "analysis": "答案 A",
            },
        )
        check(f"新增题目 {i + 1}", status == 201, body)
        question_ids.append(body["id"])

    print("\n[4] 创建考试草稿")
    start = now_utc() - timedelta(hours=1)
    end = now_utc() + timedelta(hours=1)
    status, exam = request(
        base,
        "POST",
        "/api/admin/exams",
        token=admin_token,
        json_body={
            "title": "冒烟测试考试",
            "recruitment_no": f"SMOKE-{int(now_utc().timestamp())}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "pass_ratio": 50,
            "settings": {"rules": [{"tag": "冒烟", "count": 3}]},
        },
    )
    check("创建草稿 → 201", status == 201, exam)
    exam_id = exam["id"]
    check("初始状态为 draft", exam["status"] == "draft", exam)

    print("\n[5] 导入名单（CSV）")
    csv_text = (
        "手机号,姓名,身份证号\n"
        "13800000001,张三,110101199001010011\n"
        "13800000002,李四,110101199001010022\n"
    )
    status, body = request(
        base,
        "POST",
        f"/api/admin/exams/{exam_id}/candidates/import",
        token=admin_token,
        raw_body=csv_text.encode("utf-8"),
        content_type="text/csv; charset=utf-8",
    )
    check("导入成功", status == 200, body)
    # 身份证号全局唯一 + upsert 口径：若库里已存在这两名考生（例如先跑过 seed_demo），
    # 就会走更新分支而不是新建，两种都算成功。
    check(
        "名单包含 2 名考生（新增或更新）",
        body["users_created"] + body["users_updated"] == 2,
        body,
    )

    print("\n[6] 生成邀请码")
    status, body = request(
        base,
        "POST",
        f"/api/admin/exams/{exam_id}/candidates/generate",
        token=admin_token,
        json_body={"confirm": True},
    )
    check("生成成功", status == 200, body)
    status, candidates = request(
        base, "GET", f"/api/admin/exams/{exam_id}/candidates", token=admin_token
    )
    codes = {c["name"]: c["invite_code"] for c in candidates}
    check("每人 6 位数字码", all(len(c) == 6 and c.isdigit() for c in codes.values()), codes)

    print("\n[7] 发布考试（生成快照并冻结）")
    status, body = request(base, "POST", f"/api/admin/exams/{exam_id}/publish", token=admin_token)
    check("发布成功", status == 200, body)
    check("快照 3 题", body["question_count"] == 3, body)

    status, body = request(
        base,
        "PUT",
        f"/api/admin/exams/{exam_id}",
        token=admin_token,
        json_body={
            "title": "试图修改",
            "recruitment_no": exam["recruitment_no"],
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "pass_ratio": 60,
            "settings": {"rules": [{"tag": "冒烟", "count": 3}]},
        },
    )
    check("发布后修改被拒绝（冻结）", status == 409, status)

    print("\n[8] 考生登录 → 答题 → 交卷")
    status, body = request(
        base, "POST", "/api/auth/join", json_body={"phone": "13800000001", "invite_code": codes["张三"]}
    )
    check("考生登录成功", status == 200, body)
    token = body["token"]

    status, body = request(base, "POST", f"/api/exams/{exam_id}/attempts", token=token)
    check("创建 attempt", status == 200, body)
    attempt_id = body["attempt_id"]

    status, paper = request(base, "GET", f"/api/exams/{exam_id}/paper", token=token)
    check("拉取试卷", status == 200, paper)
    check("试卷 3 题", len(paper["questions"]) == 3, paper)
    serialized = json.dumps(paper, ensure_ascii=False)
    check("试卷不含答案/解析", "answer" not in serialized and "analysis" not in serialized)

    answers = [{"question_id": q["id"], "answer": ["A"]} for q in paper["questions"]]
    status, result = request(
        base,
        "POST",
        f"/api/attempts/{attempt_id}/submit",
        token=token,
        json_body={"answers": answers, "switch_count": 1, "switch_log": ["2026-09-19T10:01:23"]},
    )
    check("交卷成功", status == 200, result)
    check("满分 30.0", result["score"] == 30.0, result)

    status, again = request(
        base,
        "POST",
        f"/api/attempts/{attempt_id}/submit",
        token=token,
        json_body={"answers": [], "switch_count": 9, "switch_log": []},
    )
    check("重复交卷幂等（返回首次结果）", again["score"] == 30.0, again)

    status, body = request(
        base, "POST", "/api/auth/join", json_body={"phone": "13800000001", "invite_code": codes["张三"]}
    )
    check("已交卷再次登录被拒（409）", status == 409, status)

    print("\n[9] 统计与成绩导出")
    status, stats = request(base, "GET", f"/api/admin/exams/{exam_id}/stats", token=admin_token)
    check("统计接口可用", status == 200, stats)
    check("有 attempt 人数 = 1", stats["attempt_count"] == 1, stats)
    check("缺考人数 = 1", stats["absent_count"] == 1, stats)
    check("平均分 30.0", stats["average_score"] == 30.0, stats)

    status, csv_text = request(
        base, "GET", f"/api/admin/exams/{exam_id}/results/export", token=admin_token
    )
    check("导出 CSV 成功", status == 200, status)
    rows = list(csv.reader(io.StringIO(csv_text)))
    check("列头正确", rows[0] == [
        "选聘编号", "考试名称", "手机号", "姓名", "身份证号", "邀请码",
        "开始时间", "交卷时间", "得分", "是否及格", "切屏次数", "切屏时间点", "状态",
    ], rows[0])
    check("导出含 2 人", len(rows) == 3, rows)
    statuses = {r[3]: r[12] for r in rows[1:]}
    check("张三为正常提交", statuses["张三"] == "正常提交", statuses)
    check("李四为缺考", statuses["李四"] == "缺考", statuses)

    print(f"\n冒烟通过：{PASSED} 项检查全部成功")
    return 0


if __name__ == "__main__":
    sys.exit(main())
