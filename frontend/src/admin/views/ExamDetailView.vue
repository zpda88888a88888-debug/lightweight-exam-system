<script setup lang="ts">
/**
 * 考试详情：成绩与统计。
 *
 * 规格依据：规格说明 4.7、5.2「成绩与统计」
 *   - 平均分、及格率、题目标错率图表（ECharts）；
 *   - 成绩列表与 CSV 导出（含缺考）。
 *
 * 注意：**名单与邀请码已迁到「考生管理」模块**（CH-007），
 * 本页不再承担发布前的名单维护职责，避免同一功能两处入口。
 */
import { computed, onMounted, ref } from 'vue'

import { ApiError, api } from '@/api/client'
import type { ExamOut, ResultRow, StatsResponse } from '@/api/client'
import { downloadText, timestampedName } from '@/lib/download'
import { examStatusClass, examStatusLabel } from '@/lib/examStatus'
import { formatLocal } from '@/lib/time'
import { adminSession } from '../session'
import StatChart from '../components/StatChart.vue'

const props = defineProps<{ id: string }>()

const exam = ref<ExamOut | null>(null)
const loading = ref(false)
const error = ref('')
const notice = ref('')



const stats = ref<StatsResponse | null>(null)
const results = ref<ResultRow[]>([])
const statsLoading = ref(false)


const examId = computed(() => Number(props.id))

