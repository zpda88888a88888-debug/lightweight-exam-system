<script setup lang="ts">
/**
 * 考试管理：列表、创建/编辑草稿（含组卷规则）、发布、归档、删除。
 * 状态门禁与后端一致：草稿可改可删可发布；发布后全冻结，仅可归档。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, api } from '@/api/client'
import type { ExamOut, TagCount } from '@/api/client'
import { examStatusClass, examStatusLabel, isDraft } from '@/lib/examStatus'
import {
  dateToLocalInput,
  formatLocal,
  localDateEndToServer,
  localDateStartToServer,
  localInputToServer,
  serverToLocalInput,
} from '@/lib/time'
import { adminSession } from '../session'

const router = useRouter()

const exams = ref<ExamOut[]>([])
const loading = ref(false)
const error = ref('')
const notice = ref('')

/**
 * 考试列表查询条件（CH-006）。
 * 状态用对外状态（与界面一致），开考时间用本地日期区间。
 */
const filters = ref({
  status: '',
  recruitment_no: '',
  title: '',
  start_from: '',
  start_to: '',
})

const showForm = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const formError = ref('')

const passRatioOptions = [10, 20, 30, 40, 50, 60, 70, 80, 90]

/**
 * 题库标签（CH-005）：组卷规则的标签改为封闭选项，并显示每个标签的可用题数。
 * 手打标签极易出现错别字（如多一个空格），导致发布时才发现题量不足。
 */
const tags = ref<TagCount[]>([])

const form = reactive({
  title: '',
  recruitment_no: '',
  start_at: '',
  end_at: '',
  pass_ratio: 50,
  rules: [{ tag: '', count: 5 }],
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [examList, tagList] = await Promise.all([
      api.listExams(adminSession.token, {
        status: filters.value.status || undefined,
        recruitment_no: filters.value.recruitment_no.trim() || undefined,
        title: filters.value.title.trim() || undefined,
        start_from: localDateStartToServer(filters.value.start_from) || undefined,
        start_to: localDateEndToServer(filters.value.start_to) || undefined,
      }),
      api.listTags(adminSession.token),
    ])
    exams.value = examList
    tags.value = tagList
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '加载考试列表失败'
  } finally {
    loading.value = false
  }
}

/** 某标签当前可用的题数（未知标签返回 0） */
function availableFor(tag: string): number {
  return tags.value.find((item) => item.tag === tag)?.question_count ?? 0
}

/**
 * 渲染用的标签选项：题库标签 + 当前规则里已存在但题库已没有的标签。
 * 后者必须保留，否则编辑历史草稿时会把已有标签悄悄清空。
 */
function tagOptionsFor(current: string): { tag: string; question_count: number }[] {
  const options = [...tags.value]
  if (current && !options.some((item) => item.tag === current)) {
    options.unshift({ tag: current, question_count: 0 })
  }
  return options
}

/** 抽题数是否超过该标签可用题数（即时提示，不等发布才报错） */
function ruleOverflow(rule: { tag: string; count: number }): boolean {
  if (!rule.tag) return false
  const available = availableFor(rule.tag)
  return Number(rule.count) > available
}

function openCreate() {
  editingId.value = null
  form.title = ''
  form.recruitment_no = ''
  const now = new Date()
  const later = new Date(now.getTime() + 2 * 3600 * 1000)
  form.start_at = dateToLocalInput(now)
  form.end_at = dateToLocalInput(later)
  form.pass_ratio = 50
  form.rules = [{ tag: '', count: 5 }]
  formError.value = ''
  showForm.value = true
}

function openEdit(exam: ExamOut) {
  editingId.value = exam.id
  form.title = exam.title
  form.recruitment_no = exam.recruitment_no
  form.start_at = serverToLocalInput(exam.start_at)
  form.end_at = serverToLocalInput(exam.end_at)
  form.pass_ratio = exam.pass_ratio
  form.rules = exam.settings.rules.length
    ? exam.settings.rules.map((r) => ({ ...r }))
    : [{ tag: '', count: 5 }]
  formError.value = ''
  showForm.value = true
}

function addRule() {
  form.rules.push({ tag: '', count: 5 })
}

