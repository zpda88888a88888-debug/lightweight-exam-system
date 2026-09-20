<script setup lang="ts">
/**
 * 试卷详情（CH-002）：某场考试抽中的题目清单，只读。
 *
 * 规格依据：规格说明 4.8、5.2「试卷管理」
 *   - 显示序号、题型、题干、选项、正确答案、本题分值；
 *   - 不提供任何改题/换题入口（发布即冻结）。
 */
import { computed, onMounted, ref } from 'vue'

import { ApiError, api } from '@/api/client'
import type { AdminPaper } from '@/api/client'
import { examStatusClass, examStatusLabel } from '@/lib/examStatus'
import { typeLabel } from '@/lib/questionTypes'
import { formatLocal } from '@/lib/time'
import { adminSession } from '../session'

const props = defineProps<{ id: string }>()

const paper = ref<AdminPaper | null>(null)
const loading = ref(false)
const error = ref('')

const examId = computed(() => Number(props.id))

async function load() {
  loading.value = true
  error.value = ''
  try {
    paper.value = await api.getAdminPaper(adminSession.token, examId.value)
  } catch (err) {
    // 草稿状态会返回 409「该考试尚未发布，暂无试卷」
    error.value = err instanceof ApiError ? err.detail : '加载试卷失败'
    paper.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <router-link class="btn btn-sm" :to="{ name: 'admin-papers' }">← 返回试卷管理</router-link>
      <h2 class="page-title">{{ paper?.exam.title ?? '试卷详情' }}</h2>
      <span v-if="paper" class="status" :class="examStatusClass(paper.exam.external_status)">
        {{ examStatusLabel(paper.exam.external_status) }}
      </span>
      <span class="spacer"></span>
      <span class="tag">只读</span>
    </div>

    <div v-if="error" class="alert alert-error">{{ error }}</div>
    <div v-if="loading" class="card empty">加载中…</div>

    <template v-if="paper">
      <div class="card meta-card">
        <div><span class="muted">选聘编号</span><strong class="mono">{{ paper.exam.recruitment_no }}</strong></div>
        <div><span class="muted">开考时间</span><strong>{{ formatLocal(paper.exam.start_at) }}</strong></div>
        <div><span class="muted">截止时间</span><strong>{{ formatLocal(paper.exam.end_at) }}</strong></div>
        <div><span class="muted">及格比例</span><strong>{{ paper.exam.pass_ratio }}%</strong></div>
        <div><span class="muted">题数</span><strong>{{ paper.question_count }}</strong></div>
        <div><span class="muted">试卷总分</span><strong>{{ paper.total_score }}</strong></div>
      </div>

      <div class="alert alert-info">
        本试卷共 <strong>{{ paper.question_count }}</strong> 道题，总分
        <strong>{{ paper.total_score }}</strong> 分。题目顺序在发布时随机固定；
        考生端的选项内容会按各自账号乱序，但这里显示的是题库原始顺序与正确答案。
      </div>

      <div v-if="paper.questions.length === 0" class="card empty">该试卷没有任何题目。</div>

      <section
        v-for="question in paper.questions"
        :key="question.question_id"
        class="card question"
      >
        <div class="question-head">
          <span class="question-no">{{ question.seq + 1 }}</span>
          <span class="tag">{{ typeLabel(question.type) }}</span>
          <span class="tag tag-score">{{ question.score }} 分</span>
          <span class="spacer"></span>
          <span class="muted mono">#{{ question.question_id }}</span>
        </div>

        <p class="question-stem">{{ question.stem }}</p>

        <ul class="options">
          <li
            v-for="option in question.options"
            :key="option.key"
            class="option"
            :class="{ 'is-correct': question.answer.includes(option.key) }"
          >
            <span class="option-key">{{ option.key }}</span>
            <span class="option-text">{{ option.text }}</span>
            <span v-if="question.answer.includes(option.key)" class="correct-mark">✓ 正确答案</span>
          </li>
        </ul>

        <p v-if="question.analysis" class="analysis">
          <span class="muted">解析：</span>{{ question.analysis }}
        </p>
      </section>
    </template>
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

.meta-card {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  padding: 14px 16px;
  margin-bottom: 14px;
}

.meta-card > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
}

.question {
  padding: 16px;
  margin-bottom: 12px;
}

.question-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.question-no {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--c-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
}

.tag-score {
  background: var(--c-primary-weak);
  color: #1e40af;
}

.question-stem {
  margin: 0 0 12px;
  font-size: 15px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.options {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.option {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  font-size: 14px;
}

.option.is-correct {
  border-color: #86efac;
  background: var(--c-success-weak);
}

.option-key {
  flex: none;
  font-weight: 600;
  min-width: 16px;
}

.option-text {
  flex: 1;
  word-break: break-word;
}

.correct-mark {
  flex: none;
  font-size: 12px;
  color: var(--c-success);
  font-weight: 600;
}

.analysis {
  margin: 12px 0 0;
  font-size: 13px;
  line-height: 1.6;
  padding-top: 10px;
  border-top: 1px dashed var(--c-border);
}
</style>
