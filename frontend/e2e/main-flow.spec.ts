import { expect, test, type Page } from '@playwright/test'

/**
 * E2E 主干流程（测试方案第 10 阶段 8 / 准出标准 E8）：
 *   管理员建题 → 建考试 → 考试列表查询 → 考生管理导入名单/生成邀请码 → 发布
 *   → 试卷管理核对 → 考生答题 → 成绩统计 → 题库统计
 *   → 考生登录 → 答题 → 交卷 → 管理员查看统计与成绩
 *
 * 每次运行使用唯一标识（时间戳），可重复执行且不影响历史数据。
 */

const RUN = Date.now()
const RECRUITMENT_NO = `E2E-${RUN}`
const TAG = `E2E标签${RUN}`
const PHONE = `139${String(RUN).slice(-8)}`
const ID_CARD = `1101011990${String(RUN).slice(-8)}`
const CANDIDATE_NAME = '端到端考生'
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD ?? 'changeme'

/** datetime-local 需要 "YYYY-MM-DDTHH:MM" */
function localInput(offsetHours: number): string {
  const date = new Date(Date.now() + offsetHours * 3600 * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

async function loginAsAdmin(page: Page) {
  await page.goto('/admin.html#/exams')
  // 若管理端仍是登录态（token 在 localStorage），路由守卫会直接放行，
  // 此时不存在登录表单，不能盲目 fill。
  const account = page.getByLabel('账号')
  if (await account.isVisible().catch(() => false)) {
    await account.fill('admin')
    await page.getByLabel('密码').fill(ADMIN_PASSWORD)
    await page.getByRole('button', { name: '登录' }).click()
  }
  // 注意用 exact：登录页标题是「考试管理后台」，子串匹配会掩盖登录失败
  await expect(page.getByRole('heading', { name: '考试管理', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible()
}

test('E2E 主干流程：建题 → 组卷发布 → 考生答题交卷 → 成绩统计', async ({ page }) => {
  // 管理端的 confirm() 一律接受（发布、生成邀请码等二次确认）
  page.on('dialog', (dialog) => void dialog.accept())

  // ---------------- 1. 管理员登录 ----------------
  await loginAsAdmin(page)

  // ---------------- 2. 新建题目 ----------------
  await page.getByRole('link', { name: '题库管理' }).click()
  await expect(page.getByRole('heading', { name: '题库管理' })).toBeVisible()

  await page.getByRole('button', { name: '+ 新增题目' }).click()
  const form = page.locator('.modal')
  await form.getByLabel('题干').fill(`端到端题目 ${RUN}`)
  await form.getByPlaceholder('选项 A 的内容').fill('正确选项')
  await form.getByPlaceholder('选项 B 的内容').fill('错误选项')
  // 勾选 A 为正确答案
  await form.locator('.option-row').first().locator('input[type="checkbox"]').check()
  await form.getByLabel('分值').fill('10')
  await form.getByLabel(/标签/).fill(TAG)
  await form.getByRole('button', { name: '保存' }).click()

  await expect(page.locator('.alert-success')).toContainText('题目已新增')
  await expect(page.getByText(`端到端题目 ${RUN}`)).toBeVisible()

  // ---------------- 3. 新建考试草稿 ----------------
  await page.getByRole('link', { name: '考试管理' }).click()
  await page.getByRole('button', { name: '+ 新建考试' }).click()

  const examModal = page.locator('.modal')
  await examModal.getByLabel('考试名称').fill(`端到端考试 ${RUN}`)
  await examModal.getByLabel(/选聘编号/).fill(RECRUITMENT_NO)
  await examModal.getByLabel(/开考时间/).fill(localInput(-1))
  await examModal.getByLabel(/截止时间/).fill(localInput(2))
  await examModal.getByLabel('及格比例').selectOption('50')
  // CH-004：及格比例必须展示口径说明
  await expect(examModal.getByText('同分并列者全部通过')).toBeVisible()

  // CH-005：标签是封闭选项（下拉），并显示可用题数
  const tagSelect = examModal.locator('select.rule-tag')
  await expect(tagSelect.locator('option', { hasText: TAG })).toHaveCount(1)
  await tagSelect.selectOption(TAG)
  // 该标签只建了 1 道题，抽题数设为 1（超过可用题数会被即时拦截）
  await examModal.locator('.rule-row').first().locator('input[type="number"]').fill('1')
  await examModal.getByRole('button', { name: '保存' }).click()

  await expect(page.locator('.alert-success')).toContainText('考试草稿已创建')
  const examRow = page.locator('tr', { hasText: RECRUITMENT_NO })
  await expect(examRow).toBeVisible()

  // ---------------- 4. 导入名单 + 生成邀请码 ----------------
  // ---------------- 3.5 考试列表查询（CH-006） ----------------
  await page.locator('#q-title').fill(`端到端考试 ${RUN}`)
  await page.getByRole('button', { name: '查询' }).click()
  await expect(page.locator('table tbody tr')).toHaveCount(1)
  await expect(page.locator('tr', { hasText: RECRUITMENT_NO })).toBeVisible()

  // 状态查询：刚建的是草稿
  await page.locator('#q-status').selectOption('draft')
  await expect(page.locator('tr', { hasText: RECRUITMENT_NO })).toBeVisible()

  // 选聘编号包含匹配
  await page.locator('#q-status').selectOption('')
  await page.locator('#q-title').fill('')
  await page.locator('#q-no').fill(RECRUITMENT_NO)
  await page.getByRole('button', { name: '查询' }).click()
  await expect(page.locator('tr', { hasText: RECRUITMENT_NO })).toBeVisible()

  // 清除条件后恢复完整列表
  await page.getByRole('button', { name: '清除' }).click()
  await expect(page.locator('tr', { hasText: RECRUITMENT_NO })).toBeVisible()

  // CH-007：名单与邀请码已迁到「考生管理」，草稿行提供跳转并预选该场次
  await examRow.getByRole('button', { name: '名单与邀请码' }).click()
  await expect(page.getByRole('heading', { name: '考生管理' })).toBeVisible()
  // CH-009：场次选择器是「查询 + 可点击列表」，跳转后直接处于已选（收起）状态
  await expect(page.locator('.selected-bar')).toContainText(RECRUITMENT_NO)

  // 验证「更换场次」能重新打开查询界面，并按名称筛选到场次
  await page.getByRole('button', { name: '更换场次' }).click()
  await page.locator('#p-title').fill(`端到端考试 ${RUN}`)
  await page.getByRole('button', { name: '查询' }).click()
  await expect(page.locator('.exam-row')).toHaveCount(1)
  await page.locator('.exam-row').first().click()
  await expect(page.locator('.selected-bar')).toContainText(RECRUITMENT_NO)

  await page
    .locator('textarea')
    .fill(`手机号,姓名,身份证号\n${PHONE},${CANDIDATE_NAME},${ID_CARD}\n`)
  await page.getByRole('button', { name: '导入到本场考试' }).click()
  await expect(page.locator('.alert-success')).toContainText('导入完成')

  await page.getByRole('button', { name: '生成邀请码' }).click()
  await page.locator('.modal').getByRole('button', { name: '确认生成' }).click()
  await expect(page.locator('.alert-success')).toContainText('已生成')

  const codeCell = page.locator('.code-cell').first()
  await expect(codeCell).toBeVisible()
  const inviteCode = (await codeCell.textContent())?.trim() ?? ''
  expect(inviteCode).toMatch(/^\d{6}$/)

  // ---------------- 5. 发布考试 ----------------
  await page.getByRole('link', { name: '考试管理' }).click()
  const draftRow = page.locator('tr', { hasText: RECRUITMENT_NO })
  await draftRow.getByRole('button', { name: '发布' }).click()
  await expect(page.locator('.alert-success')).toContainText('发布成功')
  await expect(page.locator('tr', { hasText: RECRUITMENT_NO })).toContainText('进行中')

  // ---------------- 5.5 试卷管理：核对考试与试卷的对应关系（CH-002） ----------------
  await page.getByRole('link', { name: '试卷管理' }).click()
  await expect(page.getByRole('heading', { name: '试卷管理' })).toBeVisible()

  const paperRow = page.locator('tr', { hasText: RECRUITMENT_NO })
  await expect(paperRow).toBeVisible()
  await expect(paperRow).toContainText('1') // 题数
  await paperRow.getByRole('button', { name: '查看试卷' }).click()

  await expect(page.getByText('只读')).toBeVisible()
  await expect(page.getByText(`端到端题目 ${RUN}`)).toBeVisible()
  await expect(page.getByText('正确答案').first()).toBeVisible()
  // 用类定位分值标签，避免与上方"总分 10 分"的说明文字产生歧义匹配
  await expect(page.locator('.tag-score')).toHaveText('10 分')
  // 只读：不提供任何改题入口
  await expect(page.getByRole('button', { name: /编辑|保存|换题/ })).toHaveCount(0)

  // ---------------- 6. 考生登录并答题 ----------------
  await page.goto('/#/')
  await page.getByLabel('手机号').fill(PHONE)
  await page.getByLabel('邀请码').fill(inviteCode)
  await page.getByRole('button', { name: '进入考试' }).click()

  await expect(page.getByRole('button', { name: '开始考试' })).toBeVisible()
  await page.getByRole('button', { name: '开始考试' }).click()

  // 一页到底：题干出现
  await expect(page.getByText(`端到端题目 ${RUN}`)).toBeVisible()
  await expect(page.getByText('单选题')).toBeVisible()

  // CH-001：选项标号按显示位置依次为 A、B…（不出现"第一项标号是 B"）
  const optionLabels = await page.locator('.option-key').allTextContents()
  expect(optionLabels).toEqual(['A', 'B'])

  // 选择「正确选项」（选项已按考生种子乱序，故按文本定位）
  await page.locator('.option', { hasText: '正确选项' }).click()
  await expect(page.locator('.option.is-selected')).toHaveCount(1)

  // 答题卡显示已答
  await page.getByRole('button', { name: '答题卡' }).click()
  await expect(page.locator('.modal').getByText('已答 1 / 1')).toBeVisible()
  await page.getByRole('button', { name: '关闭' }).click()

  // 刷新后答案恢复（IndexedDB）
  await page.reload()
  await expect(page.locator('.option.is-selected')).toHaveCount(1)

  // ---------------- 7. 交卷 ----------------
  await page.getByRole('button', { name: '交卷' }).first().click()
  await expect(page.locator('.modal')).toContainText('题目已全部作答')
  await page.getByRole('button', { name: '确认交卷' }).click()

  await expect(page.getByRole('heading', { name: '交卷成功' })).toBeVisible()

  // 已交卷后再次登录被拒绝
  await page.goto('/#/')
  await page.getByLabel('手机号').fill(PHONE)
  await page.getByLabel('邀请码').fill(inviteCode)
  await page.getByRole('button', { name: '进入考试' }).click()
  await expect(page.locator('.alert-error')).toContainText('你已交卷')

  // ---------------- 8. 管理员查看统计与成绩 ----------------
  await loginAsAdmin(page)
  const publishedRow = page.locator('tr', { hasText: RECRUITMENT_NO })
  await publishedRow.getByRole('button', { name: '成绩/统计' }).click()

  await expect(page.locator('.stat-card', { hasText: '名单人数' })).toContainText('1')
  await expect(page.locator('.stat-card', { hasText: '有 attempt' })).toContainText('1')
  await expect(page.locator('.stat-card', { hasText: '缺考' })).toContainText('0')
  await expect(page.locator('.stat-card', { hasText: '平均分' })).toContainText('10')
  await expect(page.locator('.stat-card', { hasText: '及格率' })).toContainText('100%')

  // 成绩列表包含该考生，且状态为正常提交
  const resultRow = page.locator('tr', { hasText: CANDIDATE_NAME })
  await expect(resultRow).toContainText('正常提交')
  await expect(resultRow).toContainText('是')

  // 图表已渲染（ECharts 会插入 canvas）
  await expect(page.locator('canvas').first()).toBeVisible()

  // ---------------- 9. 题库统计（CH-008） ----------------
  await page.getByRole('link', { name: '题库管理' }).click()
  await page.getByLabel('关键词').fill(`端到端题目 ${RUN}`)
  await page.getByRole('button', { name: '查询' }).click()

  const questionRow = page.locator('tr', { hasText: `端到端题目 ${RUN}` })
  await expect(questionRow).toBeVisible()
  // 上次被抽中：应显示这场考试
  await expect(questionRow).toContainText(`端到端考试 ${RUN}`)
  // 累计正确率：1 人作答且答对 → 100%
  await expect(questionRow).toContainText('100%')
})
