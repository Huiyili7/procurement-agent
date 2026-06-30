"""PurchaseRepository：数据访问的抽象接口 + 数据源工厂。

第一性原理(副作用隔离)：agent 和工具**不应该知道数据来自哪里**。
工具只调 `repo.search_history(keyword)`，至于背后是合成数据(seed)还是脱敏真实数据(real)，
由环境变量 DATA_SOURCE 在工厂里决定。好处：
- 仓库可公开：默认 seed(合成、可进 git)；real 走 .gitignore 的本地路径，不进仓库。
- 可测/可换：测试注入假仓库；M4 换成查生产 Postgres 时，只新增一个实现，工具与图不动。
这就是"用接口隔离副作用"，也是 Repository Pattern 的核心价值。
"""
import os
from abc import ABC, abstractmethod

from .models import PurchaseRecord, SpendRecord


class PurchaseRepository(ABC):
    """采购数据的访问接口。新数据源 = 新实现这个抽象类，调用方零改动。"""

    @abstractmethod
    def search_history(self, keyword: str) -> list[PurchaseRecord]:
        """按关键词查历史采购记录，命中返回(可能多条)，未命中返回空列表。"""
        raise NotImplementedError

    @abstractmethod
    def spend_records(self) -> list[SpendRecord]:
        """返回全部花费记录(供 Analytics 聚合分析)。"""
        raise NotImplementedError


def get_repository() -> PurchaseRepository:
    """工厂：按 DATA_SOURCE(seed|real) 返回具体实现。默认 seed。

    延迟 import 具体实现：real 实现可能依赖本地文件/驱动，seed 场景不该被它拖累。
    """
    source = os.environ.get("DATA_SOURCE", "seed").lower()
    if source == "seed":
        from .seed import SeedRepository

        return SeedRepository()
    if source == "real":
        from .real import RealRepository

        return RealRepository()
    raise ValueError(f"未知 DATA_SOURCE={source!r}，应为 'seed' 或 'real'")
