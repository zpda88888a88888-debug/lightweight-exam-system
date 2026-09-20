#!/usr/bin/env python3
"""演示数据播种：本地试用时立刻有题、有考试、有成绩可看。

只用 Python 标准库，通过公开 API 造数据（不直接写数据库），
因此也顺带验证了整条接口链路。

会创建：
    - 10 道题（单选/多选/判断，分属「安全生产」「法律法规」两个标签）
    - 1 场正在进行的考试（现在开考，8 小时后截止，及格比例 60%）
    - 8 名考生名单 + 全局唯一邀请码
    - 6 人已交卷（分数呈梯度，便于看统计图表），2 人缺考

用法：
    python3 backend/scripts/seed_demo.py \
        --base-url http://127.0.0.1:8000 \
        --admin-password admin123
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

# 演示考试的选聘编号前缀（实际编号带时间戳，保证每次播种都可运行）
DEMO_PREFIX = "DEMO-"

TAG_SAFETY = "安全生产"
TAG_LAW = "法律法规"

# (题干, 题型, 选项, 正确答案, 分值, 标签)
QUESTIONS: list[tuple[str, str, list[tuple[str, str]], list[str], float, str]] = [
    (
        "我国的安全生产方针是（　）。",
        "single",
        [("A", "安全第一、预防为主、综合治理"), ("B", "生产第一、安全第二"),
         ("C", "效益优先、安全兼顾"), ("D", "先生产、后安全")],
        ["A"], 10, TAG_SAFETY,
    ),
    (
        "从业人员发现直接危及人身安全的紧急情况时，有权（　）。",
        "single",
        [("A", "停止作业或者在采取可能的应急措施后撤离作业场所"), ("B", "继续作业直到完成任务"),
         ("C", "自行处理并隐瞒不报"), ("D", "等待班组长指令后再行动")],
        ["A"], 10, TAG_SAFETY,
    ),
    (
        "以下属于特种作业的有（　）。",
        "multi",
        [("A", "电工作业"), ("B", "焊接与热切割作业"),
         ("C", "高处作业"), ("D", "办公室文秘工作")],
        ["A", "B", "C"], 15, TAG_SAFETY,
    ),
    (
        "从业人员有权拒绝违章指挥和强令冒险作业。",
        "judge",
        [("对", "正确"), ("错", "错误")],
        ["对"], 5, TAG_SAFETY,
    ),
    (
        "灭火器压力表指针指在（　）区域时，表示压力正常。",
        "single",
        [("A", "绿色"), ("B", "红色"), ("C", "黄色"), ("D", "黑色")],
        ["A"], 10, TAG_SAFETY,
    ),
    (
        "《安全生产法》规定，生产经营单位的主要负责人对本单位的安全生产工作（　）负责。",
        "single",
        [("A", "全面"), ("B", "部分"), ("C", "连带"), ("D", "间接")],
        ["A"], 10, TAG_LAW,
    ),
    (
        "劳动合同应当以书面形式订立，并载明（　）。",
        "multi",
        [("A", "劳动报酬"), ("B", "工作内容和工作地点"),
         ("C", "劳动保护和劳动条件"), ("D", "员工的家庭隐私")],
        ["A", "B", "C"], 15, TAG_LAW,
    ),
    (
        "生产经营单位可以与从业人员订立协议，免除其对从业人员因生产安全事故伤亡依法应承担的责任。",
        "judge",
        [("对", "正确"), ("错", "错误")],
        ["错"], 5, TAG_LAW,
    ),
    (
        "生产安全事故发生后，事故现场有关人员应当立即报告（　）。",
        "single",
        [("A", "本单位负责人"), ("B", "新闻媒体"), ("C", "家属"), ("D", "同事")],
        ["A"], 10, TAG_LAW,
    ),
    (
        "因生产安全事故受到损害的从业人员，除依法享有工伤保险外，还可以向（　）提出赔偿要求。",
        "single",
        [("A", "本单位"), ("B", "保险公司"), ("C", "当地政府"), ("D", "工会组织")],
        ["A"], 10, TAG_LAW,
    ),
]

ROSTER: list[tuple[str, str, str]] = [
    ("13800000001", "张伟", "110101199001010011"),
    ("13800000002", "李娜", "110101199001010022"),
    ("13800000003", "王强", "110101199001010033"),
    ("13800000004", "刘洋", "110101199001010044"),
    ("13800000005", "陈静", "110101199001010055"),
    ("13800000006", "赵磊", "110101199001010066"),
    ("13800000007", "孙悦", "110101199001010077"),  # 缺考
    ("13800000008", "周涛", "110101199001010088"),  # 缺考
]

# 每人每题作答模式：correct 全对 / partial 多选漏选 / wrong 答错
# 顺序与 QUESTIONS 一致，长度不足时按 correct 处理
ANSWER_PLANS: dict[str, list[str]] = {
    "张伟": ["correct"] * 10,
    "李娜": ["correct"] * 7 + ["wrong"] * 3,
    "王强": ["correct"] * 5 + ["wrong"] + ["correct"] * 2 + ["wrong"] * 2,
    "刘洋": ["correct"] * 4 + ["partial", "wrong"] + ["correct"] * 2 + ["wrong"] * 2,
    "陈静": ["correct"] * 2 + ["wrong"] * 5 + ["partial"] * 3,
    "赵磊": ["correct"] + ["wrong"] * 9,
}


class ApiError(RuntimeError):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


def request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict | None = None,
    raw: bytes | None = None,
    content_type: str = "application/json",
) -> object:
    data = raw
    headers = {"Content-Type": content_type}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(f"{base_url.rstrip('/')}{path}", data=data, headers=headers,
                                method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else None
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        try:
            detail = json.loads(text).get("detail", text)
        except json.JSONDecodeError:
            detail = text
        raise ApiError(exc.code, str(detail)) from exc


def utc_naive(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def build_answer(question: dict, mode: str) -> list[str]:
    """按模式构造作答：correct 全对；partial 多选漏选；wrong 选错项。"""
    correct = [str(k) for k in question["answer"]]
    all_keys = [o["key"] for o in question["options"]]

    if mode == "correct":
        return correct

    if mode == "partial" and len(correct) > 1:
        return correct[: max(1, len(correct) - 1)]

    wrong_keys = [k for k in all_keys if k not in correct]
    if not wrong_keys:
        return correct  # 退化情形：没有错误项可选
    return [wrong_keys[0]]


def main() -> int:
    parser = argparse.ArgumentParser(description="播种演示数据")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-user", default="admin")
    parser.add_argument("--admin-password", default="admin123")
    args = parser.parse_args()

    base = args.base_url
    print(f"目标后端：{base}")

    # ---------------- 管理员登录 ----------------
    token = request(base, "POST", "/api/admin/login",
                    body={"username": args.admin_user, "password": args.admin_password})["token"]
    print("  ✓ 管理员登录")

    # ---------------- 题库 ----------------
    existing = request(base, "GET", "/api/admin/questions", token=token)
    by_stem = {q["stem"]: q for q in existing}

    created: dict[str, dict] = {}
    for stem, qtype, options, answer, score, tag in QUESTIONS:
        if stem in by_stem:
            created[stem] = by_stem[stem]
            continue
        payload = {
            "type": qtype,
            "stem": stem,
            "options": [{"key": k, "text": t} for k, t in options],
            "answer": answer,
            "score": score,
            "tags": [tag],
            "analysis": f"正确答案：{''.join(answer)}",
        }
        created[stem] = request(base, "POST", "/api/admin/questions", token=token, body=payload)
    print(f"  ✓ 题库就绪（{len(created)} 题，其中新增 {len(created) - len(by_stem)} 题）")

    # ---------------- 考试 ----------------
    # 复用「仍在进行中」的演示考试；若没有（首次运行，或旧的已过期），
    # 就用当前时间新建一场，避免隔天再跑时考生登不进去。
    now = datetime.now(timezone.utc)
    exams = request(base, "GET", "/api/admin/exams", token=token)
    running = [e for e in exams
               if e["recruitment_no"].startswith(DEMO_PREFIX) and e.get("external_status") == "running"]

    if running:
        demo = running[0]
        print(f"  ✓ 复用进行中的演示考试（{demo['recruitment_no']}）")
    else:
        recruitment_no = f"{DEMO_PREFIX}{now:%Y%m%d-%H%M%S}"
        demo = request(base, "POST", "/api/admin/exams", token=token, body={
            "title": "2026 年安全生产知识考试（演示）",
            "recruitment_no": recruitment_no,
            "start_at": utc_naive(now - timedelta(hours=1)),
            "end_at": utc_naive(now + timedelta(hours=8)),
            "pass_ratio": 60,
            "settings": {"rules": [
                {"tag": TAG_SAFETY, "count": 5},
                {"tag": TAG_LAW, "count": 5},
            ]},
        })
        print(f"  ✓ 已创建演示考试（{recruitment_no}，现在开考，8 小时后截止）")

    exam_id = demo["id"]

    # ---------------- 名单与邀请码 ----------------
    candidates = request(base, "GET", f"/api/admin/exams/{exam_id}/candidates", token=token)
    if not candidates:
        lines = ["手机号,姓名,身份证号"] + [",".join(r) for r in ROSTER]
        csv_text = "\n".join(lines) + "\n"
        request(base, "POST", f"/api/admin/exams/{exam_id}/candidates/import", token=token,
                raw=csv_text.encode("utf-8"), content_type="text/csv; charset=utf-8")
        request(base, "POST", f"/api/admin/exams/{exam_id}/candidates/generate", token=token,
                body={"confirm": True})
        candidates = request(base, "GET", f"/api/admin/exams/{exam_id}/candidates", token=token)
        print(f"  ✓ 已导入名单并生成邀请码（{len(candidates)} 人）")

    codes = {c["name"]: c["invite_code"] for c in candidates}

    # ---------------- 发布 ----------------
    if demo["status"] == "draft":
        result = request(base, "POST", f"/api/admin/exams/{exam_id}/publish", token=token)
        print(f"  ✓ 已发布（抽题 {result['question_count']} 道，总分 {result['total_score']}）")
    else:
        print("  ✓ 考试已处于发布状态")

    # ---------------- 模拟考生作答 ----------------
    # 注意：试卷接口**不会**下发正确答案（这是刻意的安全约束，由后端契约测试保证）。
    # 因此这里必须用建题时自己记录的正确答案，而不是从试卷里读。
    question_meta = {q["id"]: q for q in created.values()}

    stats_before = request(base, "GET", f"/api/admin/exams/{exam_id}/stats", token=token)
    if stats_before["attempt_count"] > 0:
        # 重复运行 dev.sh 时不要重复交卷（已交卷的考生会被后端正确拒绝）
        submitted = stats_before["attempt_count"]
        print("  ✓ 已有交卷记录，跳过模拟作答（想重新开始请执行 ./dev.sh --reset）")
    else:
        submitted = 0
        for phone, name, _id_card in ROSTER:
            plan = ANSWER_PLANS.get(name)
            if plan is None:
                continue  # 故意留作缺考

            code = codes.get(name)
            if not code:
                continue

            try:
                login = request(base, "POST", "/api/auth/join",
                                body={"phone": phone, "invite_code": code})
                cand_token = login["token"]
                attempt = request(base, "POST", f"/api/exams/{exam_id}/attempts", token=cand_token)
                paper = request(base, "GET", f"/api/exams/{exam_id}/paper", token=cand_token)

                answers = []
                for index, item in enumerate(paper["questions"]):
                    mode = plan[index] if index < len(plan) else "correct"
                    meta = question_meta.get(item["id"], item)
                    answers.append({"question_id": item["id"], "answer": build_answer(meta, mode)})

                body = {
                    "answers": answers,
                    "switch_count": 1 if name in {"刘洋", "陈静"} else 0,
                    "switch_log": ["2026-01-01T00:00:00.000Z"] if name in {"刘洋", "陈静"} else [],
                }
                request(base, "POST", f"/api/attempts/{attempt['attempt_id']}/submit",
                        token=cand_token, body=body)
                submitted += 1
            except ApiError as exc:
                print(f"      （{name} 交卷跳过：{exc.detail}）", file=sys.stderr)

        print(f"  ✓ 已模拟 {submitted} 人交卷，{len(ROSTER) - submitted} 人缺考")

    # ---------------- 输出试用信息 ----------------
    stats = request(base, "GET", f"/api/admin/exams/{exam_id}/stats", token=token)
    print()
    print("=" * 62)
    print("演示数据就绪")
    print("=" * 62)
    print(f"考试名称 ：{demo['title']}")
    print(f"选聘编号 ：{demo['recruitment_no']}")
    print(f"及格比例 ：{demo['pass_ratio']}%")
    print(f"统计快照 ：有 attempt {stats['attempt_count']} 人 / 缺考 {stats['absent_count']} 人 / "
          f"平均分 {stats['average_score']} / 及格线 {stats['pass_line']}")
    print()
    print("考生登录用的手机号 + 邀请码：")
    for phone, name, _id_card in ROSTER:
        suffix = "（缺考，未登录）" if name not in ANSWER_PLANS else ""
        print(f"  {phone}  {codes.get(name, '-')}   {name}{suffix}")
    print()
    print("提示：想换个身份重新答题，请用「未登录」的两名考生，")
    print("      或执行 ./dev.sh --reset 重建演示数据。")

    # 演示考试的有效期是基于「首次播种时刻」计算的；
    # 隔天再跑时它可能已经结束，考生会登不进去，这里提前说清楚。
    fresh = request(base, "GET", "/api/admin/exams", token=token)
    current = next((e for e in fresh if e["id"] == exam_id), None)
    if current and current.get("external_status") not in ("running", None):
        print()
        print(f"注意：当前演示考试状态为「{current['external_status']}」，考生可能无法登录答题。")
        print("      请执行 ./dev.sh --reset 用当前时间重建一场正在进行的考试。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
