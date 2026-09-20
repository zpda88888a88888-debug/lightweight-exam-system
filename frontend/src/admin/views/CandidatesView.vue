<script setup lang="ts">
/**
 * 考生管理：按「考试场次」管理名单、邀请码与参与状态。
 *
 * 规格依据：规格说明 5.2「考生管理」、4.6
 *
 * 三个设计要点：
 *   1. 场次选择用「查询 + 可点击结果列表」而不是下拉框（CH-009）：
 *      场次一多下拉框几乎没法用，而且看不到状态与开考时间。
 *   2. 参与状态直接回答"谁在考试、谁没来"（CH-010）：
 *      未登录 / 答题中 / 已交卷 / 超时交卷，并给出各状态人数。
 *   3. 状态人数汇总始终基于**全量名单**，不随筛选变化，
 *      否则"未登录 3 人"会因筛选条件不同而失真。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, api } from '@/api/client'
import type { CandidateRow, ExamOut } from '@/api/client'
import { downloadText, timestampedName } from '@/lib/download'
import { examStatusClass, examStatusLabel, isDraft } from '@/lib/examStatus'
import {
  filterByStatus,
  participationClass,
  participationLabel,
  summarizeParticipation,
  type ParticipationStatus,
} from '@/lib/participation'
import { formatLocal, localDateEndToServer, localDateStartToServer } from '@/lib/time'
import { adminSession } from '../session'

const route = useRoute()
const router = useRouter()

// ---------------- 场次查询（CH-009） ----------------
const examFilters = ref({
  status: '',
  recruitment_no: '',
  title: '',
  start_from: '',
  start_to: '',
})
const examResults = ref<ExamOut[]>([])
const loadingExams = ref(false)
const pickerOpen = ref(true)
const selectedExamId = ref<number | null>(null)

// ---------------- 名单与状态（CH-010） ----------------
const allCandidates = ref<CandidateRow[]>([])
const loadingRoster = ref(false)
const statusFilter = ref<ParticipationStatus | ''>('')

// ---------------- 通用 ----------------
const error = ref('')
const notice = ref('')
const csvText = ref('')
const importing = ref(false)
const importError = ref('')
const showGenerateConfirm = ref(false)
const generating = ref(false)

const selectedExam = computed(
  () => examResults.value.find((exam) => exam.id === selectedExamId.value) ?? null,
)
const draft = computed(() => isDraft(selectedExam.value?.status ?? ''))
const withInviteCode = computed(() => allCandidates.value.filter((row) => row.invite_code).length)
const summary = computed(() => summarizeParticipation(allCandidates.value))
const visibleCandidates = computed(() => filterByStatus(allCandidates.value, statusFilter.value))
const hasExamFilters = computed(
  () => Object.values(examFilters.value).some((value) => String(value).trim() !== ''),
)

/** 状态筛选项带人数，直接回答"谁在考试、谁没来" */
const statusChips = computed(() => {
  const s = summary.value
  return [
    { value: '' as const, label: '全部', count: s.total },
    { value: 'not_started' as const, label: '未登录', count: s.not_started },
    { value: 'in_progress' as const, label: '答题中', count: s.in_progress },
    { value: 'submitted' as const, label: '已交卷', count: s.submitted },
    { value: 'timeout_submitted' as const, label: '超时交卷', count: s.timeout_submitted },
  ]
})

async function loadExams() {
  loadingExams.value = true
  error.value = ''
  try {
    examResults.value = await api.listExams(adminSession.token, {
      status: examFilters.value.status || undefined,
      recruitment_no: examFilters.value.recruitment_no.trim() || undefined,
      title: examFilters.value.title.trim() || undefined,
      start_from: localDateStartToServer(examFilters.value.start_from) || undefined,
      start_to: localDateEndToServer(examFilters.value.start_to) || undefined,
    })
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '加载考试列表失败'
  } finally {
    loadingExams.value = false
  }
}

function resetExamFilters() {
  examFilters.value = { status: '', recruitment_no: '', title: '', start_from: '', start_to: '' }
  void loadExams()
}

async function selectExam(examId: number) {
  selectedExamId.value = examId
  statusFilter.value = ''
  notice.value = ''
  importError.value = ''
  csvText.value = ''
  pickerOpen.value = false
  await router.replace({ query: { exam: String(examId) } })
  await loadRoster()
}

function changeExam() {
  pickerOpen.value = true
}

