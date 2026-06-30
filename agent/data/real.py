"""RealRepository：脱敏真实数据实现(不进 git 的"口子")。

数据文件放在 .gitignore 的本地路径，默认 agent/data/_real/purchase_history.json，
可用环境变量 REAL_DATA_PATH 覆盖。文件不存在时给出清晰报错(而不是静默返回空)。

格式：JSON 数组，每项字段对应 PurchaseRecord(item_name/url/last_project/note/match_terms)。
M4 真正接生产时，可以把这里换成查 Postgres——调用方(工具/图)依旧零改动。
"""
import json
import os
from pathlib import Path

from .models import ComplianceRecord, PurchaseRecord, SpendRecord
from .repository import PurchaseRepository

_DEFAULT_PATH = Path(__file__).parent / "_real" / "purchase_history.json"
_DEFAULT_SPEND_PATH = Path(__file__).parent / "_real" / "spend.json"
_DEFAULT_COMPLIANCE_PATH = Path(__file__).parent / "_real" / "compliance.json"


class RealRepository(PurchaseRepository):
    def __init__(self) -> None:
        self._path = Path(os.environ.get("REAL_DATA_PATH", _DEFAULT_PATH))
        if not self._path.exists():
            raise FileNotFoundError(
                f"DATA_SOURCE=real 但未找到数据文件：{self._path}\n"
                "请放置脱敏数据(JSON 数组)，或用 REAL_DATA_PATH 指定路径；"
                "公开仓库请用默认的 DATA_SOURCE=seed。"
            )
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._records = [PurchaseRecord(**item) for item in raw]

    def search_history(self, keyword: str) -> list[PurchaseRecord]:
        kw = keyword.lower()
        return [
            r
            for r in self._records
            if any(term.lower() in kw or kw in term.lower() for term in r.match_terms)
        ]

    def spend_records(self) -> list[SpendRecord]:
        # 花费数据可选：放了 spend.json 就读，没放则返回空(分析类功能优雅降级)。
        path = Path(os.environ.get("REAL_SPEND_PATH", _DEFAULT_SPEND_PATH))
        if not path.exists():
            return []
        return [SpendRecord(**item) for item in json.loads(path.read_text(encoding="utf-8"))]

    def compliance_for(self, supplier: str) -> ComplianceRecord | None:
        path = Path(os.environ.get("REAL_COMPLIANCE_PATH", _DEFAULT_COMPLIANCE_PATH))
        if not path.exists():
            return None
        records = [ComplianceRecord(**item) for item in json.loads(path.read_text(encoding="utf-8"))]
        return next(
            (r for r in records if r.supplier in supplier or supplier in r.supplier), None
        )
