<script setup lang="ts">
/**
 * 题库管理：列表（按题型/标签/关键词筛选）、单题增删改、JSON 批量导入。
 */
import { computed, onMounted, ref } from 'vue'

import { ApiError, api } from '@/api/client'
import type { QuestionOut } from '@/api/client'
import { downloadText, timestampedName } from '@/lib/download'
import { typeLabel } from '@/lib/questionTypes'
import { formatLocal } from '@/lib/time'
import { adminSession } from '../session'
import QuestionForm from '../components/QuestionForm.vue'

const questions = ref<QuestionOut[]>([])
const loading = ref(false)
const error = ref('')
const notice = ref('')

const filterType = ref('')
const filterTag = ref('')
const filterKeyword = ref('')

const showForm = ref(false)
const editing = ref<QuestionOut | null>(null)
const saving = ref(false)

const showImport = ref(false)
const importText = ref('')
const importing = ref(false)
const importError = ref('')

const editingInitial = computed(() =>
  editing.value
    ? {
        type: editing.value.type,
        stem: editing.value.stem,
        options: editing.value.options,
        answer: editing.value.answer,
        score: editing.value.score,
        tags: editing.value.tags.join(', '),
        analysis: editing.value.analysis,
      }
    : null,
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    questions.value = await api.listQuestions(adminSession.token, {
      type: filterType.value || undefined,
      tag: filterTag.value || undefined,
      keyword: filterKeyword.value || undefined,
    })
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '加载题库失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  showForm.value = true
}

function openEdit(question: QuestionOut) {
  editing.value = question
  showForm.value = true
}

async function onSubmit(payload: Parameters<typeof api.createQuestion>[1]) {
  saving.value = true
  error.value = ''
  try {
    if (editing.value) {
      await api.updateQuestion(adminSession.token, editing.value.id, payload)
      notice.value = '题目已更新'
    } else {
      await api.createQuestion(adminSession.token, payload)
      notice.value = '题目已新增'
    }
    showForm.value = false
    editing.value = null
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '保存失败'
  } finally {
    saving.value = false
  }
}

async function onDelete(question: QuestionOut) {
  if (!confirm(`确定删除题目 #${question.id}？`)) return
  error.value = ''
  try {
    await api.deleteQuestion(adminSession.token, question.id)
    notice.value = '题目已删除'
    await load()
  } catch (err) {
    // 已被已发布考试引用的题目会被后端拒绝（架构 9.6）
    error.value = err instanceof ApiError ? err.detail : '删除失败'
  }
}

/** 累计正确率展示（CH-008）：从未被作答时显示「暂无」而不是 0% */
function correctRateText(question: QuestionOut): string {
  const rate = question.stats?.correct_rate
  if (rate === null || rate === undefined) return '暂无'
  return `${Math.round(rate * 1000) / 10}%`
}

/** 样本量：显示"对/总"，让管理员知道正确率背后的样本有多大 */
function sampleText(question: QuestionOut): string {
  const stats = question.stats
  if (!stats || stats.answer_count === 0) return ''
  return `${stats.correct_count}/${stats.answer_count}`
}

/** 上次被抽中的考试与时间；从未被抽中时显示「暂无」 */
function lastDrawnText(question: QuestionOut): string {
  const stats = question.stats
  if (!stats?.last_drawn_exam_title) return '暂无'
  return stats.last_drawn_exam_title
}

/** 导出题库 CSV（CH-011）：便于备份与线下审校 */
async function exportQuestions() {
  error.value = ''
  try {
    const csv = await api.exportQuestions(adminSession.token)
    downloadText(timestampedName('题库', 'csv'), csv)
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '导出题库失败'
  }
}

function openImport() {
  importText.value = ''
  importError.value = ''
  showImport.value = true
}