async function loadRoster() {
  if (selectedExamId.value === null) {
    allCandidates.value = []
    return
  }
  loadingRoster.value = true
  error.value = ''
  try {
    allCandidates.value = await api.listCandidates(adminSession.token, selectedExamId.value)
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '加载名单失败'
    allCandidates.value = []
  } finally {
    loadingRoster.value = false
  }
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    csvText.value = String(reader.result ?? '')
  }
  reader.readAsText(file, 'utf-8')
  input.value = ''
}

async function onImport() {
  importError.value = ''
  notice.value = ''
  if (selectedExamId.value === null) {
    importError.value = '请先选择考试场次'
    return
  }
  if (!csvText.value.trim()) {
    importError.value = '请粘贴 CSV 内容或选择文件'
    return
  }
  importing.value = true
  try {
    const result = await api.importCandidates(
      adminSession.token,
      selectedExamId.value,
      csvText.value,
    )
    notice.value =
      `导入完成：新增考生 ${result.users_created} 人，更新 ${result.users_updated} 人，` +
      `关联到本场名单 ${result.linked} 人`
    csvText.value = ''
    await loadRoster()
  } catch (err) {
    importError.value = err instanceof ApiError ? err.detail : '导入失败'
  } finally {
    importing.value = false
  }
}

async function onGenerate() {
  if (selectedExamId.value === null) return
  generating.value = true
  error.value = ''
  try {
    const result = await api.generateInvites(adminSession.token, selectedExamId.value, true)
    notice.value = `已生成 ${result.generated} 个邀请码（旧码已全部失效，需重新分发）`
    showGenerateConfirm.value = false
    await loadRoster()
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '生成邀请码失败'
    showGenerateConfirm.value = false
  } finally {
    generating.value = false
  }
}

async function exportCodes() {
  if (selectedExamId.value === null) return
  try {
    const csv = await api.exportInviteCodes(adminSession.token, selectedExamId.value)
    const prefix = `邀请码-${selectedExam.value?.recruitment_no ?? selectedExamId.value}`
    downloadText(timestampedName(prefix, 'csv'), csv)
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '导出失败'
  }
}

onMounted(async () => {
  await loadExams()
  // 支持从「考试管理」草稿行带 ?exam=<id> 跳转过来
  const fromQuery = Number(route.query.exam)
  if (Number.isFinite(fromQuery) && examResults.value.some((e) => e.id === fromQuery)) {
    await selectExam(fromQuery)
  }
})
</script>

