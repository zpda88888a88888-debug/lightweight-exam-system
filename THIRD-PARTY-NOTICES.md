# 第三方组件与许可证说明

本文件记录本项目的第三方依赖及其许可证，用于说明采用 MIT 许可证的合规性。
审计时间：2026-09-20（依据当时锁定的依赖版本）。

---

## 1. 结论

**本项目可以采用 MIT 许可证，不存在许可证冲突。**

- 全部第三方依赖均为**宽松许可证**（MIT / BSD / Apache-2.0 / ISC / MPL-2.0 / BlueOak-1.0.0 / PSF / 0BSD）；
- **没有任何 GPL / AGPL / LGPL 等传染性 copyleft 依赖**；
- 本项目**未复制任何第三方源代码**，仅以依赖方式使用，不触发 copyleft 的衍生作品义务；
- 唯一需要注意的 MPL-2.0 属**文件级**copyleft，只要不修改并分发其源文件即无额外义务。

---

## 2. 后端运行时依赖

来源：`backend/requirements-deploy.txt` 解析出的完整依赖树（即离线包内的 wheel）。

| 组件 | 版本 | 许可证 |
|---|---|---|
| FastAPI | 0.141.1 | MIT |
| Starlette | 1.6.0 | BSD-3-Clause |
| Uvicorn | 0.53.0 | BSD-3-Clause |
| SQLModel | 0.0.42 | MIT |
| SQLAlchemy | 2.0.54 | MIT |
| Pydantic | 2.13.5 | MIT |
| pydantic-core | 2.46.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| AnyIO | 4.15.1 | MIT |
| h11 | 0.16.0 | MIT |
| Click | 8.5.0 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |

**运行时环境自带组件**（随 Python 分发，非本仓库引入）：

| 组件 | 许可证 |
|---|---|
| Python | PSF-2.0 |
| SQLite | Public Domain（公有领域） |

## 3. 后端开发/测试依赖

不随部署包分发，仅供开发与 CI 使用。

| 组件 | 版本 | 许可证 |
|---|---|---|
| pytest | 9.1.1 | MIT |
| pytest-cov | 7.1.0 | MIT |
| coverage | 7.16.1 | Apache-2.0 |
| httpx | 0.28.1 | BSD-3-Clause |
| httpcore | 1.0.9 | BSD-3-Clause |
| certifi | 2026.7.22 | **MPL-2.0** |
| pluggy | 1.6.0 | MIT |
| iniconfig | 2.3.0 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| Pygments | 2.21.0 | BSD-2-Clause |

## 4. 前端依赖

共 88 个包（含传递依赖），许可证分布：

| 许可证 | 包数 | 性质 |
|---|---|---|
| MIT | 62 | 宽松 |
| Apache-2.0 | 7 | 宽松 |
| ISC | 7 | 宽松（等价 MIT） |
| BlueOak-1.0.0 | 5 | 宽松 |
| MPL-2.0 | 2 | 文件级 copyleft |
| BSD-3-Clause | 2 | 宽松 |
| BSD-2-Clause | 1 | 宽松 |
| 0BSD | 1 | 宽松（无署名要求） |

直接依赖：

| 组件 | 版本 | 许可证 | 用途 |
|---|---|---|---|
| Vue | 3.5.43 | MIT | 框架 |
| vue-router | 5.3.1 | MIT | 路由 |
| ECharts | 6.1.0 | Apache-2.0 | 统计图表 |
| Vite | 8.3.0 | MIT | 构建 |
| TypeScript | 5.9.3 | Apache-2.0 | 类型系统 |
| vue-tsc | 3.3.11 | MIT | 类型检查 |
| Vitest | 5.0.1 | MIT | 单元测试 |
| @vue/test-utils | 2.5.1 | MIT | 组件测试 |
| happy-dom | 20.14.5 | MIT | DOM 测试环境 |
| fake-indexeddb | 6.2.5 | Apache-2.0 | IndexedDB 测试替身 |
| @vitejs/plugin-vue | 6.0.9 | MIT | Vue 插件 |
| @playwright/test | 1.63.0 | Apache-2.0 | 浏览器 E2E |

> 前端依赖**不随部署包分发**（部署包只含构建产物），仅供开发与测试使用。

---

## 5. 关于仓库内的文档资产

`极轻量级客观题考试系统— 规格说明.md`、`— 技术架构.md`、`— 测试方案.md`
三份文档由项目负责人提供，作为本项目的输入规格一并纳入版本库，
其著作权归项目负责人所有，随本项目一同以 MIT 许可证授权。

若这三份文档中**含有来自第三方的受版权保护内容**，请在对外分发前自行确认授权情况
（本审计只覆盖代码依赖，不涉及文档内容的来源）。

---

## 6. 复核方式

```bash
# 后端依赖许可证
cd backend && .venv/bin/python - <<'PY'
import importlib.metadata as md
for d in sorted(md.distributions(), key=lambda x: (x.metadata['Name'] or '').lower()):
    m = d.metadata
    print(f"{m['Name']:<22}{m['Version']:<12}{m.get('License-Expression') or (m.get('License') or '')[:40]}")
PY

# 前端依赖许可证
cd frontend && node -e "
const fs=require('fs'),p=require('path');
const c={};
for (const d of fs.readdirSync('node_modules')) {
  if (d.startsWith('.')) continue;
  const names = d.startsWith('@') ? fs.readdirSync(p.join('node_modules',d)).map(s=>d+'/'+s) : [d];
  for (const n of names) {
    const f = p.join('node_modules', n, 'package.json');
    if (!fs.existsSync(f)) continue;
    const j = JSON.parse(fs.readFileSync(f,'utf8'));
    const l = typeof j.license==='string'?j.license:JSON.stringify(j.license||'(未声明)');
    c[l]=(c[l]||0)+1;
  }
}
console.log(c);
"
```

若上游依赖许可证发生变化，请以各依赖自带 `LICENSE` 文件为准。
