# Yisi Auto Tool

椅思内部本地自动化工具项目，采用 `Vue 3 + Vite` 前端和 `FastAPI + Python` 后端，面向各部门承接可配置、可执行、可留痕的自动化脚本。

## 当前状态

截至 `2026-04-14`，项目已经完成基础平台搭建，并有 2 个业务脚本接入到统一页面和后端执行链路中。

- 已上线脚本数量：`2`
- 已接入部门：`CONSULT`、`BUE2`
- 已具备能力：工具配置保存、部门局域网路径配置、网络路径读写测试、实时日志、终止任务、浏览器本机文件选择上传、历史执行记录
- 前端占位部门：`BUE1`、`BUV1`、`BUV2`、`BUV3`

## 已上线脚本

| 部门 | 工具 ID | 页面名称 | 当前用途 | 输入配置 | 输出结果 |
|------|---------|----------|----------|----------|----------|
| CONSULT | `invoice_recognizer` | 英德单据识别 | 识别英国、德国递延税相关 PDF，提取关键字段并生成结果文件 | 单据总文件夹、总清单 Excel | 客户结果表、批次汇总表 |
| BUE2 | `citeo_email_extractor` | FR-Citeo 注销成功名单邮件提取 | 连接 163 邮箱，提取匹配主题邮件中的会员号并导出 Excel | 邮件文件夹、邮件数量、部门共享路径 | 注销成功名单 Excel |

## 当前进度

### 已完成

- 统一前端工作台已完成，支持按部门切换工具。
- FastAPI 后端已完成工具注册、配置读写、脚本异步执行和日志查询。
- 工具运行链路已支持实时输出回传和手动终止。
- 部门级共享路径配置已接入，并提供写入权限测试接口。
- `CONSULT / invoice_recognizer` 已接入预览弹窗、配置读取和正式执行。
- `BUE2 / citeo_email_extractor` 已接入邮箱文件夹读取、配置保存和正式执行。
- 部门日志已按 `black/logs/*.json` 独立存储。

### 已验证

- `2026-04-14` 日志显示，`CONSULT / invoice_recognizer` 已有成功执行记录，能够更新共享目录中的 `汇总表.xlsx`。
- `2026-04-14` 日志显示，`BUE2 / citeo_email_extractor` 已有成功执行记录，能够在部门共享目录生成注销成功名单 Excel。
- 两个部门的测试脚本 `test_hello`、`test` 已用于验证异步执行和日志展示。

### 待推进

- 其他部门目前仍是前端占位卡片，尚未接入真实脚本。
- 后端 `DEPARTMENT_SCRIPTS` 中存在 `pdf_classifier` 预留项，但当前脚本文件未落地，尚未上线。
- 文档、依赖安装说明和环境约束此前滞后于代码，已在本次更新中补齐。

### 当前注意事项

- `CONSULT / invoice_recognizer` 的历史日志里出现过共享目录写入权限失败记录，部署时需要先验证局域网路径的读写权限。
- `BUE2 / citeo_email_extractor` 当前运行依赖预置的 163 邮箱能力，使用前需要确认授权信息和目标文件夹可用。

## 项目结构

```text
.
├── front/                     # Vue 3 前端
│   ├── src/
│   │   ├── api/              # 前端 API 封装
│   │   ├── components/       # UI、日志面板、预览弹窗等组件
│   │   └── data/             # 部门与工具定义
├── black/                     # FastAPI 后端
│   ├── configs/              # 工具与部门配置
│   ├── logs/                 # 按部门存储的执行日志
│   ├── runner/               # 运行日志和进程管理
│   ├── scripts/              # 自动化脚本
│   └── main.py               # 后端入口
└── README.md
```

## 本地启动

### 1. 后端依赖

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r black/requirements.txt
```

说明：

- `invoice_recognizer` 依赖 `PyMuPDF(fitz)` 和 `openai`
- 浏览器上传接口依赖 `python-multipart`
- 旧版服务端本机弹窗能力仍依赖 `tkinter`
- 建议统一使用项目根目录的 `.venv`，避免误用电脑里已有的全局 `python/openai`

### 2. 启动后端

```bash
./.venv/bin/python -m uvicorn black.main:app --host 0.0.0.0 --port 8000 --reload
```

- 健康检查：`http://localhost:8000/api/health`
- 接口文档：`http://localhost:8000/docs`

### 3. 启动前端

```bash
cd front
npm install
npm run dev
```

### 3.1 启动说明

项目已移除根目录的一键启动 / 停止脚本，请按上面的原始命令分别启动后端与前端。







默认开发代理会把 `/api` 转发到 `http://localhost:8000`。

如果后端不在本机，可在启动前指定：

```bash
VITE_PROXY_TARGET=http://<后端IP>:8000 npm run dev
```

### 4. 局域网部署要点

- 前端默认端口：`5173`
- 后端默认端口：`8000`
- 这套系统后续统一按 Windows 部署考虑，前端页面中应保存“部署电脑可访问”的 Windows 路径，例如：
  - `CONSULT`：`\\\\192.168.76.93\\厦门部门\\顾问部`
  - `BUE2`：`\\\\192.168.76.93\\厦门部门\\BUE2`
  - 或本机盘符路径：`D:\\YisiData\\BUE2`
- `CONSULT / invoice_recognizer` 的“选择文件夹 / 选择 Excel”会在访问网页的用户电脑上弹窗选择，并上传副本到部署电脑，不会在部署电脑桌面上弹系统选择框
- 共享目录保存后，建议先通过页面内“测试路径”确认可读写

## 配置文件

- 工具配置：`black/configs/<部门>_<工具>.json`
- 部门配置：`black/configs/<部门>_config.json`
- 运行并发配置：`black/configs/runtime_limits.json`
- 执行日志：`black/logs/<department>.json`

当前已存在的配置文件：

- `black/configs/CONSULT_invoice_recognizer.json`
- `black/configs/BUE2_citeo_email_extractor.json`
- `black/configs/CONSULT_config.json`
- `black/configs/BUE2_config.json`
- `black/configs/runtime_limits.json`

`runtime_limits.json` 当前字段：

- `global`：全局最多同时运行多少个任务
- `perDepartment`：每个部门最多同时运行多少个任务
- `perTool`：同一部门下同一工具最多同时运行多少个任务

## 主要接口

| 接口 | 说明 |
|------|------|
| `GET /api/health` | 健康检查 |
| `GET /api/departments/{department}/tools` | 查询部门工具 |
| `POST /api/departments/{department}/tools/{tool}/run` | 执行工具 |
| `POST /api/departments/{department}/tools/{tool}/config` | 保存工具配置 |
| `GET /api/departments/{department}/tools/{tool}/config` | 读取工具配置 |
| `GET /api/departments/{department}/tools/{tool}/preview` | 获取工具预览 |
| `GET /api/departments/{department}/logs` | 查询部门日志 |
| `POST /api/executions/{log_id}/terminate` | 终止运行中的任务 |
| `POST /api/test-network-path` | 测试共享目录读写权限 |
| `POST /api/uploads/consult/invoice-recognizer/folder` | 上传顾问部源文件夹 |
| `POST /api/uploads/consult/invoice-recognizer/excel` | 上传顾问部 Excel 清单 |
| `POST /api/select-folder` | 选择文件夹 |
| `POST /api/select-file` | 选择文件 |

## 开发命令

```bash
cd front
npm run dev
npm run build
npm run preview
```

```bash
cd black
uvicorn main:app --reload
```
