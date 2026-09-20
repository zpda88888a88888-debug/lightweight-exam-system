"""阶段 5：名单 CSV 导入（测试方案 6.9）。

规格依据：spec 4.6 / 架构 9.8

规格冲突 R1 已由业务方确认（2026-09-19）：
    身份证号已存在 → 关联已有考生并更新姓名、手机号（upsert），不报错。
    本文件按该口径断言；spec 4.6 的「重复导入报错」口径不再适用。
"""

from __future__ import annotations

from tests.support import build_draft_scenario

ROWS = [
    ("13800000001", "张三", "110101199001010011"),
    ("13800000002", "李四", "110101199001010022"),
]


def post_csv(client, headers, exam_id, text: str, *, content_type="text/csv; charset=utf-8",
             raw: bytes | None = None):
    return client.post(
        f"/api/admin/exams/{exam_id}/candidates/import",
        headers={**headers, "Content-Type": content_type},
        content=raw if raw is not None else text.encode("utf-8"),
    )


# --------------------------------------------------------------------------
# 表头校验
# --------------------------------------------------------------------------


def test_valid_import_creates_users_and_links(client, clock):
    """合法导入：建立考生并关联到考试名单。"""
    scenario = build_draft_scenario(client, clock)
    resp = scenario.import_rows(ROWS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["users_created"] == 2
    assert body["linked"] == 2
    assert body["total_rows"] == 2

    candidates = scenario.candidates()
    assert len(candidates) == 2
    assert {c["name"] for c in candidates} == {"张三", "李四"}


def test_header_order_and_naming_must_match(client, clock):
    """表头必须为「手机号,姓名,身份证号」（顺序与命名一致）。"""
    scenario = build_draft_scenario(client, clock)

    wrong_order = "姓名,手机号,身份证号\n张三,13800000001,110101199001010011\n"
    resp = post_csv(client, scenario.headers, scenario.exam_id, wrong_order)
    assert resp.status_code == 422
    assert "表头" in resp.json()["detail"]

    wrong_name = "手机号,名字,身份证号\n13800000001,张三,110101199001010011\n"
    assert post_csv(client, scenario.headers, scenario.exam_id, wrong_name).status_code == 422

    missing_column = "手机号,姓名\n13800000001,张三\n"
    assert post_csv(client, scenario.headers, scenario.exam_id, missing_column).status_code == 422


def test_empty_csv_rejected(client, clock):
    """空内容 → 422。"""
    scenario = build_draft_scenario(client, clock)
    assert post_csv(client, scenario.headers, scenario.exam_id, "").status_code == 422


def test_bom_prefixed_csv_accepted(client, clock):
    """带 UTF-8 BOM 的 CSV（Excel 导出常见）可正常导入。"""
    scenario = build_draft_scenario(client, clock)
    text = "手机号,姓名,身份证号\n13800000001,张三,110101199001010011\n"
    resp = post_csv(client, scenario.headers, scenario.exam_id, "", raw=("\ufeff" + text).encode("utf-8"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["users_created"] == 1


def test_json_body_form_accepted(client, clock):
    """同时支持 application/json 的 {"csv": "..."} 形式。"""
    scenario = build_draft_scenario(client, clock)
    text = "手机号,姓名,身份证号\n13800000001,张三,110101199001010011\n"
    resp = client.post(
        f"/api/admin/exams/{scenario.exam_id}/candidates/import",
        headers=scenario.headers,
        json={"csv": text},
    )
    assert resp.status_code == 200, resp.text


def test_invalid_utf8_rejected(client, clock):
    """编码异常 → 422。"""
    scenario = build_draft_scenario(client, clock)
    resp = post_csv(client, scenario.headers, scenario.exam_id, "", raw=b"\xff\xfe\x00bad")
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# 内容校验
# --------------------------------------------------------------------------


def test_empty_lines_ignored(client, clock):
    """空行不影响导入。"""
    scenario = build_draft_scenario(client, clock)
    text = (
        "手机号,姓名,身份证号\n"
        "13800000001,张三,110101199001010011\n"
        "\n"
        ",,\n"
        "13800000002,李四,110101199001010022\n"
    )
    resp = post_csv(client, scenario.headers, scenario.exam_id, text)
    assert resp.status_code == 200, resp.text
    assert resp.json()["users_created"] == 2


def test_missing_id_card_rejected(client, clock):
    """身份证号为空 → 422。"""
    scenario = build_draft_scenario(client, clock)
    text = "手机号,姓名,身份证号\n13800000001,张三,\n"
    resp = post_csv(client, scenario.headers, scenario.exam_id, text)
    assert resp.status_code == 422
    assert "身份证号" in resp.json()["detail"]


def test_invalid_phone_rejected(client, clock):
    """手机号格式非法 → 422（spec 4.6 建议的格式校验）。"""
    scenario = build_draft_scenario(client, clock)
    text = "手机号,姓名,身份证号\n123,张三,110101199001010011\n"
    resp = post_csv(client, scenario.headers, scenario.exam_id, text)
    assert resp.status_code == 422
    assert "手机号" in resp.json()["detail"]


def test_row_with_missing_columns_rejected(client, clock):
    """行缺少列 → 422。"""
    scenario = build_draft_scenario(client, clock)
    text = "手机号,姓名,身份证号\n13800000001,张三\n"
    assert post_csv(client, scenario.headers, scenario.exam_id, text).status_code == 422


# --------------------------------------------------------------------------
# 身份证号唯一性与 upsert（R1 已确认口径）
# --------------------------------------------------------------------------


def test_duplicate_id_card_upserts_name_and_phone(client, clock):
    """身份证号已存在 → 关联并更新姓名、手机号，不报错、不重复建人。"""
    scenario = build_draft_scenario(client, clock)
    assert scenario.import_rows([ROWS[0]]).status_code == 200

    # 同一身份证号，姓名与手机号都变了
    updated = scenario.import_rows([("13800000009", "张三改名", ROWS[0][2])])
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["users_created"] == 0
    assert body["users_updated"] == 1
    assert body["linked"] == 0  # 已有名单关联，不新增

    candidates = scenario.candidates()
    assert len(candidates) == 1
    assert candidates[0]["name"] == "张三改名"
    assert candidates[0]["phone"] == "13800000009"


def test_reimport_identical_csv_is_idempotent(client, clock):
    """重复导入同一份名单：不重复建人、不重复关联、无报错。"""
    scenario = build_draft_scenario(client, clock)
    first = scenario.import_rows(ROWS).json()
    second = scenario.import_rows(ROWS).json()

    assert first["users_created"] == 2
    assert second["users_created"] == 0
    assert second["users_updated"] == 0
    assert second["linked"] == 0
    assert len(scenario.candidates()) == 2


def test_same_person_across_exams_reuses_user(client, clock):
    """身份证号全局唯一：跨考试导入同一人 → 复用同一 user 记录。"""
    first = build_draft_scenario(client, clock, recruitment_no="ZP-R1")
    second = build_draft_scenario(client, clock, recruitment_no="ZP-R2")

    first.import_rows([ROWS[0]])
    second.import_rows([ROWS[0]])

    user_ids_first = {c["user_id"] for c in first.candidates()}
    user_ids_second = {c["user_id"] for c in second.candidates()}
    assert user_ids_first == user_ids_second, "同一身份证号在不同考试应关联同一考生"


def test_duplicate_id_card_within_same_file_merged(client, clock):
    """同一批次内重复身份证号 → 合并为一条，不报错。"""
    scenario = build_draft_scenario(client, clock)
    text = (
        "手机号,姓名,身份证号\n"
        "13800000001,张三,110101199001010011\n"
        "13800000002,张三重复,110101199001010011\n"
    )
    resp = post_csv(client, scenario.headers, scenario.exam_id, text)
    assert resp.status_code == 200, resp.text
    assert len(scenario.candidates()) == 1


def test_import_only_allowed_in_draft(client, clock):
    """发布后名单冻结，导入被拒绝。"""
    from tests.support import build_running_scenario

    scenario = build_running_scenario(client, clock)
    resp = scenario.client.post(
        f"/api/admin/exams/{scenario.exam_id}/candidates/import",
        headers={**scenario.headers, "Content-Type": "text/csv; charset=utf-8"},
        content="手机号,姓名,身份证号\n13800000009,王五,110101199001010099\n".encode("utf-8"),
    )
    assert resp.status_code == 409
