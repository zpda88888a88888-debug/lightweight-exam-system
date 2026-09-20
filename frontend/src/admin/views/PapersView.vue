<script setup lang="ts">
/**
 * 试卷管理（CH-002）：查看每场考试与试卷的对应关系。
 *
 * 规格依据：规格说明 4.8、5.2「试卷管理」
 *
 * 只读列表：显示每场考试的抽题数、试卷总分与状态；草稿没有试卷。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, api } from '@/api/client'
import type { AdminPaper, ExamOut } from '@/api/client'
import { examStatusClass, examStatusLabel } from '@/lib/examStatus'
import { formatLocal } from '@/lib/time'
import { adminSession } from '../session'

const router = useRouter()

const exams = ref<ExamOut[]>([])
const papers = ref<Record<number, AdminPaper | null>>({})
const loading = ref(false)
const error = ref('')

/** 已发布的考试才有试卷 */
const publishedExams = computed(() =>
  exams.value.filter((exam) => exam.status !== 'draft'),
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    exams.value = await api.listExams(adminSession.token)

    // 逐场取试卷概要（题数 / 总分）。数据量级很小，串行足够且便于定位错误。
    const result: Record<number, AdminPaper | null> = {}
    for (const exam of publishedExams.value) {
      try {
        result[exam.id] = await api.getAdminPaper(adminSession.token, exam.id)
      } catch {
        result[exam.id] = null
      }
    }
    papers.value = result
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '加载试卷列表失败'
  } finally {
    loading.value = false
  }
}

function openPaper(exam: ExamOut) {
  router.push({ name: 'admin-paper-detail', params: { id: exam.id } })
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <h2 class="page-title">试卷管理</h2>
      <span class="spacer"></span>
      <button class="btn btn-sm" type="button" :disabled="loading" @click="load">刷新</button>
    </div>

    <div class="alert alert-info">
      试卷是<strong>发布时生成的快照</strong>，发布后不可修改、不可换题。
      这里只做只读查看，用于核对某场考试到底抽了哪些题。
      要调整试卷只能删除考试后重建。
    </div>

    <div v-if="error" class="alert alert-error">{{ error }}</div>

    <div class="card">
      <div v-if="loading" class="empty">加载中…</div>
      <div v-else-if="publishedExams.length === 0" class="empty">
        暂无已发布的考试。请先到「考试管理」创建草稿并发布，发布后才会生成试卷。
      </div>
      <table v-else class="table">
        <thead>
          <tr>
            <th>考试名称</th>
            <th style="width: 150px">选聘编号</th>
            <th style="width: 90px">状态</th>
            <th style="width: 80px">题数</th>
            <th style="width: 90px">试卷总分</th>
            <th style="width: 80px">及格比例</th>
            <th style="width: 150px">开考时间</th>
            <th style="width: 110px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="exam in publishedExams" :key="exam.id">
            <td>{{ exam.title }}</td>
            <td class="mono">{{ exam.recruitment_no }}</td>
            <td>
              <span class="status" :class="examStatusClass(exam.external_status)">
                {{ examStatusLabel(exam.external_status) }}
              </span>
            </td>
            <td>
              <template v-if="papers[exam.id]">{{ papers[exam.id]?.question_count }}</template>
              <span v-else class="muted">—</span>
            </td>
            <td>
              <template v-if="papers[exam.id]">{{ papers[exam.id]?.total_score }}</template>
              <span v-else class="muted">—</span>
            </td>
            <td>{{ exam.pass_ratio }}%</td>
            <td>{{ formatLocal(exam.start_at) }}</td>
            <td>
              <button class="btn btn-ghost btn-sm" type="button" @click="openPaper(exam)">
                查看试卷
              </button>
            </td>
          </tr>
        </tbody>
      </table>
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
</style>