async function onImport() {
  importError.value = ''
  let parsed: unknown
  try {
    parsed = JSON.parse(importText.value)
  } catch {
    importError.value = 'JSON 解析失败，请检查格式'
    return
  }

  const list = Array.isArray(parsed) ? parsed : (parsed as { questions?: unknown[] }).questions
  if (!Array.isArray(list) || list.length === 0) {
    importError.value = '需要提供题目数组，或 {"questions": [...]} 结构'
    return
  }

  importing.value = true
  try {
    const result = await api.importQuestions(adminSession.token, list)
    showImport.value = false
    notice.value = `导入完成：新增 ${result.created} 题，更新 ${result.updated} 题`
    await load()
  } catch (err) {
    importError.value = err instanceof ApiError ? err.detail : '导入失败'
  } finally {
    importing.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <h2 class="page-title">题库管理</h2>
      <span class="spacer"></span>
      <button class="btn" type="button" @click="exportQuestions">导出题库 CSV</button>
      <button class="btn" type="button" @click="openImport">JSON 批量导入</button>
      <button class="btn btn-primary" type="button" @click="openCreate">+ 新增题目</button>
    </div>

    <div v-if="error" class="alert alert-error">{{ error }}</div>
    <div v-if="notice" class="alert alert-success">{{ notice }}</div>

    <div class="card filters">
      <div class="field">
        <label for="f-type">题型</label>
        <select id="f-type" v-model="filterType" class="input">
          <option value="">全部</option>
          <option value="single">单选题</option>
          <option value="multi">多选题</option>
          <option value="judge">判断题</option>
        </select>
      </div>
      <div class="field">
        <label for="f-tag">标签</label>
        <input id="f-tag" v-model.trim="filterTag" class="input" placeholder="精确匹配标签" />
      </div>
      <div class="field">
        <label for="f-keyword">关键词</label>
        <input id="f-keyword" v-model.trim="filterKeyword" class="input" placeholder="题干包含" @keyup.enter="load" />
      </div>
      <div class="field filter-action">
        <button class="btn btn-primary" type="button" :disabled="loading" @click="load">查询</button>
      </div>
    </div>

    <div class="card">
      <div v-if="loading" class="empty">加载中…</div>
      <div v-else-if="questions.length === 0" class="empty">暂无题目，请先新增或批量导入</div>
      <table v-else class="table">
        <thead>
          <tr>
            <th style="width: 60px">ID</th>
            <th style="width: 84px">题型</th>
            <th>题干</th>
            <th style="width: 160px">标签</th>
            <th style="width: 70px">分值</th>
            <th style="width: 90px">答案</th>
            <th style="width: 190px">上次被抽中</th>
            <th style="width: 130px">累计正确率</th>
            <th style="width: 120px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="question in questions" :key="question.id">
            <td class="muted">{{ question.id }}</td>
            <td>{{ typeLabel(question.type) }}</td>
            <td class="stem-cell">{{ question.stem }}</td>
            <td>
              <span v-for="tag in question.tags" :key="tag" class="tag" style="margin-right: 4px">
                {{ tag }}
              </span>
            </td>
            <td>{{ question.score }}</td>
            <td>{{ question.answer.join('') }}</td>
            <td>
              <div v-if="question.stats?.last_drawn_exam_title" class="drawn-cell">
                <span class="drawn-exam">{{ lastDrawnText(question) }}</span>
                <span class="muted drawn-time">{{ formatLocal(question.stats.last_drawn_at) }}</span>
              </div>
              <span v-else class="muted">暂无（未被抽中）</span>
            </td>
            <td>
              <span :class="{ 'rate-value': question.stats?.correct_rate != null }">
                {{ correctRateText(question) }}
              </span>
              <span v-if="sampleText(question)" class="muted rate-sample">
                （{{ sampleText(question) }}）
              </span>
            </td>
            <td>
              <button class="btn btn-ghost btn-sm" type="button" @click="openEdit(question)">编辑</button>
              <button class="btn btn-ghost btn-sm" type="button" @click="onDelete(question)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 新增/编辑 -->
    <div v-if="showForm" class="modal-mask" @click.self="showForm = false">
      <div class="modal modal-wide">
        <h3>{{ editing ? `编辑题目 #${editing.id}` : '新增题目' }}</h3>
        <QuestionForm :initial="editingInitial" :submitting="saving" @submit="onSubmit" @cancel="showForm = false" />
      </div>
    </div>

    <!-- 批量导入 -->
    <div v-if="showImport" class="modal-mask" @click.self="showImport = false">
      <div class="modal modal-wide">
        <h3>JSON 批量导入</h3>
        <p class="muted" style="font-size: 13px">
          按 <code>id</code> upsert：带 id 且已存在则更新，否则新增。示例：
        </p>
        <pre class="code-sample">[
  {
    "id": 1,
    "type": "single",
    "stem": "题干",
    "options": [{"key": "A", "text": "选项A"}, {"key": "B", "text": "选项B"}],
    "answer": ["A"],
    "score": 5,
    "tags": ["标签A"],
    "analysis": "解析"
  }
]</pre>
        <div v-if="importError" class="alert alert-error">{{ importError }}</div>
        <textarea v-model="importText" class="input code-area" rows="10" placeholder="粘贴 JSON 数组"></textarea>
        <div class="modal-actions">
          <button class="btn" type="button" @click="showImport = false">取消</button>
          <button class="btn btn-primary" type="button" :disabled="importing" @click="onImport">
            {{ importing ? '导入中…' : '开始导入' }}
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

.filters {
  display: grid;
  grid-template-columns: 160px 200px 1fr 90px;
  gap: 12px;
  padding: 14px;
  margin-bottom: 16px;
  align-items: end;
}

.filters .field {
  margin-bottom: 0;
}

.filter-action {
  justify-content: flex-end;
}

.drawn-cell {
  display: flex;
  flex-direction: column;
  line-height: 1.35;
}

.drawn-exam {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 180px;
}

.drawn-time {
  font-size: 11.5px;
}

.rate-value {
  font-weight: 600;
}

.rate-sample {
  font-size: 11.5px;
}

.stem-cell {
  max-width: 380px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modal-wide {
  max-width: 720px;
  max-height: 88vh;
  overflow-y: auto;
}

.code-sample {
  background: #0f172a;
  color: #e2e8f0;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 12px;
  overflow-x: auto;
}

.code-area {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px;
}
</style>
