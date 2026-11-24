# Release notes

## 1.0.0

First public release.

- A full-screen break overlay on every monitor, with an adjustable dim level and fully opaque text.
- Configurable work intervals (1–180 min) and break durations (10 s–60 min), applied live.
- Gentle, Focus and Strict modes, with a documented emergency exit in Strict mode.
- Idle, lock and sleep detection; reliable elapsed-time scheduling.
- System tray with pause, snooze and meeting mode; optional automatic pause during full-screen apps.
- Local statistics with charts, streaks, CSV export and deletion.
- 106 original quotations in 7 categories, plus your own.
- Light, dark and system themes; 6 accent colours; live overlay preview.
- Optional notifications, soft sounds and secondary health reminders.
- Per-user start with Windows; single instance; per-user installer and uninstaller.

### Known limitations

- The executable and installer are **not code-signed**, so SmartScreen may show an "unknown
  publisher" warning.
- Automatic meeting detection relies on Windows' notification state (full-screen apps, D3D games,
  presentation mode). It does not detect windowed video calls; use manual Meeting mode for those.
- Windows restricts background apps from taking keyboard focus. If the strict-mode Esc hold doesn't
  respond, click the overlay first or use the tray's **End break now (emergency)**.
- Notification appearance depends on Windows notification settings (Focus Assist can hide them).

## Release checklist

1. Bump the version in `pyproject.toml`, `src/eye_break/__init__.py`, `packaging/version_info.txt`
   and `packaging/installer.iss`.
2. Run `powershell -ExecutionPolicy Bypass -File scripts\build.ps1`.
3. Run `uv run python scripts/smoke_test.py --exe dist\EyeBreak\EyeBreak.exe`.
4. Install `packaging\output\EyeBreak-<version>-Setup.exe`, launch it, then uninstall it.
5. Tag the commit as `v<version>`.
