<script setup lang="ts">
/**
 * 题目编辑表单（新增/编辑共用）。
 * 校验规则与后端一致：单选/判断必须且仅有 1 个正确答案，多选至少 1 个。
 */
import { computed, reactive, ref, watch } from 'vue'

import type { Option, QuestionType } from '@/api/client'
import { JUDGE_OPTIONS } from '@/lib/questionTypes'

export interface QuestionFormModel {
  type: QuestionType
  stem: string
  options: Option[]
  answer: string[]
  score: number
  tags: string
  analysis: string
}

const props = defineProps<{
  initial?: Partial<QuestionFormModel> | null
  submitting?: boolean
}>()

const emit = defineEmits<{
  submit: [payload: {
    type: QuestionType
    stem: string
    options: Option[]
    answer: string[]
    score: number
    tags: string[]
    analysis: string
  }]
  cancel: []
}>()

function emptyForm(): QuestionFormModel {
  return {
    type: 'single',
    stem: '',
    options: [
      { key: 'A', text: '' },
      { key: 'B', text: '' },
      { key: 'C', text: '' },
      { key: 'D', text: '' },
    ],
    answer: [],
    score: 5,
    tags: '',
    analysis: '',
  }
}

const form = reactive<QuestionFormModel>(emptyForm())
const error = ref('')

function reset() {
  Object.assign(form, emptyForm())
  const init = props.initial
  if (init) {
    if (init.type) form.type = init.type
    if (init.stem !== undefined) form.stem = init.stem
    if (init.options) form.options = init.options.map((o) => ({ ...o }))
    if (init.answer) form.answer = [...init.answer]
    if (init.score !== undefined) form.score = init.score
    if (init.tags !== undefined) form.tags = init.tags
    if (init.analysis !== undefined) form.analysis = init.analysis
  }
  if (form.type === 'judge' && form.options.length === 0) {
    form.options = JUDGE_OPTIONS.map((o) => ({ ...o }))
  }
  error.value = ''
}

watch(() => props.initial, reset, { immediate: true })

/** 判断题选项固定，不可编辑 */
const optionsLocked = computed(() => form.type === 'judge')
const multi = computed(() => form.type === 'multi')

function onTypeChange() {
  form.answer = []
  if (form.type === 'judge') {
    form.options = JUDGE_OPTIONS.map((o) => ({ ...o }))
  }
}

function addOption() {
  const used = form.options.map((o) => o.key)
  const nextKey = 'ABCDEFGH'.split('').find((k) => !used.includes(k))
  if (!nextKey) return
  form.options.push({ key: nextKey, text: '' })
}

function removeOption(index: number) {
  const removed = form.options[index]
  form.options.splice(index, 1)
  form.answer = form.answer.filter((key) => key !== removed.key)
}

function toggleAnswer(key: string) {
  if (multi.value) {
    form.answer = form.answer.includes(key)
      ? form.answer.filter((item) => item !== key)
      : [...form.answer, key]
  } else {
    form.answer = [key]
  }
}

function onSubmit() {
  error.value = ''

  // 默认给出 4 个选项，但大多题目只有 2~4 个：
  // 提交时自动丢弃「内容为空」的选项，而不是强迫管理员逐个删空行。
  const emptyKeys = form.options.filter((o) => !o.text.trim()).map((o) => o.key)
  const keptOptions = form.options.filter((o) => o.text.trim())

  if (!form.stem.trim()) {
    error.value = '请填写题干'
    return
  }
  if (keptOptions.length === 0) {
    error.value = '请至少填写一个选项内容'
    return
  }

  const answerOnEmpty = form.answer.filter((key) => emptyKeys.includes(key))
  if (answerOnEmpty.length > 0) {
    error.value = `正确答案 ${answerOnEmpty.join('、')} 对应的选项内容为空，请填写或改选`
    return
  }

  const answer = form.answer.filter((key) => !emptyKeys.includes(key))
  if (answer.length === 0) {
    error.value = '请选择正确答案'
    return
  }
  if (!multi.value && answer.length !== 1) {
    error.value = '单选题/判断题必须且只能有 1 个正确答案'
    return
  }
  if (!(form.score > 0)) {
    error.value = '分值必须大于 0'
    return
  }

  emit('submit', {
    type: form.type,
    stem: form.stem.trim(),
    options: keptOptions.map((o) => ({ key: o.key, text: o.text.trim() })),
    answer,
    score: Number(form.score),
    tags: form.tags
      .split(/[,，\s]+/)
      .map((t) => t.trim())
      .filter(Boolean),
    analysis: form.analysis,
  })
}
</script>

<template>
  <form class="qform" @submit.prevent="onSubmit">
    <div v-if="error" class="alert alert-error">{{ error }}</div>

    <div class="qform-grid">
      <div class="field">
        <label for="q-type">题型</label>
        <select id="q-type" v-model="form.type" class="input" @change="onTypeChange">
          <option value="single">单选题</option>
          <option value="multi">多选题</option>
          <option value="judge">判断题</option>
        </select>
      </div>

      <div class="field">
        <label for="q-score">分值</label>
        <input id="q-score" v-model.number="form.score" class="input" type="number" min="0.5" step="0.5" />
      </div>
    </div>

    <div class="field">
      <label for="q-stem">题干</label>
      <textarea id="q-stem" v-model="form.stem" class="input" rows="3" placeholder="请输入题干（纯文本）"></textarea>
    </div>

    <div class="field">
      <label>选项与正确答案</label>
      <div class="options-editor">
        <div v-for="(option, index) in form.options" :key="index" class="option-row">
          <span class="option-key">{{ option.key }}</span>
          <input
            v-model="option.text"
            class="input"
            :disabled="optionsLocked"
            :placeholder="`选项 ${option.key} 的内容`"
          />
          <label class="option-correct">
            <input
              type="checkbox"
              :checked="form.answer.includes(option.key)"
              @change="toggleAnswer(option.key)"
            />
            正确
          </label>
          <button
            v-if="!optionsLocked && form.options.length > 2"
            class="btn btn-ghost btn-sm"
            type="button"
            @click="removeOption(index)"
          >
            删除
          </button>
        </div>
      </div>
      <button
        v-if="!optionsLocked && form.options.length < 8"
        class="btn btn-sm"
        type="button"
        style="align-self: flex-start; margin-top: 6px"
        @click="addOption"
      >
        + 添加选项
      </button>
    </div>

    <div class="field">
      <label for="q-tags">标签（逗号分隔，用于组卷抽题）</label>
      <input id="q-tags" v-model="form.tags" class="input" placeholder="例如：安全生产,法规" />
    </div>

    <div class="field">
      <label for="q-analysis">解析（仅管理端可见，不下发考生）</label>
      <textarea id="q-analysis" v-model="form.analysis" class="input" rows="2"></textarea>
    </div>

    <div class="modal-actions">
      <button class="btn" type="button" :disabled="submitting" @click="emit('cancel')">取消</button>
      <button class="btn btn-primary" type="submit" :disabled="submitting">
        {{ submitting ? '保存中…' : '保存' }}
      </button>
    </div>
  </form>
</template>

<style scoped>
.qform-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.options-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.option-key {
  width: 20px;
  flex: none;
  font-weight: 600;
  text-align: center;
}

.option-correct {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  white-space: nowrap;
  color: var(--c-text-weak);
}
</style>
