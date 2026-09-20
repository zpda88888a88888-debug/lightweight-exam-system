/**
 * 答案本地持久化（测试方案 6.12 / spec 4.2、架构 9.4）。
 *
 * 规则：
 *   - 答题后答案写入 IndexedDB，刷新/断网/崩溃可恢复。
 *   - 换设备/换浏览器/清缓存 → 读到空答案，从空白继续，**不报错**。
 *   - 每个 attempt 独立命名空间，互不干扰。
 */

import { beforeEach, describe, expect, it } from 'vitest'

import { createAnswerStore } from '@/lib/answerStore'

let store: ReturnType<typeof createAnswerStore>

beforeEach(() => {
  // 每个用例一个全新的 IndexedDB 实例，保证测试隔离
  store = createAnswerStore({ factory: new IDBFactory(), dbName: `exam-${Math.random()}` })
})

describe('createAnswerStore', () => {
  it('保存后能读回答案', async () => {
    await store.save(1, { 101: ['A'], 102: ['A', 'B'] })

    const loaded = await store.load(1)
    expect(loaded).toEqual({ 101: ['A'], 102: ['A', 'B'] })
  })

  it('未保存过的 attempt 读到空对象（换设备/清缓存不报错）', async () => {
    const loaded = await store.load(999)
    expect(loaded).toEqual({})
  })

  it('同一 attempt 再次保存覆盖为最新答案（可回头改题）', async () => {
    await store.save(1, { 101: ['A'] })
    await store.save(1, { 101: ['B'], 102: ['C'] })

    const loaded = await store.load(1)
    expect(loaded).toEqual({ 101: ['B'], 102: ['C'] })
  })

  it('不同 attempt 之间互不干扰', async () => {
    await store.save(1, { 101: ['A'] })
    await store.save(2, { 101: ['D'] })

    expect(await store.load(1)).toEqual({ 101: ['A'] })
    expect(await store.load(2)).toEqual({ 101: ['D'] })
  })

  it('可以清空指定 attempt 的答案', async () => {
    await store.save(1, { 101: ['A'] })
    await store.clear(1)

    expect(await store.load(1)).toEqual({})
  })

  it('单选答案以数组形式保存，与后端提交格式一致', async () => {
    await store.save(1, { 101: ['B'] })

    const loaded = await store.load(1)
    expect(Array.isArray(loaded[101])).toBe(true)
    expect(loaded[101]).toEqual(['B'])
  })

  it('保存空答案集合不报错', async () => {
    await store.save(1, {})
    expect(await store.load(1)).toEqual({})
  })

  it('保存时间戳可用于展示「已保存」提示', async () => {
    const savedAt = await store.save(1, { 101: ['A'] })
    expect(savedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  })
})
