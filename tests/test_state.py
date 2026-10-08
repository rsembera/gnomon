"""Remembered settings: round trip, bad files, atomic writes."""

import json

from core import state
from core.clockface import DEFAULT_HEIGHT, MAX_HEIGHT


def test_missing_file_gives_defaults(tmp_path):
    loaded = state.load(tmp_path / "state.json")
    assert loaded == state.State()
    assert loaded.x is None and loaded.height == DEFAULT_HEIGHT and loaded.scheme == "ink"
    assert loaded.alarm_end is None and loaded.warn_minutes == 5 and loaded.end_minute == 50


def test_round_trip(tmp_path):
    path = tmp_path / "nested" / "state.json"  # parent is created on save
    saved = state.State(
        x=663.0, y=872.0, height=28.0, scheme="amber", twenty_four=True,
        alarm_end=1_800_000_000.0, alarm_warn_acked=True, warn_minutes=2, end_minute=20,
    )
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
        json.dumps({
            "x": "left", "y": 100, "height": 99999, "scheme": "plaid", "twenty_four": False,
            "alarm_end": "soon", "alarm_warn_acked": True, "warn_minutes": 99, "end_minute": 75,
        }),
        encoding="utf-8",
    )
    loaded = state.load(path)
    assert loaded.x is None and loaded.y is None  # half a position is no position
    assert loaded.height == MAX_HEIGHT            # clamped, not rejected
    assert loaded.scheme == "ink"                 # unknown scheme: default kept
    assert loaded.twenty_four is False
    assert loaded.alarm_end is None               # no end time, so no alert ...
    assert loaded.alarm_warn_acked is False       # ... and nothing acknowledged
    assert loaded.warn_minutes == 5               # clamped to the maximum
    assert loaded.end_minute == 50                # not a minute of the hour: default


def test_a_1_0_state_file_keeps_its_appearance(tmp_path):
    # 1.0 stored {"dark": true|false}; paper users must not wake up in ink.
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"x": 1, "y": 2, "height": 40, "dark": False}), encoding="utf-8")
    assert state.load(path).scheme == "paper"
    path.write_text(json.dumps({"x": 1, "y": 2, "height": 40, "dark": True}), encoding="utf-8")
    assert state.load(path).scheme == "ink"


def test_a_1_1_0_scheme_name_is_carried_over(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"scheme": "terminal"}), encoding="utf-8")
    assert state.load(path).scheme == "green"
    path.write_text(json.dumps({"scheme": "crimson-veil"}), encoding="utf-8")
    assert state.load(path).scheme == "ink"


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