function removeRule(index: number) {
  form.rules.splice(index, 1)
}

async function onSave() {
  formError.value = ''
  if (!form.title.trim() || !form.recruitment_no.trim()) {
    formError.value = '请填写考试名称与选聘编号'
    return
  }
  if (!form.start_at || !form.end_at) {
    formError.value = '请填写开考时间与截止时间'
    return
  }
  const start = localInputToServer(form.start_at)
  const end = localInputToServer(form.end_at)
  if (end <= start) {
    formError.value = '截止时间必须晚于开考时间'
    return
  }
  const rules = form.rules
    .map((r) => ({ tag: r.tag, count: Number(r.count) }))
    .filter((r) => r.tag && r.count > 0)
  if (rules.length === 0) {
    formError.value = '请至少配置一条组卷规则（标签 + 题数）'
    return
  }
  // 即时校验：抽题数不能超过该标签可用题数（后端也会再校验一次）
  for (const rule of rules) {
    const available = availableFor(rule.tag)
    if (rule.count > available) {
      formError.value = `标签「${rule.tag}」题库仅有 ${available} 题，无法抽取 ${rule.count} 题`
      return
    }
  }

  saving.value = true
  const payload = {
    title: form.title.trim(),
    recruitment_no: form.recruitment_no.trim(),
    start_at: start,
    end_at: end,
    pass_ratio: Number(form.pass_ratio),
    settings: { rules },
  }

  try {
    if (editingId.value === null) {
      await api.createExam(adminSession.token, payload)
      notice.value = '考试草稿已创建'
    } else {
      await api.updateExam(adminSession.token, editingId.value, payload)
      notice.value = '考试已更新'
    }
    showForm.value = false
    await load()
  } catch (err) {
    formError.value = err instanceof ApiError ? err.detail : '保存失败'
  } finally {
    saving.value = false
  }
}

async function onPublish(exam: ExamOut) {
  if (!confirm(`发布「${exam.title}」？发布后将随机抽题生成快照，且名单、组卷、时间全部冻结。`)) return
  error.value = ''
  try {
    const result = await api.publishExam(adminSession.token, exam.id)
    notice.value = `发布成功：抽取 ${result.question_count} 题，总分 ${result.total_score}`
    await load()
  } catch (err) {
    // 标签题量不足时后端会指明具体标签
    error.value = err instanceof ApiError ? err.detail : '发布失败'
  }
}

async function onArchive(exam: ExamOut) {
  if (!confirm(`归档「${exam.title}」？`)) return
  try {
    await api.archiveExam(adminSession.token, exam.id)
    notice.value = '考试已归档'
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '归档失败'
  }
}

async function onDelete(exam: ExamOut) {
  if (!confirm(`删除草稿「${exam.title}」？此操作不可恢复。`)) return
  try {
    await api.deleteExam(adminSession.token, exam.id)
    notice.value = '草稿已删除'
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '删除失败'
  }
}

function openDetail(exam: ExamOut) {
  router.push({ name: 'admin-exam-detail', params: { id: exam.id } })
}

function openPaper(exam: ExamOut) {
  router.push({ name: 'admin-paper-detail', params: { id: exam.id } })
}

/** 名单与邀请码已迁到「考生管理」模块：跳转并预选该场次（CH-007） */
function openCandidates(exam: ExamOut) {
  router.push({ name: 'admin-candidates', query: { exam: String(exam.id) } })
}

const hasFilters = computed(
  () => Object.values(filters.value).some((value) => String(value).trim() !== ''),
)

