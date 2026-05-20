from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton

class OrbitInputDialog(QDialog):
    def __init__(self, fields, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Input Required")

        self.inputs = {}
        layout = QVBoxLayout()

        self.fields = {}
        for field in fields:
            label = QLabel(field)
            textbox = QLineEdit()
            self.fields[field.lower()] = textbox

            layout.addWidget(label)
            layout.addWidget(textbox)

        submit_btn = QPushButton("Submit")
        submit_btn.clicked.connect(self.submit)

        layout.addWidget(submit_btn)
        self.setLayout(layout)

    def submit(self):
        for key, field in self.fields.items():
            self.inputs[key] = field.text().strip()
        self.accept()