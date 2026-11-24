"""Generate the app icon (.ico/.png) and the soft notification sounds (.wav).

All assets are original and generated here, so there are no third-party licensing concerns.
Run: uv run python scripts/make_assets.py
"""

from __future__ import annotations

import io
import math
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from eye_break.ui.icons import logo_pixmap  # noqa: E402

ASSETS = ROOT / "src" / "eye_break" / "assets"
RATE = 44100


def write_ico(path: Path, sizes: list[int]) -> None:
    images = []
    for size in sizes:
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        logo_pixmap(size).save(buf, "PNG")
        images.append((size, bytes(buf.data())))
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    path.write_bytes(header + entries + blobs)


def tone(notes: list[tuple[float, float]], volume: float = 0.18) -> bytes:
    """Soft sine chime: each note (frequency, seconds) with a smooth attack and long decay."""
    out = io.BytesIO()
    for freq, seconds in notes:
        count = int(RATE * seconds)
        for i in range(count):
            t = i / RATE
            env = min(1.0, t / 0.015) * math.exp(-4.0 * t / seconds)
            sample = math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(4 * math.pi * freq * t)
            out.write(struct.pack("<h", int(32767 * volume * env * sample / 1.25)))
    return out.getvalue()


def write_wav(path: Path, frames: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 - required for QPixmap
    (ASSETS / "icons").mkdir(parents=True, exist_ok=True)
    (ASSETS / "sounds").mkdir(parents=True, exist_ok=True)
    write_ico(ASSETS / "icons" / "app.ico", [16, 20, 24, 32, 40, 48, 64, 128, 256])
    logo_pixmap(512).save(str(ASSETS / "icons" / "app.png"), "PNG")
    write_wav(ASSETS / "sounds" / "pre_break.wav", tone([(659.25, 0.45)]))
    write_wav(ASSETS / "sounds" / "break_start.wav", tone([(523.25, 0.35), (659.25, 0.6)]))
    write_wav(ASSETS / "sounds" / "break_end.wav", tone([(659.25, 0.3), (783.99, 0.3), (1046.5, 0.7)]))
    print("Assets written to", ASSETS)


if __name__ == "__main__":
    main()
