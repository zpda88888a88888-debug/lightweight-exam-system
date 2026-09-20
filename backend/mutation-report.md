# 变异测试报告（测试方案 4.3 / 准出标准 E3）

- 执行时间：自动生成
- 结果：**10/10** 个变异被捕获

| 编号 | 注入点 | 变异内容 | 预期捕获测试 | 结果 |
|---|---|---|---|---|
| M1 | 多选判分 | 「选错得 0 分」改为「选错扣分」 | `tests/test_scoring.py::test_multi_choice_wrong_selection_scores_zero` | ✅ 已捕获 |
| M2 | 多选判分 | 漏选比例分母改为「已选数量」 | `tests/test_scoring.py::test_multi_choice_partial_selection_scores_proportionally` | ✅ 已捕获 |
| M3 | 多选判分 | 保留 2 位小数 | `tests/test_scoring.py::test_score_rounded_to_one_decimal` | ✅ 已捕获 |
| M4 | 及格线 | 「并列全部通过」改为「只取前 N 名」 | `tests/test_pass_line.py::test_pass_line_includes_all_ties` | ✅ 已捕获 |
| M5 | 及格率/平均分口径 | 分母改为「全部考生（含缺考）」 | `tests/test_stats_export.py::test_average_score_denominator_excludes_absent` | ✅ 已捕获 |
| M6 | 标错率 | 未作答不计入分母 | `tests/test_wrong_rate.py::test_wrong_rate_counts_unanswered_as_wrong` | ✅ 已捕获 |
| M7 | 幂等 | 重复提交重新判分 | `tests/test_attempt_idempotency.py::test_submit_is_idempotent` | ✅ 已捕获 |
| M8 | 试卷接口 | 响应中带上 answer_json | `tests/test_paper_contract.py::test_paper_response_has_no_answer_field` | ✅ 已捕获 |
| M9 | 选项乱序 | 种子改为随机 | `tests/test_shuffling.py::test_option_order_stable_for_same_candidate` | ✅ 已捕获 |
| M10 | 发布冻结 | 发布后允许改组卷 | `tests/test_publish_freeze.py::test_published_exam_rejects_rule_change` | ✅ 已捕获 |
