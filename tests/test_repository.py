"""第 2 块·数据层：seed 命中、DATA_SOURCE 切换、real 缺文件清晰报错。"""
import pytest

from agent.data import get_repository
from agent.data.seed import SeedRepository


def test_seed_search_hits_and_misses():
    repo = SeedRepository()
    assert [r.item_name for r in repo.search_history("我要买几个轴承")]
    assert repo.search_history("买一台五轴加工中心") == []


def test_record_model_facing_is_compact():
    rec = SeedRepository().search_history("轴承")[0]
    text = rec.to_model_facing()
    assert "|" in text and rec.url in text  # 精简单行、含链接


def test_factory_defaults_to_seed(monkeypatch):
    monkeypatch.delenv("DATA_SOURCE", raising=False)
    assert isinstance(get_repository(), SeedRepository)


def test_factory_real_missing_file_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_SOURCE", "real")
    monkeypatch.setenv("REAL_DATA_PATH", str(tmp_path / "nope.json"))
    with pytest.raises(FileNotFoundError):
        get_repository()


def test_factory_unknown_source_errors(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "mars")
    with pytest.raises(ValueError):
        get_repository()