<template>
  <div>
    <div class="page-head">
      <h2 class="page-title">考生管理</h2>
      <span class="spacer"></span>
      <button class="btn btn-sm" type="button" :disabled="loadingExams" @click="loadExams">
        刷新
      </button>
    </div>

    <div v-if="error" class="alert alert-error">{{ error }}</div>
    <div v-if="notice" class="alert alert-success">{{ notice }}</div>

    <!-- 已选场次（收起态） -->
    <div v-if="selectedExam && !pickerOpen" class="card selected-bar">
      <div class="selected-main">
        <span class="status" :class="examStatusClass(selectedExam.external_status)">
          {{ examStatusLabel(selectedExam.external_status) }}
        </span>
        <strong>{{ selectedExam.title }}</strong>
        <span class="muted mono">{{ selectedExam.recruitment_no }}</span>
        <span class="muted">开考 {{ formatLocal(selectedExam.start_at) }}</span>
      </div>
      <button class="btn btn-sm" type="button" @click="changeExam">更换场次</button>
    </div>

    <!-- 场次查询 + 可点击结果列表（CH-009） -->
    <div v-if="pickerOpen" class="card picker">
      <h3 class="panel-title">选择考试场次</h3>
      <p class="field-hint" style="margin-bottom: 12px">
        场次较多时先用条件筛选，再在结果里点选。查询条件与「考试管理」一致。
      </p>

      <div class="query-bar">
        <div class="field">
          <label for="p-status">状态</label>
          <select id="p-status" v-model="examFilters.status" class="input" @change="loadExams">
            <option value="">全部</option>
            <option value="draft">草稿</option>
            <option value="upcoming">未开始</option>
            <option value="running">进行中</option>
            <option value="ended">已结束</option>
            <option value="archived">已归档</option>
          </select>
        </div>
        <div class="field">
          <label for="p-no">选聘编号</label>
          <input id="p-no" v-model="examFilters.recruitment_no" class="input" placeholder="包含匹配" @keyup.enter="loadExams" />
        </div>
        <div class="field">
          <label for="p-title">考试名称</label>
          <input id="p-title" v-model="examFilters.title" class="input" placeholder="模糊匹配" @keyup.enter="loadExams" />
        </div>
        <div class="field">
          <label for="p-from">开考时间（起）</label>
          <input id="p-from" v-model="examFilters.start_from" class="input" type="date" />
        </div>
        <div class="field">
          <label for="p-to">开考时间（止）</label>
          <input id="p-to" v-model="examFilters.start_to" class="input" type="date" />
        </div>
        <div class="field query-actions">
          <button class="btn btn-primary" type="button" :disabled="loadingExams" @click="loadExams">
            查询
          </button>
          <button v-if="hasExamFilters" class="btn" type="button" :disabled="loadingExams" @click="resetExamFilters">
            清除
          </button>
        </div>
      </div>

      <div class="exam-list">
        <div v-if="loadingExams" class="empty">加载中…</div>
        <div v-else-if="examResults.length === 0" class="empty">
          <template v-if="hasExamFilters">
            没有符合查询条件的考试。
            <button class="btn btn-ghost btn-sm" type="button" @click="resetExamFilters">清除查询条件</button>
          </template>
          <template v-else>还没有任何考试，请先到「考试管理」创建。</template>
        </div>
        <table v-else class="table exam-table">
          <thead>
            <tr>
              <th>考试名称</th>
              <th style="width: 150px">选聘编号</th>
              <th style="width: 90px">状态</th>
              <th style="width: 150px">开考时间</th>
              <th style="width: 90px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="exam in examResults"
              :key="exam.id"
              class="exam-row"
              :class="{ 'is-selected': exam.id === selectedExamId }"
              @click="selectExam(exam.id)"
            >
              <td>{{ exam.title }}</td>
              <td class="mono">{{ exam.recruitment_no }}</td>
              <td>
                <span class="status" :class="examStatusClass(exam.external_status)">
                  {{ examStatusLabel(exam.external_status) }}
                </span>
              </td>
              <td>{{ formatLocal(exam.start_at) }}</td>
              <td>
                <button class="btn btn-ghost btn-sm" type="button" @click.stop="selectExam(exam.id)">
                  {{ exam.id === selectedExamId ? '已选' : '选择' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <template v-if="selectedExam && !pickerOpen">
      <div v-if="!draft" class="alert alert-warning">
        该场考试<strong>已发布</strong>，名单与邀请码已冻结，不可再修改。
        成绩与统计请到「考试管理 → 成绩/统计」查看。
      </div>

      <!-- 参与状态汇总（CH-010） -->
      <div class="card panel">
        <div class="panel-head">
          <h3 class="panel-title">参与状态</h3>
          <span class="spacer"></span>
          <span class="muted summary-text">
            名单 {{ summary.total }} 人 · 已产生成绩 {{ summary.finished }} 人 ·
            未登录 {{ summary.not_started }} 人
          </span>
        </div>
        <div class="chips">
          <button
            v-for="chip in statusChips"
            :key="chip.value || 'all'"
            class="chip"
            :class="{ 'chip-active': statusFilter === chip.value }"
            type="button"
            @click="statusFilter = chip.value"
          >
            {{ chip.label }}
            <span class="chip-count">{{ chip.count }}</span>
          </button>
        </div>
      </div>

      <!-- 导入名单 -->
      <div v-if="draft" class="card panel">
        <h3 class="panel-title">导入考生名单</h3>
        <p class="field-hint" style="margin-bottom: 10px">
          CSV 表头必须为 <code>手机号,姓名,身份证号</code>。身份证号全局唯一，
          重复导入会更新已有考生的姓名与手机号（同一人参加多场考试时复用同一档案）。
        </p>
        <div v-if="importError" class="alert alert-error">{{ importError }}</div>
        <input type="file" accept=".csv,text/csv" @change="onFileChange" />
        <textarea
          v-model="csvText"
          class="input code-area"
          rows="5"
          placeholder="手机号,姓名,身份证号&#10;13800000001,张三,110101199001010011"
        ></textarea>
        <button class="btn btn-primary" type="button" :disabled="importing" @click="onImport">
          {{ importing ? '导入中…' : '导入到本场考试' }}
        </button>
      </div>

      <!-- 名单与邀请码 -->
      <div class="card panel">
        <div class="panel-head">
          <h3 class="panel-title">名单与邀请码</h3>
          <span class="spacer"></span>
          <button
            class="btn btn-sm"
            type="button"
            :disabled="allCandidates.length === 0"
            @click="exportCodes"
          >
            导出邀请码 CSV
          </button>
          <button
            v-if="draft"
            class="btn btn-sm btn-primary"
            type="button"
            :disabled="allCandidates.length === 0"
            @click="showGenerateConfirm = true"
          >
            {{ withInviteCode > 0 ? '重新生成邀请码' : '生成邀请码' }}
          </button>
        </div>

        <div v-if="loadingRoster" class="empty">加载中…</div>
        <div v-else-if="allCandidates.length === 0" class="empty">
          本场还没有名单。请在上方导入考生 CSV。
        </div>
        <div v-else-if="visibleCandidates.length === 0" class="empty">
          没有该状态的考生。
          <button class="btn btn-ghost btn-sm" type="button" @click="statusFilter = ''">查看全部</button>
        </div>
        <table v-else class="table">
          <thead>
            <tr>
              <th style="width: 48px">#</th>
              <th>姓名</th>
              <th>手机号</th>
              <th>身份证号</th>
              <th style="width: 110px">邀请码</th>
              <th style="width: 100px">状态</th>
              <th style="width: 80px">得分</th>
              <th style="width: 150px">交卷时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in visibleCandidates" :key="row.user_id">
              <td class="muted">{{ index + 1 }}</td>
              <td>{{ row.name }}</td>
              <td class="mono">{{ row.phone }}</td>
              <td class="mono">{{ row.id_card }}</td>
              <td>
                <span v-if="row.invite_code" class="code-cell">{{ row.invite_code }}</span>
                <span v-else class="muted">未生成</span>
              </td>
              <td>
                <span class="p-status" :class="participationClass(row.status)">
                  {{ participationLabel(row.status) }}
                </span>
              </td>
              <td>{{ row.score ?? '—' }}</td>
              <td>{{ row.submitted_at ? formatLocal(row.submitted_at) : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- 生成邀请码二次确认 -->
    <div v-if="showGenerateConfirm" class="modal-mask" @click.self="showGenerateConfirm = false">
      <div class="modal">
        <h3>{{ withInviteCode > 0 ? '重新生成邀请码' : '生成邀请码' }}</h3>
        <p>
          将为「{{ selectedExam?.title }}」名单中的 <strong>{{ allCandidates.length }}</strong>
          名考生生成全局唯一的 6 位数字邀请码。
        </p>
        <p v-if="withInviteCode > 0" class="alert alert-warning" style="margin-bottom: 0">
          重新生成会<strong>覆盖全部邀请码</strong>，旧码立即失效，已分发的邀请码需重新发放。
        </p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="showGenerateConfirm = false">取消</button>
          <button class="btn btn-primary" type="button" :disabled="generating" @click="onGenerate">
            {{ generating ? '生成中…' : '确认生成' }}
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

/* ---- 已选场次栏 ---- */
.selected-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.selected-main {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
  font-size: 13px;
  flex-wrap: wrap;
}

/* ---- 场次查询 ---- */
.picker {
  padding: 16px;
  margin-bottom: 14px;
}

.panel-title {
  margin: 0;
  font-size: 15px;
}

.query-bar {
  display: grid;
  grid-template-columns: 130px 160px 1fr 150px 150px auto;
  gap: 12px;
  align-items: end;
  margin-bottom: 12px;
}

.query-bar .field {
  margin-bottom: 0;
}

.query-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.exam-list {
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
}

.exam-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
}

.exam-row {
  cursor: pointer;
}

.exam-row:hover {
  background: #fafbfc;
}

.exam-row.is-selected {
  background: var(--c-primary-weak);
}

.exam-row.is-selected td:first-child {
  font-weight: 600;
}

/* ---- 名单与状态 ---- */
.panel {
  padding: 16px;
  margin-bottom: 14px;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.summary-text {
  font-size: 13px;
}

.chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  background: var(--c-surface);
  font-size: 13px;
  color: var(--c-text);
}

.chip:hover {
  border-color: var(--c-primary);
}

.chip-active {
  background: var(--c-primary);
  border-color: var(--c-primary);
  color: #fff;
  font-weight: 600;
}

.chip-count {
  font-variant-numeric: tabular-nums;
  opacity: 0.75;
}

.p-status {
  display: inline-block;
  padding: 1px 9px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 19px;
  white-space: nowrap;
}

.p-not-started {
  background: #f1f5f9;
  color: #64748b;
}

.p-in-progress {
  background: var(--c-warning-weak);
  color: #92400e;
}

.p-submitted {
  background: var(--c-success-weak);
  color: #166534;
}

.p-timeout {
  background: #fef2f2;
  color: #991b1b;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
}

.code-area {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px;
  margin: 10px 0;
}

.code-cell {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 600;
  letter-spacing: 1px;
}

.field-hint {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--c-text-weak);
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

@media (max-width: 1180px) {
  .query-bar {
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  }
}
</style>