/** 题目标错率柱状图 */
const wrongRateOption = computed(() => {
  const rows = stats.value?.questions ?? []
  return {
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${v}%` },
    grid: { left: 48, right: 20, top: 30, bottom: 40 },
    xAxis: {
      type: 'category',
      data: rows.map((_, index) => `第${index + 1}题`),
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      {
        name: '标错率',
        type: 'bar',
        data: rows.map((r) => Math.round(r.wrong_rate * 1000) / 10),
        itemStyle: { color: '#2563eb', borderRadius: [4, 4, 0, 0] },
        barMaxWidth: 38,
      },
    ],
  }
})

/** 及格情况饼图 */
const passPieOption = computed(() => {
  const s = stats.value
  const passed = s?.pass_count ?? 0
  const attend = s?.attempt_count ?? 0
  const failed = Math.max(0, attend - passed)
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [
      {
        name: '及格情况',
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '44%'],
        data: [
          { value: passed, name: '及格', itemStyle: { color: '#16a34a' } },
          { value: failed, name: '不及格', itemStyle: { color: '#dc2626' } },
        ],
        label: { formatter: '{b} {c} 人' },
      },
    ],
  }
})

async function loadExam() {
  const list = await api.listExams(adminSession.token)
  const found = list.find((item) => item.id === examId.value)
  if (!found) {
    error.value = '考试不存在'
    return
  }
  exam.value = found
}

async function loadStats() {
  statsLoading.value = true
  try {
    const [statsData, resultsData] = await Promise.all([
      api.getStats(adminSession.token, examId.value),
      api.getResults(adminSession.token, examId.value),
    ])
    stats.value = statsData
    results.value = resultsData.rows
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '加载成绩失败'
  } finally {
    statsLoading.value = false
  }
}

async function exportResults() {
  try {
    const csv = await api.exportResults(adminSession.token, examId.value)
    downloadText(timestampedName(`成绩-${exam.value?.recruitment_no ?? examId.value}`, 'csv'), csv)
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '导出失败'
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await loadExam()
    await loadStats()
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <div class="page-head">
      <router-link class="btn btn-sm" :to="{ name: 'admin-exams' }">← 返回</router-link>
      <h2 class="page-title">{{ exam?.title ?? '考试详情' }}</h2>
      <span v-if="exam" class="status" :class="examStatusClass(exam.external_status)">
        {{ examStatusLabel(exam.external_status) }}
      </span>
      <span class="spacer"></span>
      <span v-if="exam" class="muted mono">{{ exam.recruitment_no }}</span>
    </div>

    <div v-if="error" class="alert alert-error">{{ error }}</div>
    <div v-if="notice" class="alert alert-success">{{ notice }}</div>

    <div v-if="exam" class="card meta-card">
      <div><span class="muted">开考时间</span><strong>{{ formatLocal(exam.start_at) }}</strong></div>
      <div><span class="muted">截止时间</span><strong>{{ formatLocal(exam.end_at) }}</strong></div>
      <div><span class="muted">及格比例</span><strong>{{ exam.pass_ratio }}%</strong></div>
      <div>
        <span class="muted">组卷规则</span>
        <strong>
          {{
            exam.settings.rules.length
              ? exam.settings.rules.map((r) => `${r.tag}×${r.count}`).join('，')
              : '—'
          }}
        </strong>
      </div>
    </div>

    <h3 class="section-title">成绩与统计</h3>

    <!-- ---------------- 成绩与统计 ---------------- -->
    <div class="stack">
      <div v-if="statsLoading" class="card empty">加载中…</div>

      <template v-else-if="stats">
        <div class="stat-cards">
          <div class="card stat-card">
            <div class="stat-label">名单人数</div>
            <div class="stat-value">{{ stats.total_candidates }}</div>
          </div>
          <div class="card stat-card">
            <div class="stat-label">有 attempt</div>
            <div class="stat-value">{{ stats.attempt_count }}</div>
          </div>
          <div class="card stat-card">
            <div class="stat-label">缺考</div>
            <div class="stat-value">{{ stats.absent_count }}</div>
          </div>
          <div class="card stat-card">
            <div class="stat-label">平均分</div>
            <div class="stat-value">{{ stats.average_score }}</div>
          </div>
          <div class="card stat-card">
            <div class="stat-label">及格线</div>
            <div class="stat-value">{{ stats.pass_line ?? '—' }}</div>
          </div>
          <div class="card stat-card">
            <div class="stat-label">及格率</div>
            <div class="stat-value">{{ Math.round(stats.pass_rate * 1000) / 10 }}%</div>
          </div>
        </div>

        <div class="charts">
          <div class="card panel">
            <h3 class="panel-title">题目标错率</h3>
            <StatChart :option="wrongRateOption" height="280px" />
          </div>
          <div class="card panel">
            <h3 class="panel-title">及格情况</h3>
            <StatChart :option="passPieOption" height="280px" />
          </div>
        </div>

        <div class="card panel">
          <div class="panel-head">
            <h3 class="panel-title">成绩列表</h3>
            <span class="spacer"></span>
            <button class="btn btn-sm btn-primary" type="button" @click="exportResults">
              导出成绩 CSV
            </button>
          </div>
          <div class="table-scroll">
            <table v-if="results.length" class="table">
              <thead>
                <tr>
                  <th style="width: 50px">#</th>
                  <th>姓名</th>
                  <th>手机号</th>
                  <th style="width: 80px">得分</th>
                  <th style="width: 80px">是否及格</th>
                  <th style="width: 90px">切屏次数</th>
                  <th style="width: 110px">状态</th>
                  <th style="width: 160px">交卷时间</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in results" :key="row.id_card + index">
                  <td class="muted">{{ index + 1 }}</td>
                  <td>{{ row.name }}</td>
                  <td class="mono">{{ row.phone }}</td>
                  <td>{{ row.score ?? '—' }}</td>
                  <td>
                    <span v-if="row.status === '缺考'" class="muted">—</span>
                    <span v-else :class="row.is_pass ? 'pass-yes' : 'pass-no'">
                      {{ row.is_pass ? '是' : '否' }}
                    </span>
                  </td>
                  <td>{{ row.switch_count }}</td>
                  <td>{{ row.status }}</td>
                  <td>{{ row.submitted_at ? formatLocal(row.submitted_at) : '—' }}</td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty">暂无成绩数据</div>
          </div>
        </div>
      </template>
    </div>

  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.page-title {
  margin: 0;
  font-size: 19px;
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

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
}

.meta-card {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  padding: 14px 16px;
  margin-bottom: 16px;
}

.meta-card > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
}

.tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--c-border);
}

.tab {
  padding: 9px 16px;
  border: none;
  background: transparent;
  color: var(--c-text-weak);
  font-weight: 500;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}

.tab-active {
  color: var(--c-primary);
  border-bottom-color: var(--c-primary);
}

.panel {
  padding: 16px;
}

.panel-title {
  margin: 0;
  font-size: 15px;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.panel-head .panel-title {
  margin: 0;
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

.stat-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}

.stat-card {
  padding: 14px 16px;
}

.stat-label {
  font-size: 12.5px;
  color: var(--c-text-weak);
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  margin-top: 2px;
}

.charts {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 12px;
}

.table-scroll {
  overflow-x: auto;
}

.pass-yes {
  color: var(--c-success);
  font-weight: 600;
}

.pass-no {
  color: var(--c-danger);
}

@media (max-width: 980px) {
  .charts {
    grid-template-columns: 1fr;
  }
}
</style>
