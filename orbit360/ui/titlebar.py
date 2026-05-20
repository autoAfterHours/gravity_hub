from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel


class OutlinedLabel(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._outline_color = QColor(0, 0, 0)
        self._outline_width = 2  # crisp outline

    def set_outline(self, color: QColor, width: int = 2):
        self._outline_color = color
        self._outline_width = max(1, int(width))
        self.update()

    def paintEvent(self, event):
        # Custom paint to draw text outline + fill
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        text = self.text()
        if not text:
            return

        rect = self.rect()
        flags = int(self.alignment()) | int(Qt.TextFlag.TextSingleLine)

        font = self.font()
        painter.setFont(font)

        # Outline
        pen = QPen(self._outline_color)
        pen.setWidth(self._outline_width)
        painter.setPen(pen)
        painter.drawText(rect, flags, text)

        # Fill
        painter.setPen(self.palette().windowText().color())
        painter.drawText(rect, flags, text)


class TitleBar(QFrame):
    def __init__(self, title="Orbit360", subtitle=None, dark_mode=False):
        super().__init__()
        self.setObjectName("TitleBar")

        layout = QVBoxLayout(self)
        # Reduce vertical padding to remove the 'white box' feeling and keep bar tight
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(2)

        self.setStyleSheet("""
            QFrame#TitleBar {
                background-color: #003087;
                border: none;
                border-radius: 0px;
            }
        """)

        self.title = OutlinedLabel(title)
        self.title.setObjectName("TitleBarTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        font = QFont()
        font.setBold(True)
        font.setPointSize(26)
        self.title.setFont(font)

        # Orange fill + transparent background
        self.title.setStyleSheet("""
            QLabel#TitleBarTitle {
                color: #ff6600;
                background: transparent;
                letter-spacing: 1px;
            }
        """)

        # Sharp black outline
        self.title.set_outline(QColor(0, 0, 0), width=2)

        layout.addWidget(self.title)
