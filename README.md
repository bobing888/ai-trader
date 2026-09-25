# AI 交易助手 — 项目说明

> **现货 + 合约混合模式**的 AI 交易助手。集成推荐单、回测复盘、策略管理、Dashboard 四大模块。

## 目录结构

```
ai-trader/
├── backend/          # FastAPI 后端（Python 3.14）
│   ├── app/          # 业务代码
│   ├── tests/        # pytest 测试
│   └── pyproject.toml
├── frontend/         # React + TypeScript 前端（Vite）
│   ├── src/          # 业务代码
│   └── package.json
├── docs/             # 设计文档
│   └── architecture/
│       └── github-survey.md   # GitHub 调研汇总
└── tests/            # 端到端测试
```

## 快速启动

### 后端
```bash
cd backend
uv sync                  # 安装依赖
uv run pytest            # 跑测试
uv run uvicorn app.main:app --reload --port 8765  # ⚠️ 生产端口是 8765，不是 8000
```

### 前端
```bash
cd frontend
pnpm install             # 安装依赖
pnpm dev                 # 启动 dev server (http://localhost:5173)
pnpm build               # 生产构建
pnpm test                # 跑测试
```

## 当前进度

- [x] W1 基础设施 + 数据层（详见 [W1 总结](docs/architecture/w1-summary.md)）
- [ ] W2 推荐单引擎（Regime + Affinity Matrix + 置信度）
- [ ] W3 推荐单 UI（K 线信号标注 + 实时推送）
- [ ] W4 回测复盘（多策略对比 + 归因面板）

## 调研依据

详细调研笔记见 [docs/architecture/github-survey.md](docs/architecture/github-survey.md)，覆盖：
- 策略库（10 个 MIT/Apache-2.0 策略源码）
- 推荐单引擎架构（6 个方案）
- Dashboard UI（5 个 React 项目源码）
- 回测复盘系统（7 个工具）

## License 原则

仅借鉴 MIT / Apache-2.0 / BSD 协议项目；GPL/AGPL 仅借鉴架构模式，不复制代码。
