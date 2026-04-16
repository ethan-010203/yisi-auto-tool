# Yisi Auto Tool Frontend

前端工作台基于 `Vue 3 + Vite`，用于统一展示部门自动化工具、配置入口、运行状态和执行日志。

## 当前接入情况

截至 `2026-04-14`，前端已支持以下内容：

- 部门切换与工具卡片展示
- 工具配置弹窗
- `CONSULT / invoice_recognizer` 预览弹窗
- 部门共享路径配置与路径连通性测试
- 实时执行日志面板
- 运行中任务终止
- Toast 消息反馈

当前页面中，真正接入后端能力的业务工具有 2 个：

- `CONSULT / invoice_recognizer`
- `BUE2 / citeo_email_extractor`

其余部门工具当前仍为占位态展示。

## 启动方式

```bash
cd front
npm install
npm run dev
```

默认访问地址：

- `http://localhost:5173`

## 开发代理

开发环境下，Vite 会将 `/api` 自动代理到后端服务。

默认代理地址：

- `http://localhost:8000`

如需指定其他后端地址：

```bash
VITE_PROXY_TARGET=http://<后端IP>:8000 npm run dev
```

## 环境变量

| 变量名 | 用途 |
|--------|------|
| `VITE_PROXY_TARGET` | Vite 开发代理目标地址 |
| `VITE_API_BASE_URL` | 前端请求 API 的基础路径，默认是 `/api` |

## 目录说明

```text
front/
├── src/
│   ├── api/                  # 接口封装
│   ├── assets/               # 静态资源
│   ├── components/           # UI 组件、日志面板、预览弹窗
│   ├── data/                 # 部门与工具定义
│   ├── App.vue               # 页面主入口
│   └── style.css             # 全局样式
├── index.html
└── vite.config.js
```

## 页面能力说明

### 部门工作台

- `src/data/departments.js` 维护部门卡片与工具元数据
- 当前只有 `CONSULT` 和 `BUE2` 的业务工具真正具备执行能力

### 配置与执行

- 通过 `src/api/index.js` 调用后端保存工具配置
- 可设置部门共享目录，并触发网络路径测试
- 可直接发起脚本执行，并在页面内查看实时输出

### 预览与反馈

- `invoice_recognizer` 已接入预览弹窗
- 页面包含日志面板、状态提示和异常反馈能力

## 打包

```bash
cd front
npm run build
```

构建产物默认输出到 Vite 标准目录，可配合任意静态服务部署。
