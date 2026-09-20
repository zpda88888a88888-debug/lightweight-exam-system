"""阶段 5：邀请码生成（测试方案 6.8）。

规格依据：spec 4.6 / 架构 9.8
"""

from __future__ import annotations

from datetime import timedelta

from tests.support import (
    build_draft_scenario,
    build_running_scenario,
    generate_invites,
    import_roster,
    join,
)

ROSTER = [
    ("13800000001", "张三", "110101199001010011"),
    ("13800000002", "李四", "110101199001010022"),
    ("13800000003", "王五", "110101199001010033"),
]


def test_generated_codes_are_six_digit_numeric(client, clock):
    """生成的邀请码均为 6 位数字字符串（含前导零也算合法）。"""
    scenario = build_draft_scenario(
        client, clock, roster=ROSTER, import_roster_rows=True
    )
    assert scenario.generate(confirm=True).status_code == 200

    codes = scenario.codes()
    assert len(codes) == len(ROSTER)
    for code in codes:
        assert isinstance(code, str)
        assert len(code) == 6
        assert code.isdigit(), f"邀请码不是纯数字：{code}"


def test_codes_unique_within_exam(client, clock):
    """同一考试内所有考生邀请码互不相同。"""
    scenario = build_draft_scenario(
        client,
        clock,
        roster=[(f"1380000{i:04d}", f"考生{i}", f"11010119900101{i:04d}") for i in range(30)],
        import_roster_rows=True,
    )
    scenario.generate(confirm=True)
    codes = scenario.codes()
    assert len(codes) == 30
    assert len(set(codes)) == 30


def test_codes_globally_unique_across_exams(client, clock):
    """跨考试全局不重复（invite_code 为全局唯一约束）。"""
    first = build_draft_scenario(
        client, clock, roster=ROSTER, import_roster_rows=True, recruitment_no="ZP-G1"
    )
    second = build_draft_scenario(
        client, clock, roster=ROSTER, import_roster_rows=True, recruitment_no="ZP-G2"
    )
    first.generate(confirm=True)
    second.generate(confirm=True)

    codes_first = set(first.codes())
    codes_second = set(second.codes())
    assert len(codes_first) == len(ROSTER)
    assert len(codes_second) == len(ROSTER)
    assert codes_first.isdisjoint(codes_second), "不同考试之间出现重复邀请码"


def test_regenerate_requires_second_confirmation(client, clock):
    """重新生成需二次确认：未确认时报错，确认后成功。"""
    scenario = build_draft_scenario(
        client, clock, roster=ROSTER, import_roster_rows=True
    )
    # 首次生成：名单尚无码，无需确认
    assert scenario.generate(confirm=False).status_code == 200

    # 二次生成：未确认 → 拒绝
    resp = scenario.generate(confirm=False)
    assert resp.status_code == 409
    assert "覆盖" in resp.json()["detail"]

    # 确认后成功
    assert scenario.generate(confirm=True).status_code == 200


def test_regenerate_replaces_all_codes(client, clock):
    """重新生成后旧邀请码全部失效，新码全部替换。"""
    scenario = build_draft_scenario(
        client, clock, roster=ROSTER, import_roster_rows=True
    )
    scenario.generate(confirm=True)
    old_codes = set(scenario.codes())
    assert len(old_codes) == len(ROSTER)
    assert None not in old_codes

    scenario.generate(confirm=True)
    new_codes = set(scenario.codes())

    assert len(new_codes) == len(ROSTER)
    assert old_codes.isdisjoint(new_codes), "重新生成后仍存在旧邀请码"
    assert all(code is not None for code in new_codes)


def test_regeneration_invalidates_old_code_at_login(client, clock):
    """重新生成后，用旧码登录被拒绝，新码可用。"""
    scenario = build_draft_scenario(
        client, clock, roster=ROSTER, import_roster_rows=True
    )
    scenario.generate(confirm=True)
    old_code = scenario.code("张三")

    scenario.generate(confirm=True)
    new_code = scenario.code("张三")
    assert new_code != old_code

    assert scenario.publish().status_code == 200
    assert join(client, "13800000001", old_code).status_code == 403
    assert join(client, "13800000001", new_code).status_code == 200


def test_generate_only_allowed_in_draft(client, clock):
    """仅草稿状态可生成/重新生成邀请码，发布后冻结。"""
    scenario = build_running_scenario(client, clock)
    resp = generate_invites(client, scenario.headers, scenario.exam_id, confirm=True)
    assert resp.status_code == 409


def test_login_fails_before_codes_generated(client, clock):
    """名单导入后未生成邀请码 → 考生无法登录。"""
    scenario = build_draft_scenario(
        client, clock, roster=ROSTER, import_roster_rows=True
    )
    assert scenario.codes() == [None, None, None]
    assert scenario.publish().status_code == 200

    # 任何邀请码都无法登录（未生成）
    for candidate_code in ("000000", "111111", "123456"):
        assert join(client, "13800000001", candidate_code).status_code == 403


def test_generate_for_empty_roster_is_harmless(client, clock):
    """空名单生成邀请码 → 生成 0 个，不报错。"""
    scenario = build_draft_scenario(client, clock, roster=[])
    resp = scenario.generate(confirm=True)
    assert resp.status_code == 200
    assert resp.json()["generated"] == 0


def test_codes_export_csv_contains_all_candidates(client, clock):
    """邀请码导出 CSV 含全部考生与邀请码。"""
    scenario = build_draft_scenario(
        client, clock, roster=ROSTER, import_roster_rows=True
    )
    scenario.generate(confirm=True)

    resp = client.get(
        f"/api/admin/exams/{scenario.exam_id}/candidates/export", headers=scenario.headers
    )
    assert resp.status_code == 200
    text = resp.content.decode("utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    assert lines[0].strip() == "手机号,姓名,身份证号,邀请码"
    assert len(lines) == 1 + len(ROSTER)
    for phone, name, id_card in ROSTER:
        assert phone in text and name in text and id_card in text


def test_concurrent_generation_produces_unique_codes(client, clock):
    """并发生成（两个管理员同时触发）不产生重复码。"""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    scenario = build_draft_scenario(
        client,
        clock,
        roster=[(f"1380000{i:04d}", f"考生{i}", f"11010119900101{i:04d}") for i in range(20)],
        import_roster_rows=True,
    )

    barrier = threading.Barrier(2)
    statuses: list[int] = []
    lock = threading.Lock()

    def worker():
        barrier.wait(timeout=10)
        resp = generate_invites(client, scenario.headers, scenario.exam_id, confirm=True)
        with lock:
            statuses.append(resp.status_code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: worker(), range(2)))

    # 冲突由唯一约束兜底：允许一个成功、另一个失败，但绝不产生重复码
    codes = [c for c in scenario.codes() if c]
    assert len(codes) == len(set(codes)), "并发生成产生了重复邀请码"
