# syntax=docker/dockerfile:1
# 这个镜像把 FastAPI 服务打包成一个可移植的容器。

# 1) 基础镜像：官方 Python 3.11 的精简版(slim 体积小，够用)。
FROM python:3.11-slim

# 2) 容器内的工作目录(后续命令都在这里执行)。
WORKDIR /app

# 让 Python 输出不缓冲、不写 .pyc(容器里日志要实时、目录要干净)。
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# 3) 先只复制"依赖声明 + 包代码"再装依赖 —— 利用 Docker 层缓存：
#    只要 pyproject/agent 没变，重建时这一层(装依赖,最慢)就直接复用，不重装。
COPY pyproject.toml ./
COPY agent ./agent
RUN pip install --no-cache-dir ".[server,postgres]"

# 4) 再复制变动频繁的入口与前端(改这些不会让上面的依赖层失效)。
COPY api.py main.py ./
COPY web ./web

# 5) 声明服务端口(仅文档作用，真正映射在 compose 里做)。
EXPOSE 8000

# 6) 容器启动命令：用 uvicorn 跑 FastAPI。
#    --host 0.0.0.0 必须有，否则只监听容器内 localhost，外面连不进来。
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
