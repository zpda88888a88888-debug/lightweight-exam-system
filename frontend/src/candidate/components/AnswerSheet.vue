<script setup lang="ts">
/**
 * 答题卡：显示已答/未答，可跳题。
 */
import { computed } from 'vue'

import { isAnswered, type Answers } from '@/lib/answers'

const props = defineProps<{
  questions: { id: number }[]
  answers: Answers
}>()

const emit = defineEmits<{ jump: [index: number] }>()

const items = computed(() =>
  props.questions.map((question, index) => ({
    index,
    answered: isAnswered(props.answers[question.id]),
  })),
)

const answeredTotal = computed(() => items.value.filter((i) => i.answered).length)
</script>

<template>
  <div class="sheet">
    <div class="sheet-head">
      <strong>答题卡</strong>
      <span class="muted">已答 {{ answeredTotal }} / {{ questions.length }}</span>
    </div>

    <div class="sheet-grid">
      <button
        v-for="item in items"
        :key="item.index"
        class="sheet-cell"
        :class="{ 'is-answered': item.answered }"
        type="button"
        :title="item.answered ? '已作答' : '未作答'"
        @click="emit('jump', item.index)"
      >
        {{ item.index + 1 }}
      </button>
    </div>

    <div class="sheet-legend muted">
      <span class="legend-dot legend-answered"></span>已答
      <span class="legend-dot legend-blank"></span>未答
    </div>
  </div>
</template>

<style scoped>
.sheet {
  padding: 12px;
}

.sheet-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 14px;
  margin-bottom: 10px;
}

.sheet-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(38px, 1fr));
  gap: 6px;
}

.sheet-cell {
  aspect-ratio: 1;
  min-height: 34px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  background: #f8fafc;
  color: var(--c-text-weak);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.sheet-cell:hover {
  border-color: var(--c-primary);
}

.sheet-cell.is-answered {
  background: var(--c-primary);
  border-color: var(--c-primary);
  color: #fff;
  font-weight: 600;
}

.sheet-legend {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 12px;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  display: inline-block;
}

.legend-answered {
  background: var(--c-primary);
}

.legend-blank {
  background: #f8fafc;
  border: 1px solid var(--c-border);
  margin-left: 8px;
}
</style>
