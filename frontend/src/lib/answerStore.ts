/**
 * 答案本地持久化（IndexedDB）。
 *
 * 规格依据：spec 4.2、架构 9.4
 *   - 答题后答案写入 IndexedDB，刷新 / 断网 / 浏览器崩溃可恢复。
 *   - 换设备、换浏览器、清缓存 → 读到空答案，从空白继续，不报错。
 *   - 考试中零后端交互：本模块是答案的唯一存放处。
 */

/** questionId → 选中的原始选项标识（A/B/C/D 或 对/错） */
export type Answers = Record<number, string[]>

export interface AnswerStore {
  /** 保存并返回保存时间（ISO8601） */
  save: (attemptId: number, answers: Answers) => Promise<string>
  /** 读取；从未保存过返回空对象 */
  load: (attemptId: number) => Promise<Answers>
  /** 清空指定 attempt 的答案（交卷成功后调用） */
  clear: (attemptId: number) => Promise<void>
}

export interface AnswerStoreOptions {
  /** 注入 IDBFactory（测试隔离用） */
  factory?: IDBFactory
  dbName?: string
  storeName?: string
}

const DEFAULT_DB = 'exam-answers'
const DEFAULT_STORE = 'answers'

export function createAnswerStore(options: AnswerStoreOptions = {}): AnswerStore {
  const factory = options.factory ?? globalThis.indexedDB
  const dbName = options.dbName ?? DEFAULT_DB
  const storeName = options.storeName ?? DEFAULT_STORE

  let cached: Promise<IDBDatabase> | null = null

  function open(): Promise<IDBDatabase> {
    if (cached) return cached
    cached = new Promise<IDBDatabase>((resolve, reject) => {
      const request = factory.open(dbName, 1)
      request.onupgradeneeded = () => {
        const db = request.result
        if (!db.objectStoreNames.contains(storeName)) {
          db.createObjectStore(storeName)
        }
      }
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
    return cached
  }

  async function withStore<T>(
    mode: IDBTransactionMode,
    action: (store: IDBObjectStore) => IDBRequest,
  ): Promise<T> {
    const db = await open()
    return new Promise<T>((resolve, reject) => {
      const transaction = db.transaction(storeName, mode)
      const request = action(transaction.objectStore(storeName))
      request.onsuccess = () => resolve(request.result as T)
      request.onerror = () => reject(request.error)
      transaction.onabort = () => reject(transaction.error)
    })
  }

  return {
    async save(attemptId: number, answers: Answers): Promise<string> {
      await withStore<IDBValidKey>('readwrite', (store) => store.put(answers, attemptId))
      return new Date().toISOString()
    },

    async load(attemptId: number): Promise<Answers> {
      const stored = await withStore<Answers | undefined>('readonly', (store) =>
        store.get(attemptId),
      )
      return stored ?? {}
    },

    async clear(attemptId: number): Promise<void> {
      await withStore<undefined>('readwrite', (store) => store.delete(attemptId))
    },
  }
}

/** 应用级单例（考生端使用；测试请自行 new IDBFactory）。 */
export const answerStore = createAnswerStore()
