"""阶段 4：试卷接口契约安全（测试方案 6.6）。

规格依据：架构 6、12 / spec 8

核心不变量：试卷接口绝不下发 answer_json / analysis。
对应变异 M8：响应中带上 answer_json → 本文件测试必须失败。
"""

from __future__ import annotations

import pytest

from tests.support import build_running_scenario

FORBIDDEN_KEYS = {"answer_json", "answer", "analysis", "correct", "correct_answer"}


def walk_keys(node, path="") -> list[tuple[str, str]]:
    """递归收集所有 (路径, 键名)。"""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append((f"{path}.{key}", key))
            found.extend(walk_keys(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(walk_keys(value, f"{path}[{index}]"))
    return found


def test_paper_response_has_no_answer_field(client, clock):
    """响应 JSON 中不存在 answer_json / answer / analysis（递归检查）。"""
    scenario = build_running_scenario(client, clock, question_count=3)
    resp = scenario.paper("张三")
    assert resp.status_code == 200, resp.text

    keys = walk_keys(resp.json())
    offending = [
        (path, key) for path, key in keys if key in FORBIDDEN_KEYS
    ]
    assert offending == [], f"试卷接口泄露了禁止字段：{offending}"


def test_paper_top_level_field_set_is_exact(client, clock):
    """顶层字段集合精确匹配 {exam, questions}。"""
    scenario = build_running_scenario(client, clock, question_count=2)
    body = scenario.paper("张三").json()
    assert set(body.keys()) == {"exam", "questions"}


def test_paper_exam_field_set_is_exact(client, clock):
    """exam 字段集合精确匹配 {id, title, start_at, end_at}（架构 7.1）。"""
    scenario = build_running_scenario(client, clock, question_count=1)
    body = scenario.paper("张三").json()
    assert set(body["exam"].keys()) == {"id", "title", "start_at", "end_at"}


def test_paper_question_field_set_is_exact(client, clock):
    """题目字段集合精确匹配 {id, type, stem, options}。"""
    scenario = build_running_scenario(client, clock, question_count=2)
    body = scenario.paper("张三").json()
    assert len(body["questions"]) == 2
    for question in body["questions"]:
        assert set(question.keys()) == {"id", "type", "stem", "options"}


def test_paper_option_field_set_is_exact(client, clock):
    """选项字段集合精确匹配 {key, text}。"""
    scenario = build_running_scenario(client, clock, question_count=1)
    body = scenario.paper("张三").json()
    options = body["questions"][0]["options"]
    assert options
    for option in options:
        assert set(option.keys()) == {"key", "text"}


def test_paper_contains_all_snapshot_questions(client, clock):
    """试卷题目数量与快照一致，且 id 集合等于题库中抽中的题目。"""
    scenario = build_running_scenario(client, clock, question_count=5)
    body = scenario.paper("张三").json()
    paper_ids = {q["id"] for q in body["questions"]}
    bank_ids = {q["id"] for q in scenario.bank}
    assert paper_ids == bank_ids


def test_question_order_globally_fixed_across_candidates(client, clock):
    """题目顺序全局固定：不同考生看到的题目顺序一致（仅选项乱序）。"""
    scenario = build_running_scenario(client, clock, question_count=6)
    order_zhang = [q["id"] for q in scenario.paper("张三").json()["questions"]]
    order_li = [q["id"] for q in scenario.paper("李四").json()["questions"]]
    assert order_zhang == order_li


def test_paper_stem_and_type_match_bank(client, clock):
    """题干与题型与题库一致，未被篡改。"""
    scenario = build_running_scenario(client, clock, question_count=2)
    body = scenario.paper("张三").json()
    by_id = {q["id"]: q for q in scenario.bank}
    for question in body["questions"]:
        original = by_id[question["id"]]
        assert question["stem"] == original["stem"]
        assert question["type"] == original["type"]


@pytest.mark.parametrize("endpoint", ["paper", "stats", "results"])
def test_admin_endpoints_do_not_leak_answers_to_candidates(client, clock, endpoint):
    """考生 token 无法访问管理端接口（答案只存在于管理端视图）。"""
    scenario = build_running_scenario(client, clock, question_count=1)
    token = scenario.login("张三")
    url = {
        "paper": f"/api/admin/exams/{scenario.exam_id}/results",
        "stats": f"/api/admin/exams/{scenario.exam_id}/stats",
        "results": f"/api/admin/exams/{scenario.exam_id}/results/export",
    }[endpoint]
    resp = client.get(url, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_admin_endpoints_require_auth(client, clock):
    """管理端接口未认证 → 401。"""
    scenario = build_running_scenario(client, clock)
    assert client.get(f"/api/admin/exams/{scenario.exam_id}/results").status_code == 401
    assert client.get(f"/api/admin/exams/{scenario.exam_id}/stats").status_code == 401
