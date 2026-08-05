import pytest

from pipeline.content.higgsfield_loader import list_higgsfield_series, load_higgsfield_series
from pipeline.content.schema import ContentError


def test_list_higgsfield_series_finds_robi_le_robot():
    assert "robi_le_robot" in list_higgsfield_series()


def test_load_higgsfield_series_robi_le_robot():
    series = load_higgsfield_series("robi_le_robot")
    assert series.key == "robi_le_robot"
    assert series.voice == "fr_FR-siwis-medium"
    assert series.aspect_ratio in ("16:9", "9:16", "1:1")
    assert len(series.scenes) == 6
    assert series.scenes[0].narration
    assert series.scenes[0].prompt


def test_load_higgsfield_series_unknown_raises():
    with pytest.raises(ContentError):
        load_higgsfield_series("does_not_exist")


def test_load_higgsfield_series_malformed_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("higgsfield_series:\n  key: bad\nscenes: []\n", encoding="utf-8")
    with pytest.raises(ContentError):
        load_higgsfield_series("bad", data_dir=tmp_path)