function resetFilters() {
  filters.value = { status: '', recruitment_no: '', title: '', start_from: '', start_to: '' }
  void load()
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <h2 class="page-title">考试管理</h2>
      <span class="spacer"></span>
      <button class="btn btn-primary" type="button" @click="openCreate">+ 新建考试</button>
    </div>

    <div v-if="error" class="alert alert-error">{{ error }}</div>
    <div v-if="notice" class="alert alert-success">{{ notice }}</div>

    <div class="card query-bar">
      <div class="field">
        <label for="q-status">状态</label>
        <select id="q-status" v-model="filters.status" class="input" @change="load">
          <option value="">全部</option>
          <option value="draft">草稿</option>
          <option value="upcoming">未开始</option>
          <option value="running">进行中</option>
          <option value="ended">已结束</option>
          <option value="archived">已归档</option>
        </select>
      </div>
      <div class="field">
        <label for="q-no">选聘编号</label>
        <input id="q-no" v-model="filters.recruitment_no" class="input" placeholder="包含匹配" @keyup.enter="load" />
      </div>
      <div class="field">
        <label for="q-title">考试名称</label>
        <input id="q-title" v-model="filters.title" class="input" placeholder="模糊匹配" @keyup.enter="load" />
      </div>
      <div class="field">
        <label for="q-from">开考时间（起）</label>
        <input id="q-from" v-model="filters.start_from" class="input" type="date" />
      </div>
      <div class="field">
        <label for="q-to">开考时间（止）</label>
        <input id="q-to" v-model="filters.start_to" class="input" type="date" />
      </div>
      <div class="field query-actions">
        <button class="btn btn-primary" type="button" :disabled="loading" @click="load">查询</button>
        <button v-if="hasFilters" class="btn" type="button" :disabled="loading" @click="resetFilters">
          清除
        </button>
      </div>
    </div>

    <div class="card">
      <div v-if="loading" class="empty">加载中…</div>
      <div v-else-if="exams.length === 0" class="empty">
        <template v-if="hasFilters">
          没有符合查询条件的考试。
          <button class="btn btn-ghost btn-sm" type="button" @click="resetFilters">清除查询条件</button>
        </template>
        <template v-else>暂无考试，请先新建</template>
      </div>
      <table v-else class="table">
        <thead>
          <tr>
            <th>考试名称</th>
            <th style="width: 130px">选聘编号</th>
            <th style="width: 90px">状态</th>
            <th style="width: 150px">开考时间</th>
            <th style="width: 150px">截止时间</th>
            <th style="width: 80px">及格比例</th>
            <th style="width: 260px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="exam in exams" :key="exam.id">
            <td>{{ exam.title }}</td>
            <td class="mono">{{ exam.recruitment_no }}</td>
            <td>
              <span class="status" :class="examStatusClass(exam.external_status)">
                {{ examStatusLabel(exam.external_status) }}
              </span>
            </td>
            <td>{{ formatLocal(exam.start_at) }}</td>
            <td>{{ formatLocal(exam.end_at) }}</td>
            <td>{{ exam.pass_ratio }}%</td>
            <td>
              <template v-if="isDraft(exam.status)">
                <button class="btn btn-ghost btn-sm" type="button" @click="openEdit(exam)">编辑</button>
                <button class="btn btn-ghost btn-sm" type="button" @click="onPublish(exam)">发布</button>
                <button class="btn btn-ghost btn-sm" type="button" @click="openCandidates(exam)">
                  名单与邀请码
                </button>
                <button class="btn btn-ghost btn-sm" type="button" @click="onDelete(exam)">删除</button>
              </template>
              <template v-else>
                <button class="btn btn-ghost btn-sm" type="button" @click="openDetail(exam)">
                  成绩/统计
                </button>
                <button class="btn btn-ghost btn-sm" type="button" @click="openPaper(exam)">
                  查看试卷
                </button>
                <button
                  v-if="exam.status === 'published'"
                  class="btn btn-ghost btn-sm"
                  type="button"
                  @click="onArchive(exam)"
                >
                  归档
                </button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 新建/编辑 -->
    <div v-if="showForm" class="modal-mask" @click.self="showForm = false">
      <div class="modal modal-wide">
        <h3>{{ editingId === null ? '新建考试草稿' : '编辑考试' }}</h3>

        <div v-if="formError" class="alert alert-error">{{ formError }}</div>

        <div class="form-grid">
          <div class="field">
            <label for="e-title">考试名称</label>
            <input id="e-title" v-model.trim="form.title" class="input" placeholder="例如：2026 年安全生产考试" />
          </div>
          <div class="field">
            <label for="e-no">选聘编号（全局唯一）</label>
            <input id="e-no" v-model.trim="form.recruitment_no" class="input" placeholder="例如：ZP2026001" />
          </div>
          <div class="field">
            <label for="e-start">开考时间（本地时间）</label>
            <input id="e-start" v-model="form.start_at" class="input" type="datetime-local" />
          </div>
          <div class="field">
            <label for="e-end">截止时间（本地时间）</label>
            <input id="e-end" v-model="form.end_at" class="input" type="datetime-local" />
          </div>
          <div class="field">
            <label for="e-ratio">及格比例</label>
            <select id="e-ratio" v-model.number="form.pass_ratio" class="input">
              <option v-for="ratio in passRatioOptions" :key="ratio" :value="ratio">
                {{ ratio }}%
              </option>
            </select>
            <p class="field-hint">
              按得分排名取前 <strong>{{ form.pass_ratio }}%</strong> 为及格；
              <strong>同分并列者全部通过</strong>，因此实际及格人数可能多于该比例；
              分母为<strong>已交卷人数</strong>，缺考不计入。
            </p>
          </div>
        </div>

        <div class="field">
          <label>组卷规则（按标签抽题）</label>
          <div class="rules">
            <div v-for="(rule, index) in form.rules" :key="index" class="rule-row">
              <select v-model="rule.tag" class="input rule-tag">
                <option value="">请选择标签</option>
                <option
                  v-for="option in tagOptionsFor(rule.tag)"
                  :key="option.tag"
                  :value="option.tag"
                >
                  {{ option.tag }}（可用 {{ option.question_count }} 题）
                </option>
              </select>
              <input
                v-model.number="rule.count"
                class="input rule-count"
                type="number"
                min="1"
                :max="availableFor(rule.tag) || undefined"
              />
              <span class="muted">题</span>
              <button
                v-if="form.rules.length > 1"
                class="btn btn-ghost btn-sm"
                type="button"
                @click="removeRule(index)"
              >
                删除
              </button>
              <span v-if="ruleOverflow(rule)" class="overflow-hint">
                超出可用 {{ availableFor(rule.tag) }} 题
              </span>
              <span v-else-if="rule.tag && availableFor(rule.tag) === 0" class="overflow-hint">
                题库中该标签暂无题目
              </span>
            </div>
          </div>
          <button class="btn btn-sm" type="button" style="align-self: flex-start; margin-top: 6px" @click="addRule">
            + 添加标签规则
          </button>
          <p class="field-hint">
            标签来自题库中已有标签（先在「题库管理」给题目打标签，这里才会出现）。
            发布时按规则随机抽题；抽题数超过该标签可用题数会发布失败。
          </p>
        </div>

        <div class="modal-actions">
          <button class="btn" type="button" :disabled="saving" @click="showForm = false">取消</button>
          <button class="btn btn-primary" type="button" :disabled="saving" @click="onSave">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 19px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
}

