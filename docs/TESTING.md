# Testing and verification report

Environment: Windows 11 Pro (build 22000), 4 logical CPUs, one 1366×768 display, no dedicated
GPU, Python 3.12.1, PySide6 6.10.3. Measured on 2026-11-24.

## 1. Automated tests: 90 passed

`uv run pytest`: **90 passed in 8.8 s**

| Suite | Tests | Kind |
|---|---|---|
| `tests/unit` | 63 | Pure logic with an injectable `FakeClock`; no waiting. |
| `tests/integration` | 11 | Real SQLite/JSON on disk, the full app wiring, **real Win32 calls** (idle time, lock state, presentation state, HKCU Run key round trip on a test-only value name), and a real second process for single-instance checks. |
| `tests/ui` | 16 | Real Qt widgets on a headless platform with **two simulated monitors** (one at 150% scaling), with mocked OS probes and a fake clock. |

Coverage of the requested areas:

| Area | Tests |
|---|---|
| Work timer accuracy, elapsed-time (not tick count) tracking | `test_break_triggers_exactly_at_interval`, `test_timer_uses_elapsed_time_not_tick_count` |
| Break countdown accuracy | `test_break_countdown_completes_and_resets_session`, `test_break_covers_every_monitor_and_dismisses_itself` |
| Custom interval/duration validation | `test_custom_interval_validation`, `test_custom_break_validation`, `test_invalid_fields_fall_back_to_defaults` |
| Pause/resume, timed pause, until tomorrow | `test_pause_and_resume_keeps_elapsed`, `test_timed_pause_expires`, `test_pause_until_tomorrow_uses_wall_clock` |
| Snooze (gentle unlimited, focus limited, tray snooze) | `test_snooze_*`, `test_focus_mode_limits_snoozes`, `test_tray_snooze_while_working_pushes_break_back`, `test_focus_mode_snooze_limit_and_confirmed_skip` |
| Skip and confirmation | `test_skip_requires_confirmation_flag`, `test_focus_mode_snooze_limit_and_confirmed_skip` |
| Strict mode and emergency exit | `test_strict_mode_blocks_skip_and_snooze_but_allows_emergency`, `test_strict_mode_hides_controls_and_emergency_exit_works`, `test_releasing_esc_early_cancels_emergency` |
| Idle transitions and reset | `test_idle_pauses_timer_and_resumes`, `test_long_idle_resets_session_when_enabled`, `test_long_idle_does_not_reset_when_disabled` |
| Sleep/wake | `test_sleep_gap_not_counted_and_no_accumulated_breaks`, `test_short_sleep_gap_does_not_count_as_work`, `test_sleep_during_break_marks_interrupted` |
| Lock screen | `test_locked_session_never_triggers_break`, `test_locked_and_idle_never_show_overlay` |
| System clock changes | `test_wall_clock_change_does_not_affect_timer` |
| Meeting mode expiry and auto-detection | `test_meeting_mode_expires`, `test_meeting_until_manual_resume`, `test_auto_meeting_while_presenting` |
| Multiple-break prevention | `test_no_overlapping_breaks`, `test_no_overlapping_overlays`, `test_scheduled_break_not_started_while_paused` |
| Settings persistence and corruption recovery | `test_persistence_roundtrip`, `test_corrupt_settings_recovered`, `test_settings_persist_across_restart` |
| Database, migrations, corruption recovery | `test_migration_and_corrupt_db_recovery`, `test_history_persists_across_restart` |
| Statistics, streaks, periods, CSV | `tests/unit/test_statistics.py` |
| Quotation rotation | `tests/unit/test_quotes.py` |
| Application restart | `test_settings_persist_across_restart`, `test_history_persists_across_restart` |
| Single instance | `test_single_instance_enforced_across_processes` (real second process) |
| Overlay creation/dismissal, opacity separation | `test_background_alpha_is_separate_from_content` (pixel check: alpha 204 at 80%, window opacity 1.0) |
| Multiple monitors | `test_break_covers_every_monitor_and_dismisses_itself`, `test_primary_only_content`, `test_monitor_change_rebuilds_overlay` (simulated) |
| Repeated sessions, no window leaks | `test_repeated_breaks_do_not_leak_windows` (25 cycles) |
| No placeholder buttons | `test_no_button_is_a_placeholder` |
| Secondary reminders | `tests/unit/test_reminders.py` |

## 2. Real desktop smoke tests (not mocked)

`scripts/smoke_test.py` launches the app as a separate process with an isolated data folder and an
accelerated development clock. It inspects window metadata via Win32 and never captures the screen.
It was run against the source build, the PyInstaller executable, and the copy installed by the
installer. **All checks passed on all three:**

- A second launch exits immediately (single instance).
- A scheduled break opens a topmost, layered window exactly covering the monitor (`0,0,1366,768`).
- The overlay has no title bar.
- The overlay disappears automatically when the countdown ends.
- The completed break is recorded in SQLite.
- `--quit` shuts the app down cleanly (exit code 0).

**Soak test** (`--soak 100`, source build): 100 real overlay show/hide cycles completed. Private
memory was 57.0 MB at cycle 10, 57.0 MB at cycle 50 and 56.9 MB at cycle 100, so **no growth**.

## 3. Installer verification (real, silent mode)

`EyeBreak-1.0.0-Setup.exe /VERYSILENT /CURRENTUSER /TASKS=startup`: exit code 0.

- The exe, uninstaller, Start-menu shortcut and the "Eye Break 1.0.0" Apps entry were created;
  the file version is 1.0.0.
- The HKCU Run value was created with `--minimized`.
- The installed exe passed the full smoke test.
- With the installed app running, the silent uninstaller closed it (exit code 0) and removed the
  files, the shortcut, the Apps entry and the Run value. User data was kept, because the silent
  default answer to "delete settings and history?" is No.

Not verified: the interactive wizard pages and an installation with administrator rights
(all-users mode).

## 4. Performance (measured)

| Metric | Value |
|---|---|
| Background CPU (60 s window, tray mode, packaged exe) | 0.0% of one core (below `GetProcessTimes` resolution; source build measured 0.0–0.05%) |
| Background memory, packaged exe | 52.2 MB working set, **27.4 MB private** |
| Memory with the dashboard open | 133 MB working set, 67.7 MB private (released when the window is closed to the tray) |
| Start to visible dashboard, packaged exe | 2.3–3.0 s (3 runs) |
| Portable app size / installer size | 65 MB / 20.3 MB |

The 100 MB target is met while running in the background, which is the normal state for this app.
It is exceeded only while the dashboard window is open. The working set includes shared Qt DLL pages.

## 5. Requires manual verification

These could not be automated in this environment:

- **A physical multi-monitor setup** and monitor hot-plug. The logic is tested with simulated monitors;
  this machine has a single display.
- **Real sleep/hibernate and lock/unlock cycles.** The logic is unit-tested and the lock and idle
  Win32 queries are tested live, but no actual suspend was performed.
- **Pressing and holding Esc on the real overlay**, and focus behaviour when another app is in the
  foreground. The hold logic is tested; the tray emergency action is always available.
- **Toast notification appearance and sounds playing audibly.** The calls are made, but the output was
  not observed.
- **Automatic presentation detection** with real PowerPoint/full-screen apps.
- **Start with Windows at an actual sign-in.** The registry value is verified; a real sign-in was not.
- **Windows "follow system theme" switching live.** The code listens to Qt's `colorSchemeChanged`.
- The interactive installer wizard and SmartScreen behaviour.
