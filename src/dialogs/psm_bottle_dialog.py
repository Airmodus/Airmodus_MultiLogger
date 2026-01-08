"""
PSM Bottle Setup Dialog

Prompts user to confirm whether liquid bottles are connected to the PSM.
This ensures proper device operation and prevents running the device dry.
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton)
from PyQt5.QtCore import Qt


class PSMBottleDialog(QDialog):
    """
    Dialog asking if PSM liquid bottles are connected.

    Returns:
        True if user clicks "Yes, bottles connected"
        False if user clicks "No, run in idle mode"
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PSM Liquid Bottles Setup")
        self.setModal(True)
        self.setMinimumWidth(350)

        self._bottles_connected = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Question text
        question = QLabel("Are the liquid bottles connected to the PSM?")
        question.setStyleSheet("font-size: 14px; font-weight: bold;")
        question.setWordWrap(True)
        layout.addWidget(question)

        # Warning text
        warning = QLabel(
            "Running without bottles may damage the device.\n\n"
            "Select 'Idle mode' if bottles are not connected - "
            "this will run the PSM at minimal flow to prevent damage."
        )
        warning.setStyleSheet("font-size: 12px; color: #888;")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        layout.addSpacing(8)

        # Yes button - bottles connected
        yes_btn = QPushButton("Yes, bottles connected")
        yes_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 12px 24px;
                font-size: 13px;
                font-weight: bold;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        yes_btn.clicked.connect(self._on_yes)
        layout.addWidget(yes_btn)

        # No button - idle mode
        no_btn = QPushButton("No, run in idle mode")
        no_btn.setStyleSheet("""
            QPushButton {
                background-color: #666;
                color: white;
                padding: 12px 24px;
                font-size: 13px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #555;
            }
        """)
        no_btn.clicked.connect(self._on_no)
        layout.addWidget(no_btn)

    def _on_yes(self):
        self._bottles_connected = True
        self.accept()

    def _on_no(self):
        self._bottles_connected = False
        self.accept()

    def bottles_connected(self) -> bool:
        """Return whether user indicated bottles are connected."""
        return self._bottles_connected
