from eye_break.core.reminder_manager import ReminderManager


def cfg(**enabled_minutes):
    base = {k: {"enabled": False, "minutes": 60} for k in ("water", "stand", "stretch", "posture", "walk")}
    for kind, minutes in enabled_minutes.items():
        base[kind] = {"enabled": True, "minutes": minutes}
    return base


def run(rm, config, seconds, can=True, to_break=9999.0):
    fired = []
    for _ in range(seconds):
        kind = rm.tick(config, 1.0, can, to_break)
        if kind:
            fired.append(kind)
    return fired


def test_disabled_by_default_never_fire():
    assert run(ReminderManager(), cfg(), 10_000) == []


def test_fires_on_interval():
    rm = ReminderManager()
    assert run(rm, cfg(water=10), 600) == ["water"]
    assert run(rm, cfg(water=10), 600) == ["water"]


def test_not_during_break_or_just_before_one():
    rm = ReminderManager()
    c = cfg(water=5)
    assert run(rm, c, 400, can=False) == []
    assert run(rm, c, 10, to_break=60) == []
    assert run(rm, c, 1) == ["water"]


def test_spacing_between_reminders():
    rm = ReminderManager()
    fired = run(rm, cfg(water=5, stretch=5), 300)
    assert fired == [fired[0]]
    fired += run(rm, cfg(water=5, stretch=5), 120)
    assert sorted(fired) == ["stretch", "water"]


def test_idle_time_does_not_count():
    rm = ReminderManager()
    c = cfg(water=5)
    for _ in range(1000):
        rm.tick(c, 0.0, True, 9999)
    assert rm.elapsed["water"] == 0