.status {
  display: inline-block;
  padding: 1px 9px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 19px;
}

.status-draft {
  background: #eef2f7;
  color: #475569;
}

.status-upcoming {
  background: var(--c-warning-weak);
  color: #92400e;
}

.status-running {
  background: var(--c-success-weak);
  color: #166534;
}

.status-ended {
  background: #f1f5f9;
  color: #64748b;
}

.status-archived {
  background: #f5f3ff;
  color: #5b21b6;
}

.modal-wide {
  max-width: 680px;
  max-height: 88vh;
  overflow-y: auto;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 14px;
}

.query-bar {
  display: grid;
  grid-template-columns: 130px 160px 1fr 150px 150px auto;
  gap: 12px;
  align-items: end;
  padding: 14px;
  margin-bottom: 14px;
}

.query-bar .field {
  margin-bottom: 0;
}

.query-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

@media (max-width: 1180px) {
  .query-bar {
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  }
}

.rules {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rule-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rule-tag {
  flex: 1;
  min-width: 200px;
}

.rule-count {
  width: 90px;
  flex: none;
}

/* 字段口径说明：让管理员知道"这个数字到底怎么算" */
.field-hint {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--c-text-weak);
}

.field-hint strong {
  color: var(--c-text);
}

.overflow-hint {
  font-size: 12px;
  color: var(--c-danger);
  white-space: nowrap;
}
</style>
