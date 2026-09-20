"""测试辅助：通过公开 API 搭建场景，不直接调用被测内部逻辑。

设计原则（测试方案 4.2）：
    辅助函数只负责「造场景」与「发请求」，不参与计算期望值，
    因此不会污染断言的独立性。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.clock import FrozenClock
from tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME


# --------------------------------------------------------------------------
# 管理端
# --------------------------------------------------------------------------


def admin_headers(client) -> dict:
    resp = client.post(
        "/api/admin/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def create_question(
    client,
    headers,
    *,
    stem: str,
    question_type: str = "single",
    options: list[dict] | None = None,
    answer: list[str] | None = None,
    score: float = 10,
    tags: list[str] | None = None,
):
    if options is None:
        options = [
            {"key": "A", "text": "选项A"},
            {"key": "B", "text": "选项B"},
            {"key": "C", "text": "选项C"},
            {"key": "D", "text": "选项D"},
        ]
    if answer is None:
        answer = ["A"] if question_type != "multi" else ["A", "B"]
    resp = client.post(
        "/api/admin/questions",
        headers=headers,
        json={
            "type": question_type,
            "stem": stem,
            "options": options,
            "answer": answer,
            "score": score,
            "tags": tags or [],
            "analysis": "解析内容",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def make_bank(client, headers, *, count: int, tag: str, score: float = 10, prefix: str = "题"):
    """创建 count 道单选，正确答案均为 A。"""
    return [
        create_question(
            client, headers, stem=f"{prefix}{i+1}", answer=["A"], score=score, tags=[tag]
        )
        for i in range(count)
    ]


def create_exam(
    client,
    headers,
    *,
    title: str = "测试考试",
    recruitment_no: str = "ZP2026001",
    start_at: datetime,
    end_at: datetime,
    pass_ratio: int = 50,
    rules: list[dict] | None = None,
):
    resp = client.post(
        "/api/admin/exams",
        headers=headers,
        json={
            "title": title,
            "recruitment_no": recruitment_no,
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "pass_ratio": pass_ratio,
            "settings": {"rules": rules or []},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def import_roster(client, headers, exam_id: int, rows: list[tuple[str, str, str]]):
    """rows: [(手机号, 姓名, 身份证号)]

    用 csv.writer 构造请求体，保证含逗号/引号的姓名被正确转义。
    """
    import csv as _csv
    import io as _io

    buffer = _io.StringIO()
    writer = _csv.writer(buffer, lineterminator="\n")
    writer.writerow(["手机号", "姓名", "身份证号"])
    for row in rows:
        writer.writerow(list(row))
    body = buffer.getvalue()
    resp = client.post(
        f"/api/admin/exams/{exam_id}/candidates/import",
        headers={**headers, "Content-Type": "text/csv; charset=utf-8"},
        content=body.encode("utf-8"),
    )
    return resp


def generate_invites(client, headers, exam_id: int, confirm: bool = True):
    return client.post(
        f"/api/admin/exams/{exam_id}/candidates/generate",
        headers=headers,
        json={"confirm": confirm},
    )


def list_candidates(client, headers, exam_id: int) -> list[dict]:
    resp = client.get(f"/api/admin/exams/{exam_id}/candidates", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def publish(client, headers, exam_id: int):
    return client.post(f"/api/admin/exams/{exam_id}/publish", headers=headers)


def invite_code_for(client, headers, exam_id: int, name: str) -> str:
    for row in list_candidates(client, headers, exam_id):
        if row["name"] == name:
            assert row["invite_code"], f"{name} 还没有邀请码"
            return row["invite_code"]
    raise AssertionError(f"名单中没有 {name}")


# --------------------------------------------------------------------------
# 考生端
# --------------------------------------------------------------------------


def join(client, phone: str, invite_code: str):
    return client.post("/api/auth/join", json={"phone": phone, "invite_code": invite_code})


def join_ok(client, phone: str, invite_code: str) -> str:
    resp = join(client, phone, invite_code)
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def create_attempt(client, token: str, exam_id: int):
    return client.post(
        f"/api/exams/{exam_id}/attempts", headers={"Authorization": f"Bearer {token}"}
    )


def create_attempt_ok(client, token: str, exam_id: int) -> int:
    resp = create_attempt(client, token, exam_id)
    assert resp.status_code == 200, resp.text
    return resp.json()["attempt_id"]


def get_paper(client, token: str, exam_id: int):
    return client.get(
        f"/api/exams/{exam_id}/paper", headers={"Authorization": f"Bearer {token}"}
    )


def submit(client, token: str, attempt_id: int, answers: list[dict], **extra):
    body = {"answers": answers, "switch_count": extra.pop("switch_count", 0),
            "switch_log": extra.pop("switch_log", []), **extra}
    return client.post(
        f"/api/attempts/{attempt_id}/submit",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )


# --------------------------------------------------------------------------
# 端到端场景装配
# --------------------------------------------------------------------------


class Scenario:
    """一场「进行中、已发布」考试的完整场景句柄。"""

    def __init__(self, client, clock: FrozenClock, headers, exam, bank, roster):
        self.client = client
        self.clock = clock
        self.headers = headers
        self.exam = exam
        self.bank = bank
        self.roster = roster  # [(phone, name, id_card)]
        # API 返回的是 ISO 字符串，解析为 naive datetime 便于时间断言
        self.start_at = datetime.fromisoformat(exam["start_at"])
        self.end_at = datetime.fromisoformat(exam["end_at"])

    @property
    def exam_id(self) -> int:
        return self.exam["id"]

    def code(self, name: str) -> str:
        return invite_code_for(self.client, self.headers, self.exam_id, name)

    def login(self, name: str) -> str:
        phone = next(p for p, n, _ in self.roster if n == name)
        return join_ok(self.client, phone, self.code(name))

    def start(self, name: str) -> int:
        return create_attempt_ok(self.client, self.login(name), self.exam_id)

    def paper(self, name: str):
        return get_paper(self.client, self.login(name), self.exam_id)

    def answer_all_correct(self) -> list[dict]:
        """所有单选题都选 A（题库正确答案均为 A）。"""
        return [{"question_id": q["id"], "answer": ["A"]} for q in self.bank]


def build_running_scenario(
    client,
    clock: FrozenClock,
    *,
    question_count: int = 3,
    tag: str = "标签A",
    score: float = 10,
    pass_ratio: int = 50,
    roster: list[tuple[str, str, str]] | None = None,
    recruitment_no: str = "ZP2026001",
    title: str = "测试考试",
    rules: list[dict] | None = None,
    start_offset: timedelta = timedelta(hours=-1),
    end_offset: timedelta = timedelta(hours=1),
) -> Scenario:
    """搭建：建题库 → 建草稿 → 导入名单 → 生成邀请码 → 发布。"""
    headers = admin_headers(client)
    bank = make_bank(client, headers, count=question_count, tag=tag, score=score)
    exam = create_exam(
        client,
        headers,
        title=title,
        recruitment_no=recruitment_no,
        start_at=clock.now() + start_offset,
        end_at=clock.now() + end_offset,
        pass_ratio=pass_ratio,
        rules=rules if rules is not None else [{"tag": tag, "count": question_count}],
    )
    roster = roster if roster is not None else [
        ("13800000001", "张三", "110101199001010011"),
        ("13800000002", "李四", "110101199001010022"),
    ]
    import_roster(client, headers, exam["id"], roster)
    generate_invites(client, headers, exam["id"], confirm=True)
    resp = publish(client, headers, exam["id"])
    assert resp.status_code == 200, resp.text
    return Scenario(client, clock, headers, exam, bank, roster)


class DraftScenario:
    """一场未发布的草稿考试场景句柄。"""

    def __init__(self, client, clock: FrozenClock, headers, exam, bank, roster):
        self.client = client
        self.clock = clock
        self.headers = headers
        self.exam = exam
        self.bank = bank
        self.roster = roster
        self.start_at = datetime.fromisoformat(exam["start_at"])
        self.end_at = datetime.fromisoformat(exam["end_at"])

    @property
    def exam_id(self) -> int:
        return self.exam["id"]

    def candidates(self) -> list[dict]:
        return list_candidates(self.client, self.headers, self.exam_id)

    def codes(self) -> list[str]:
        return [row["invite_code"] for row in self.candidates()]

    def code(self, name: str) -> str:
        return invite_code_for(self.client, self.headers, self.exam_id, name)

    def import_rows(self, rows):
        return import_roster(self.client, self.headers, self.exam_id, rows)

    def generate(self, confirm: bool = True):
        return generate_invites(self.client, self.headers, self.exam_id, confirm=confirm)

    def publish(self):
        return publish(self.client, self.headers, self.exam_id)

    def payload(self, **overrides) -> dict:
        """用于 PUT /api/admin/exams/{id} 的合法载荷。"""
        body = {
            "title": self.exam["title"],
            "recruitment_no": self.exam["recruitment_no"],
            "start_at": self.exam["start_at"],
            "end_at": self.exam["end_at"],
            "pass_ratio": self.exam["pass_ratio"],
            "settings": self.exam["settings"],
        }
        body.update(overrides)
        return body


def build_draft_scenario(
    client,
    clock: FrozenClock,
    *,
    question_count: int = 3,
    tag: str = "标签A",
    score: float = 10,
    pass_ratio: int = 50,
    roster: list[tuple[str, str, str]] | None = None,
    recruitment_no: str = "ZP-DRAFT",
    title: str = "草稿考试",
    rules: list[dict] | None = None,
    import_roster_rows: bool = False,
) -> DraftScenario:
    """搭建：建题库 → 建草稿（可选导入名单，默认不生成邀请码）。"""
    headers = admin_headers(client)
    bank = make_bank(client, headers, count=question_count, tag=tag, score=score)
    exam = create_exam(
        client,
        headers,
        title=title,
        recruitment_no=recruitment_no,
        start_at=clock.now() + timedelta(hours=-1),
        end_at=clock.now() + timedelta(hours=1),
        pass_ratio=pass_ratio,
        rules=rules if rules is not None else [{"tag": tag, "count": question_count}],
    )
    roster = roster if roster is not None else [
        ("13800000001", "张三", "110101199001010011"),
        ("13800000002", "李四", "110101199001010022"),
    ]
    if import_roster_rows:
        assert import_roster(client, headers, exam["id"], roster).status_code == 200
    return DraftScenario(client, clock, headers, exam, bank, roster)
