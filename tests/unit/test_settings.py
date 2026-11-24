import json

from eye_break.services.settings_service import (
    Settings,
    SettingsService,
    validate_break_seconds,
    validate_work_minutes,
)


def test_defaults():
    s = Settings()
    assert s.work_minutes == 30
    assert s.break_seconds == 30
    assert s.overlay_opacity == 90
    assert all(not r["enabled"] for r in s.reminders.values())
    assert not s.sound_break_start


def test_custom_interval_validation():
    assert validate_work_minutes("1") == 1
    assert validate_work_minutes("180") == 180
    assert validate_work_minutes(" 45 ") == 45
    assert validate_work_minutes("0") is None
    assert validate_work_minutes("181") is None
    assert validate_work_minutes("abc") is None
    assert validate_work_minutes("") is None


def test_custom_break_validation():
    assert validate_break_seconds("10") == 10
    assert validate_break_seconds("3600") == 3600
    assert validate_break_seconds("9") is None
    assert validate_break_seconds("3601") is None
    assert validate_break_seconds("1.5") is None


def test_invalid_fields_fall_back_to_defaults():
    s = Settings.from_dict({
        "work_minutes": 999,
        "break_seconds": "thirty",
        "mode": "evil",
        "overlay_opacity": 20,
        "sound_break_end": "yes",
        "custom_quotes": ["  Rest well  ", "", 5, "Rest well"],
        "quote_categories": ["eyes", "bogus"],
        "reminders": {"water": {"enabled": True, "minutes": 1}},
        "idle_threshold_minutes": 10,
        "idle_reset_minutes": 2,
    })
    assert s.work_minutes == 30
    assert s.break_seconds == 30
    assert s.mode == "gentle"
    assert s.overlay_opacity == 90
    assert s.sound_break_end is False
    assert s.custom_quotes == ["Rest well"]
    assert s.quote_categories == ["eyes"]
    assert s.reminders["water"] == {"enabled": True, "minutes": 60}
    assert s.idle_reset_minutes == 10


def test_bool_is_not_accepted_as_int():
    assert Settings.from_dict({"work_minutes": True}).work_minutes == 30


def test_persistence_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    svc = SettingsService(path)
    svc.settings.work_minutes = 45
    svc.settings.theme = "dark"
    svc.save()
    again = SettingsService(path)
    assert again.settings.work_minutes == 45
    assert again.settings.theme == "dark"
    assert not path.with_suffix(".json.tmp").exists()


def test_corrupt_settings_recovered(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    svc = SettingsService(path)
    assert svc.settings == Settings()
    assert not path.exists()
    assert list(tmp_path.glob("settings.corrupt-*.json"))
    svc.save()
    assert json.loads(path.read_text())["work_minutes"] == 30


def test_non_dict_json_gives_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert SettingsService(path).settings == Settings()
