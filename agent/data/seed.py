"""SeedRepository：合成数据实现(默认、可公开、进 git)。

数据是手编的、脱敏的，纯粹为了把链路跑通和写 eval。
真实/脱敏数据走 RealRepository(real.py) + .gitignore，不在这里。
"""
from .models import PurchaseRecord, SpendRecord
from .repository import PurchaseRepository

_SEED_RECORDS: list[PurchaseRecord] = [
    PurchaseRecord(
        item_name="SKF 6204-2RS 深沟球轴承",
        url="https://item.taobao.com/item.htm?id=123",
        last_project="IML001",
        note="上次买过 10 个",
        match_terms=["轴承", "bearing", "6204"],
    ),
    PurchaseRecord(
        item_name="M3x10 内六角圆柱头螺丝 304 不锈钢",
        url="https://item.jd.com/100012.html",
        last_project="通用",
        note="高频复购件",
        match_terms=["螺丝", "螺钉", "screw", "m3"],
    ),
    PurchaseRecord(
        item_name="硬质合金立铣刀 4 刃 D6",
        url="https://detail.1688.com/offer/456.html",
        last_project="加工工具",
        note="",
        match_terms=["铣刀", "刀具", "endmill", "立铣刀"],
    ),
]


_SEED_SPEND: list[SpendRecord] = [
    SpendRecord(project="IML001", category="轴承", amount=1200.0, month="2026-04"),
    SpendRecord(project="IML001", category="刀具", amount=3400.0, month="2026-04"),
    SpendRecord(project="IML001", category="紧固件", amount=300.0, month="2026-05"),
    SpendRecord(project="IML002", category="轴承", amount=800.0, month="2026-05"),
    SpendRecord(project="IML002", category="刀具", amount=5600.0, month="2026-05"),
    SpendRecord(project="IML002", category="电子料", amount=2100.0, month="2026-06"),
    SpendRecord(project="IML003", category="紧固件", amount=450.0, month="2026-06"),
    SpendRecord(project="IML003", category="刀具", amount=2800.0, month="2026-06"),
]


class SeedRepository(PurchaseRepository):
    def search_history(self, keyword: str) -> list[PurchaseRecord]:
        kw = keyword.lower()
        return [
            r
            for r in _SEED_RECORDS
            if any(term.lower() in kw or kw in term.lower() for term in r.match_terms)
        ]

    def spend_records(self) -> list[SpendRecord]:
        return list(_SEED_SPEND)
