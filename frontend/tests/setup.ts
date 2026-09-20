// Vitest 全局准备：为 IndexedDB 提供内存实现
// 说明：fake-indexeddb/auto 会安装一个全局 indexedDB；
// 需要隔离的测试自行 new IDBFactory() 注入，避免用例间串数据。
import 'fake-indexeddb/auto'
