# Development progress

| Phase | Status | Notes |
|---|---|---|
| 1. Foundation | Done | uv project, validated settings with corruption recovery, scheduler state machine, SQLite + migrations, statistics, quote rotation |
| 2. Core break experience | Done | Per-monitor overlay with separate background alpha, countdown, quotes, skip/snooze/confirm, strict-mode emergency exit, monitor rebuild |
| 3. Desktop interface | Done | Token-based QSS design system, light/dark/system themes, 7 pages, live overlay preview, screenshots reviewed |
| 4. Windows integration | Done | Tray, single instance (+ `--quit`), idle/lock/presentation detection, HKCU startup, meeting mode, sleep-gap handling |
| 5. Statistics & extras | Done | Charts, streaks, CSV export, custom quotes, notifications, sounds, secondary reminders |
| 6. Quality assurance | Done | 90 automated tests, real-desktop smoke and soak tests, CPU/RAM measured; see TESTING.md |
| 7. Packaging | Done | PyInstaller one-folder build, Inno Setup per-user installer; install/uninstall verified silently |

## Bugs found and fixed during QA

- The global QSS font rule overrode the overlay's large quote and countdown fonts.
- Database corruption recovery leaked a file handle, so the corrupt file couldn't be moved aside on Windows.
- Tray submenus ("Pause for", "Meeting mode") could be garbage-collected.
- Single-instance messages could be lost, and a teardown race could crash.
- Lambda connections from pages outlived the pages once the dashboard became releasable.
- The development clock at high speed was mistaken for system sleep.
- The chart legend was duplicated after a theme change; the checked segment label was clipped; stat tiles were misaligned.
- Background memory dropped from 128 MB to 52 MB working set after making the dashboard on-demand.
