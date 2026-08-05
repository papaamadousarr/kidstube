import pytest

from pipeline.content.loader import list_series, load_series
from pipeline.content.schema import ContentError


def test_list_series_finds_alphabet_fr():
    assert "alphabet_fr" in list_series()


def test_load_series_alphabet_fr():
    series = load_series("alphabet_fr")
    assert series.key == "alphabet_fr"
    assert series.voice == "fr_FR-siwis-medium"
    assert len(series.items) >= 5
    assert series.items[0].name == "A"
    assert series.items[0].icon == "airplane"


def test_load_series_unknown_raises():
    with pytest.raises(ContentError):
        load_series("does_not_exist")


def test_load_series_malformed_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("series:\n  key: bad\nitems: []\n", encoding="utf-8")
    with pytest.raises(ContentError):
        load_series("bad", data_dir=tmp_path)
