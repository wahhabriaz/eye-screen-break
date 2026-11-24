# PyInstaller spec for Eye Break (one-folder build: fast startup, packaged by Inno Setup).
# Build: uv run pyinstaller packaging/eye_break.spec --noconfirm --distpath dist --workpath build
from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
ASSETS = SRC / "eye_break" / "assets"

# Qt modules Eye Break never imports; excluding keeps the bundle small.
EXCLUDES = [
    "tkinter", "unittest", "pydoc", "doctest", "pytest", "pytestqt", "PyInstaller", "setuptools", "pip",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtXml", "PySide6.QtDBus", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtPrintSupport", "PySide6.QtConcurrent", "PySide6.QtUiTools",
    "PySide6.QtSvgWidgets", "PySide6.QtNetworkAuth", "PySide6.QtWebSockets", "PySide6.QtHttpServer",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(SRC)],
    datas=[(str(ASSETS), "eye_break/assets")],
    hiddenimports=[],
    excludes=EXCLUDES,
    noarchive=False,
)

# Drop large runtime pieces the app does not use (software OpenGL, Qt translations, unused plugins).
DROP = ("opengl32sw.dll", "translations", "qtvirtualkeyboard", "qwebp", "qtiff", "qwbmp", "qtga", "qicns",
        "qpdf", "qjpeg", "qgif", "qnetworklistmanager", "qcertonlybackend", "qopensslbackend", "qschannelbackend")
a.binaries = [b for b in a.binaries if not any(d in b[0].lower() for d in DROP)]
a.datas = [d for d in a.datas if not any(x in d[0].lower() for x in DROP)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EyeBreak",
    console=False,
    icon=str(ASSETS / "icons" / "app.ico"),
    version=str(ROOT / "packaging" / "version_info.txt"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="EyeBreak", upx=False)
