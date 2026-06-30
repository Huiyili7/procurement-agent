"""Checkpointer 工厂：图的"记忆"后端，决定状态存哪、能不能跨进程续跑。

为什么抽一层：HITL 的 interrupt/resume 和多轮对话都依赖 checkpointer 存断点。
开发/测试要零依赖、确定性(memory)；要演示"重启后凭 thread_id 续跑"用 sqlite(零部署、落文件)；
生产换 postgres——三者同一接口(BaseCheckpointSaver)，只换这一个工厂，图结构不动。
这就是 PRD 说的"MVP MemorySaver → 生产 PostgresSaver"的落地点。

环境变量：
  CHECKPOINTER=memory(默认) | sqlite | postgres
  CHECKPOINTER_PATH=.checkpoints.sqlite   # sqlite 用
  PG_CONN=postgresql://...                # postgres 用
"""
import os

from langgraph.checkpoint.memory import MemorySaver


def get_checkpointer():
    kind = os.environ.get("CHECKPOINTER", "memory").lower()

    if kind == "memory":
        # 进程内、重启即丢。测试/CI 用——确定性、零副作用。
        return MemorySaver()

    if kind == "sqlite":
        # 落文件、可跨进程/重启续跑，且零部署(不用起 DB 服务)。
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver

        path = os.environ.get("CHECKPOINTER_PATH", ".checkpoints.sqlite")
        # check_same_thread=False：LangGraph 可能在不同线程读写同一连接。
        conn = sqlite3.connect(path, check_same_thread=False)
        return SqliteSaver(conn)

    if kind == "postgres":
        # 生产做法。需要 langgraph-checkpoint-postgres + 一个可连的 PG。
        # 接口与上面完全一致——这正是"换后端不改图"的证明。
        import time

        from langgraph.checkpoint.postgres import PostgresSaver

        conn_str = os.environ["PG_CONN"]
        # 容器编排里 app 可能先于 DB ready，连不上就重试几次(指数退避太重，固定间隔够用)。
        last_err = None
        for attempt in range(10):
            try:
                # from_conn_string 返回上下文管理器；进程级常驻，手动进入并保活。
                saver = PostgresSaver.from_conn_string(conn_str).__enter__()
                saver.setup()  # 首次建表(幂等)
                return saver
            except Exception as e:  # noqa: BLE001 (启动期连接失败要重试，不区分类型)
                last_err = e
                time.sleep(1.5)
        raise RuntimeError(f"连不上 Postgres({conn_str})，重试 10 次仍失败：{last_err}")

    raise ValueError(f"未知 CHECKPOINTER={kind!r}，应为 memory|sqlite|postgres")
