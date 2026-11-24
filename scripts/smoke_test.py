"""Real-desktop smoke test + resource measurement (Windows only).

Launches Eye Break as a separate process with an isolated data folder and verifies, via the
Win32 API (window metadata only - no screen capture):
  1. a scheduled break opens topmost, layered, borderless windows covering every monitor;
  2. the overlay disappears on its own and a completed break is written to SQLite;
  3. a second launch exits immediately (single instance) and `--quit` stops the app cleanly;
  4. CPU and memory use while running normally in the background.

Usage:
  uv run python scripts/smoke_test.py                 # test the source build
  uv run python scripts/smoke_test.py --exe dist\\EyeBreak\\EyeBreak.exe
  add --perf-seconds N to change the measurement window (default 60)
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CAPTION = 0x00C00000
WS_EX_TOPMOST, WS_EX_LAYERED = 0x00000008, 0x00080000
PROCESS_QUERY_INFORMATION, PROCESS_VM_READ = 0x0400, 0x0010
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.GetWindowLongW.restype = ctypes.c_long


class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t)]


def monitors() -> list[tuple[int, int, int, int]]:
    rects: list[tuple[int, int, int, int]] = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                              wintypes.LPARAM)

    def cb(_h, _dc, rect, _lp):
        r = rect.contents
        rects.append((r.left, r.top, r.right, r.bottom))
        return True

    user32.EnumDisplayMonitors(None, None, proc(cb), 0)
    return rects


def overlay_windows(pid: int) -> list[dict]:
    found: list[dict] = []

    def cb(hwnd, _lp):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        style = user32.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        found.append({"rect": (r.left, r.top, r.right, r.bottom), "topmost": bool(ex & WS_EX_TOPMOST),
                      "layered": bool(ex & WS_EX_LAYERED), "caption": bool(style & WS_CAPTION)})
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return [w for w in found if w["topmost"] and w["layered"]]


def process_stats(pid: int) -> tuple[float, int, int]:
    """(cpu seconds, working set bytes, private bytes)"""
    h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    try:
        c, e, k, u = (wintypes.FILETIME() for _ in range(4))
        kernel32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u))
        cpu = ((k.dwHighDateTime << 32 | k.dwLowDateTime) + (u.dwHighDateTime << 32 | u.dwLowDateTime)) / 1e7
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
        return cpu, pmc.WorkingSetSize, pmc.PrivateUsage
    finally:
        kernel32.CloseHandle(h)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


def app_pid(pid: int) -> int:
    """A venv's python.exe is a launcher that re-spawns the real interpreter; follow it to the child."""
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    child = None
    try:
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.th32ParentProcessID == pid and entry.szExeFile.lower().startswith("python"):
                child = entry.th32ProcessID
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return child or pid


def command(exe: str | None, *args: str) -> list[str]:
    if exe:
        return [exe, *args]
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return [str(pythonw if pythonw.exists() else sys.executable), str(ROOT / "main.py"), *args]


def wait_for(predicate, timeout: float, interval: float = 0.1):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return None


