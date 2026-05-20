import os
import subprocess
import sys
from pathlib import Path

if getattr(sys, "frozen", False) and "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
    _localappdata = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local"
    )
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(_localappdata, "ms-playwright")

if getattr(sys, "frozen", False) and len(sys.argv) >= 3 and sys.argv[1] == "--orbit-wrapper":
    # Rewrite argv so orbit_wrapper.main() sees: argv[0]=exe, argv[1]=script_path
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    from orbit360.backend.orbit_wrapper import main as _wrapper_main
    _wrapper_main()
    sys.exit(0)
# ─────────────────────────────────────────────────────────────────────────────

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QProgressBar, QVBoxLayout

from orbit360.ui.main_window import Ready360Window
from orbit360.utils.utils import load_dotenv


# ── Playwright browser check / auto-install ───────────────────────────────────

def _playwright_cmd(*args: str) -> list[str]:
    from playwright._impl._driver import compute_driver_executable
    node_exe, cli_js = compute_driver_executable()
    return [node_exe, cli_js, *args]


def _chromium_installed() -> bool:
    try:
        result = subprocess.run(
            _playwright_cmd("install", "chromium", "--dry-run"),
            capture_output=True, text=True, timeout=15,
        )
        # --dry-run exits 0 with no output on either stream when already installed.
        # Playwright writes its "please install" notice to stderr in newer versions,
        # so check both streams — any output means the browser is missing.
        combined = (result.stdout + result.stderr).strip()
        return result.returncode == 0 and not combined
    except Exception:
        return False

class _InstallWorker(QThread):
    finished = Signal(bool, str)   # success, error_message

    def run(self):
        try:
            result = subprocess.run(
                _playwright_cmd("install", "chromium"),
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, result.stderr.strip() or result.stdout.strip())
        except Exception as exc:
            self.finished.emit(False, str(exc))

class _BrowserSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Orbit360 — First-Time Setup")
        self.setFixedSize(400, 120)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint
        )
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        self._label = QLabel("Installing Chromium browser (one-time setup)…")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)   # indeterminate / pulsing
        self._bar.setTextVisible(False)
        layout.addWidget(self._bar)

        self._worker = _InstallWorker(self)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_done(self, success: bool, error: str) -> None:
        if success:
            self.accept()
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Browser Install Failed",
                f"Chromium could not be installed automatically.\n\n{error}\n\n"
                "You can install it manually by running:\n  playwright install chromium",
            )
            self.reject()

def _ensure_chromium(app: QApplication) -> None:
    if _chromium_installed():
        return
    dlg = _BrowserSetupDialog()
    dlg.exec()   # blocks until install finishes (or fails with a message)

# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    load_dotenv()

    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QApplication(sys.argv)

    # styles.qss lives alongside this file (project root in dev, sys._MEIPASS in frozen)
    style_path = Path(__file__).with_name("styles.qss")
    if style_path.exists():
        with open(style_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    _ensure_chromium(app)

    w = Ready360Window()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
