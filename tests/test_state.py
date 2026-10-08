"""Remembered settings: round trip, bad files, atomic writes."""

import json

from core import state
from core.clockface import DEFAULT_HEIGHT, MAX_HEIGHT


def test_missing_file_gives_defaults(tmp_path):
    loaded = state.load(tmp_path / "state.json")
    assert loaded == state.State()
    assert loaded.x is None and loaded.height == DEFAULT_HEIGHT and loaded.dark is True


def test_round_trip(tmp_path):
    path = tmp_path / "nested" / "state.json"  # parent is created on save
    saved = state.State(x=663.0, y=872.0, height=28.0, dark=False, twenty_four=True)
    state.save(saved, path)
    assert state.load(path) == saved


def test_corrupt_file_gives_defaults(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    assert state.load(path) == state.State()


def test_wrong_shape_gives_defaults(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert state.load(path) == state.State()


def test_bad_fields_are_dropped_one_by_one(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"x": "left", "y": 100, "height": 99999, "dark": "yes", "twenty_four": False}),
        encoding="utf-8",
    )
    loaded = state.load(path)
    assert loaded.x is None and loaded.y is None  # half a position is no position
    assert loaded.height == MAX_HEIGHT            # clamped, not rejected
    assert loaded.dark is True                    # not a bool: default kept
    assert loaded.twenty_four is False


def test_non_finite_numbers_are_rejected(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"x": NaN, "y": Infinity, "height": NaN}', encoding="utf-8")
    loaded = state.load(path)
    assert loaded.x is None and loaded.height == DEFAULT_HEIGHT


def test_save_leaves_no_temp_files(tmp_path):
    path = tmp_path / "state.json"
    state.save(state.State(x=1.0, y=2.0), path)
    state.save(state.State(x=3.0, y=4.0), path)
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_data_dir_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GNOMON_DATA_DIR", str(tmp_path))
    assert state.data_dir() == tmp_path
    monkeypatch.delenv("GNOMON_DATA_DIR")
    assert state.data_dir().parts[-3:] == ("Library", "Application Support", "Gnomon")
