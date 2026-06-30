# 部署指南（FastAPI + Docker）

三种用法，从轻到重：

## A. 命令行（最快，开发用）
```bash
python main.py
```

## B. Web 服务（本地，不用 Docker）
```bash
pip install -e ".[server]"
uvicorn api:app --reload          # 默认 http://127.0.0.1:8000
```
浏览器打开 http://127.0.0.1:8000 ，是个聊天页：多轮对话、下单时弹确认框、侧栏显示采购单草稿/分析口径。
此时 `CHECKPOINTER` 默认 `memory`（重启即忘）；想本地持久化设 `CHECKPOINTER=sqlite`。

## C. Docker（app + Postgres 双容器，最完整）

### 前置
1. 安装 **Docker Desktop**（Windows 版），启动它（右下角鲸鱼图标常亮即 daemon 就绪）。
2. 确认 `.env` 里填了 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `MODEL_NAME`（compose 会注入容器）。

### 一条命令起全栈
```bash
docker compose up --build
```
然后打开 http://localhost:8000 。停止：`Ctrl-C`，或 `docker compose down`（加 `-v` 连数据卷一起删）。

### 这条命令背后发生了什么（Docker 概念速通）
- **镜像(image)**：`Dockerfile` 是"配方"，`build` 把它烤成一个不可变的镜像（含 Python+依赖+你的代码）。
- **容器(container)**：镜像的运行实例。这里起了两个：`app`(你的服务) 和 `db`(Postgres)。
- **compose**：用 `docker-compose.yml` 一次编排多个容器，并把它们放进同一个虚拟网络——
  所以 `app` 用主机名 **`db`**（服务名）就能连到数据库，而不是 `localhost`。
- **端口映射 `8000:8000`**：把容器里的 8000 暴露到你电脑的 8000，浏览器才进得去。
- **数据卷(volume) `pgdata`**：数据库文件存在卷里，容器删了数据还在（持久化）。
- **healthcheck + depends_on**：让 `app` 等 `db` 真正就绪再启动；代码里(`persistence.py`)还有连接重试兜底。
- **层缓存**：Dockerfile 先复制依赖声明再装依赖、最后才复制常改的代码——改业务代码重建时不必重装依赖。

### 验证持久化（Docker 的"杀手锏"演示）
1. 在页面里走到"确认下单"那一步，**先别确认**，直接 `docker compose restart app`。
2. 刷新页面、用**同一会话**继续（或重发），状态仍在——因为断点存在 Postgres（卷）里，不随容器重启而丢。
   这就是 `CHECKPOINTER=postgres` + `thread_id` 的跨进程续跑。

### 常见坑
- **daemon 没起**：报 `cannot connect to the Docker daemon` → 打开 Docker Desktop。
- **app 连不上 db**：第一次 DB 初始化慢，`depends_on healthy` + 代码重试会兜住；若仍失败看 `docker compose logs db`。
- **改了代码没生效**：`build` 有缓存，强制重建用 `docker compose up --build`。
- **端口被占**：把 compose 里 `8000:8000` 左边换成别的，如 `8080:8000`。

## 接口（给前端或外部调用）
- `POST /chat` `{thread_id, message}` → `{type:"reply"|"interrupt", ...}`
- `POST /resume` `{thread_id, decision}` → 同上（HITL 确认后续跑）
- `GET /health`、`GET /`（聊天页）