def soak(exe: str | None, cycles: int, checks: list[tuple[str, bool]]) -> dict:
    """Run many real overlay show/hide cycles (accelerated clock) and compare memory over time."""
    data = Path(tempfile.mkdtemp(prefix="eyebreak-soak-"))
    (data / "settings.json").write_text(json.dumps({
        "work_minutes": 1, "break_seconds": 10, "fade_ms": 0, "mode": "focus", "notify_before_seconds": 0,
        "start_minimized": True, "idle_threshold_minutes": 60}), encoding="utf-8")
    proc = subprocess.Popen(command(exe, "--data-dir", str(data), "--minimized", "--dev-speed", "120"))
    db = data / "history.db"
    marks: dict[int, float] = {}
    try:
        time.sleep(3)
        pid = app_pid(proc.pid)
        deadline = time.monotonic() + cycles * 6 + 60
        done = 0
        while done < cycles and time.monotonic() < deadline:
            time.sleep(1)
            with sqlite3.connect(db) as conn:
                done = conn.execute("SELECT COUNT(*) FROM breaks").fetchone()[0]
            for mark in (10, cycles // 2, cycles):
                if done >= mark and mark not in marks:
                    marks[mark] = process_stats(pid)[2] / 2**20
        subprocess.run(command(exe, "--data-dir", str(data), "--quit"), timeout=30)
        proc.wait(timeout=15)
    finally:
        if proc.poll() is None:
            proc.kill()
    growth = marks.get(cycles, 0) - marks.get(10, 0)
    checks.append((f"{cycles} real break cycles completed", done >= cycles))
    checks.append(("private memory growth after warm-up under 10 MB", done >= cycles and growth < 10))
    return {"cycles": done, "private_mb_at_cycle": {k: round(v, 1) for k, v in marks.items()},
            "growth_mb_after_warmup": round(growth, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe")
    ap.add_argument("--perf-seconds", type=int, default=60)
    ap.add_argument("--soak", type=int, default=0, help="also run N rapid real break cycles and track memory")
    opts = ap.parse_args()
    if opts.exe:
        opts.exe = str(Path(opts.exe).resolve())
    results: dict[str, object] = {"target": opts.exe or "source (python main.py)"}
    checks: list[tuple[str, bool]] = []

    # ---- functional run (accelerated clock: 1-minute interval at 5x = 12 s; 20 s break = 4 s)
    data = Path(tempfile.mkdtemp(prefix="eyebreak-smoke-"))
    (data / "settings.json").write_text(json.dumps({
        "work_minutes": 1, "break_seconds": 20, "fade_ms": 200, "mode": "focus", "notify_before_seconds": 0,
        "start_minimized": True, "idle_threshold_minutes": 60}), encoding="utf-8")
    base = ["--data-dir", str(data)]
    proc = subprocess.Popen(command(opts.exe, *base, "--minimized", "--dev-speed", "5"))
    try:
        time.sleep(3)
        pid = app_pid(proc.pid)
        second = subprocess.run(command(opts.exe, *base), timeout=30)
        checks.append(("second launch exits immediately (single instance)", second.returncode == 0
                       and proc.poll() is None))
        screens = monitors()
        windows = wait_for(lambda: overlay_windows(pid) if len(overlay_windows(pid)) >= len(screens)
                           else None, timeout=30, interval=0.05)
        results["monitors"] = screens
        results["overlay_windows"] = windows
        covered = bool(windows) and all(any(w["rect"] == s for w in windows) for s in screens)
        checks.append(("overlay appears on every monitor, topmost + layered", covered))
        checks.append(("overlay has no title bar", bool(windows) and not any(w["caption"] for w in windows)))
        gone = wait_for(lambda: not overlay_windows(pid), timeout=30)
        checks.append(("overlay disappears automatically", bool(gone)))
        time.sleep(0.5)
        with sqlite3.connect(data / "history.db") as conn:
            rows = conn.execute("SELECT outcome, actual_seconds FROM breaks").fetchall()
        results["recorded_breaks"] = rows
        checks.append(("completed break recorded in SQLite", bool(rows) and rows[0][0] == "completed"))
        subprocess.run(command(opts.exe, *base, "--quit"), timeout=30)
        try:
            proc.wait(timeout=15)
            checks.append(("--quit shuts down cleanly", proc.returncode == 0))
        except subprocess.TimeoutExpired:
            checks.append(("--quit shuts down cleanly", False))
    finally:
        if proc.poll() is None:
            proc.kill()

    # ---- performance run (real clock, background/tray mode)
    data2 = Path(tempfile.mkdtemp(prefix="eyebreak-perf-"))
    (data2 / "settings.json").write_text(json.dumps({"start_minimized": True}), encoding="utf-8")
    t0 = time.perf_counter()
    perf = subprocess.Popen(command(opts.exe, "--data-dir", str(data2), "--minimized"))
    try:
        time.sleep(8)  # let startup settle
        pid = app_pid(perf.pid)
        cpu0, _, _ = process_stats(pid)
        w0 = time.perf_counter()
        samples = []
        for _ in range(opts.perf_seconds):
            time.sleep(1)
            samples.append(process_stats(pid))
        cpu1, ws, private = samples[-1]
        elapsed = time.perf_counter() - w0
        results["performance"] = {
            "window_seconds": round(elapsed, 1),
            "avg_cpu_percent_of_one_core": round(100 * (cpu1 - cpu0) / elapsed, 3),
            "working_set_mb": round(ws / 2**20, 1),
            "peak_working_set_mb": round(max(s[1] for s in samples) / 2**20, 1),
            "private_bytes_mb": round(private / 2**20, 1),
            "logical_cpus": __import__("os").cpu_count(),
            "startup_to_measure_s": round(w0 - t0, 1),
        }
        subprocess.run(command(opts.exe, "--data-dir", str(data2), "--quit"), timeout=30)
        perf.wait(timeout=15)
    finally:
        if perf.poll() is None:
            perf.kill()

    if opts.soak:
        results["soak"] = soak(opts.exe, opts.soak, checks)

    results["checks"] = [{"check": c, "passed": ok} for c, ok in checks]
    print(json.dumps(results, indent=2))
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
