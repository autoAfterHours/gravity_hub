# orbit360.spec — PyInstaller build specification for Orbit360
#
# Produces a --onedir bundle: a single folder (dist/orbit360/) containing
# orbit360.exe plus all runtime dependencies.
#
# HOW TO BUILD
# ------------
#   pip install pyinstaller pyinstaller-hooks-contrib
#   pyinstaller orbit360.spec
#
# The finished distribution lives at:
#   dist/orbit360/
#       orbit360.exe          ← launch this
#       _internal/            ← Qt libs, Python runtime, bundled assets
#           qml/
#           systems/
#           styles.qss
#           ...
#
# orbit_data/ is NOT included — it is created fresh next to the exe on first run.
# Users never see previous run data.

import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# ── Collect all PySide6 runtime assets (Qt DLLs, QML plugins, translations) ──
# collect_all picks up PySide6's data files, binaries, and hidden imports in one
# call.  This ensures Qt Quick, Qt Quick Controls, and QML engine plugins are
# all present in the bundle.
pyside6_datas, pyside6_binaries, pyside6_hidden = collect_all("PySide6")

# ── Collect Playwright driver binary ─────────────────────────────────────────
# Playwright ships a Node.js-based driver executable inside its package
# (playwright/driver/playwright.exe on Windows).  collect_all ensures that
# binary is copied into the bundle so compute_driver_executable() can find it
# at runtime — without this the auto-install fails with [WinError 2].
playwright_datas, playwright_binaries, playwright_hidden = collect_all("playwright")

a = Analysis(
    ["orbit360_gui.py"],
    pathex=["."],
    binaries=pyside6_binaries + playwright_binaries,
    datas=pyside6_datas + playwright_datas + [
        # Application assets — bundled into sys._MEIPASS
        ("qml",        "qml"),        # QML UI files
        ("styles.qss", "."),          # Qt stylesheet (goes to sys._MEIPASS root)
        ("systems",    "systems"),    # Test scripts (read-only; orbit_data NOT included)
    ],
    hiddenimports=pyside6_hidden + [
        # PySide6 modules required at runtime but sometimes missed by the analyser
        "PySide6.QtQuickWidgets",    # QQuickWidget
        "PySide6.QtWebEngineWidgets", # Phase 4+: WebEngineView
        "PySide6.QtWebChannel",      # Phase 4+: QWebChannel
        "shiboken6",                 # PySide6 C++ binding layer
        # Core application modules
        "core.cascade_bridge",
        "core.cascade_model",
        "core.event_bus",
        "core.executors",
        "core.executors.base",
        "core.executors.playwright_executor",
        "core.executors.powershell_executor",
        "core.executors.uipath_executor",
        "core.executors.sql_executor",
        "core.executors.registry",
        "core.history_db",
        "core.log_bridge",
        "core.log_model",
        "core.main_window",
        "core.models",
        "core.orbit_context",
        "core.orbit_logger",
        "core.orbit_wrapper",
        "core.paths",
        "core.qml_bridge",
        "core.screenshot_watcher",
        "core.script_sync",
        "core.script_template",
        "core.orbit_retry",
        "core.orbit_health",
        "core.orbit_page",
        "core.orbit_frames",
        "core.orbit_script_helpers",
        "core.orbit_report",
        "core.titlebar",
        "core.titlebar_bridge",
        "core.utils",
        "core.workers",
        # Third-party
        "yaml",
        "playwright",
        "playwright.sync_api",
        # Standard library modules sometimes missed by the static analyser
        "sqlite3",
        "concurrent.futures",
        "py_compile",
        "runpy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "orbit_data",   # user run data — never bundled
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "PyQt6",        # replaced by PySide6
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,      # onedir: binaries go into COLLECT, not the exe itself
    name="orbit360",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                   # compress where possible (requires UPX on PATH)
    upx_exclude=["vcruntime140.dll", "python*.dll", "Qt6*.dll"],
    console=False,              # no console window when launching GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="assets/orbit360.ico",  # uncomment and provide an .ico to add a custom icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime140.dll", "python*.dll", "Qt6*.dll"],
    name="orbit360",            # output folder: dist/orbit360/
)
