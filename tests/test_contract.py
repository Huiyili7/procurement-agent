"""第 1 块·工具契约层：标志正确挂载、不变式生效、schema 双用挡住错参。"""
import pytest
from pydantic import ValidationError

from agent.tools import (
    TOOLS,
    CreateRequirementArgs,
    SideEffects,
)


def test_flags_attached_per_contract_table():
    by_name = {t.name: t.extras for t in TOOLS}
    assert by_name["search_purchase_history"]["is_read_only"] is True
    assert by_name["search_purchase_history"]["is_destructive"] is False
    # create_requirement：破坏性、串行
    assert by_name["create_requirement"]["is_destructive"] is True
    assert by_name["create_requirement"]["is_concurrency_safe"] is False
    # transfer_to_human：破坏性、但并发安全
    assert by_name["transfer_to_human"]["is_destructive"] is True
    assert by_name["transfer_to_human"]["is_concurrency_safe"] is True


def test_side_effects_invariant_rejects_contradiction():
    with pytest.raises(ValueError):
        SideEffects(is_read_only=True, is_destructive=True, is_concurrency_safe=True)


def test_schema_dual_use_blocks_bad_quantity():
    # quantity 必须正整数：0/负数/字符串都应被 Pydantic 在工具边界挡掉
    with pytest.raises(ValidationError):
        CreateRequirementArgs(item_name="轴承", item_url="x", quantity=0, project_code="IML001")
    with pytest.raises(ValidationError):
        CreateRequirementArgs(
            item_name="轴承", item_url="x", quantity="十个", project_code="IML001"
        )


def test_every_tool_declares_full_contract():
    for t in TOOLS:
        for key in ("is_read_only", "is_destructive", "is_concurrency_safe", "activity"):
            assert key in (t.extras or {}), f"{t.name} 缺契约字段 {key}"
