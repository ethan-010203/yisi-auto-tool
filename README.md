# Yisi Auto Tool

本地自动化工具项目，支持咨询部门发票识别自动化流程。

## 技术栈

- **前端**: Vue 3 + Vite
- **后端**: FastAPI (Python)
- **自动化脚本**: Python + tkinter

## 项目结构

```
.
├── front/           # Vue 3 前端项目
├── black/           # FastAPI 后端
│   ├── configs/     # 配置文件存储
│   ├── scripts/     # 自动化脚本
│   └── main.py      # FastAPI 入口
└── package.json     # 根目录依赖
```

## 局域网部署指南

### 1. 环境准备

**后端依赖:**
```bash
cd black
pip install fastapi uvicorn pydantic
```

**前端依赖:**
```bash
cd front
npm install
```

### 2. 启动后端

```bash
cd black
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- 服务地址: `http://0.0.0.0:8000`
- API文档: `http://localhost:8000/docs`

### 3. 启动前端

**方式一 - 使用默认代理地址:**
```bash
cd front
npm run dev
```

默认代理指向 `http://192.168.1.40:8000`

**方式二 - 指定后端地址:**
```bash
cd front
$env:VITE_PROXY_TARGET="http://<后端IP>:8000"
npm run dev
```

例如后端在 `192.168.1.100`：
```bash
$env:VITE_PROXY_TARGET="http://192.168.1.100:8000"
npm run dev
```

### 4. 局域网访问

1. 获取本机 IP: `ipconfig`
2. 其他设备通过 `http://<前端IP>:5173` 访问

## 配置说明

- **前端端口**: 5173 (可在 `vite.config.js` 修改)
- **后端端口**: 8000
- **API 代理**: `/api/*` 自动转发到后端
- **CORS**: 已配置允许所有来源

## 可用功能

| 部门 | 工具 | 说明 |
|------|------|------|
| CONSULT | invoice_recognizer | 发票识别自动化 |

## 开发命令

```bash
# 前端开发
cd front && npm run dev

# 前端构建
cd front && npm run build

# 前端预览
cd front && npm run preview

# 后端开发
cd black && uvicorn main:app --reload
```
