import sys
import logging
from PyQt6.QtWidgets import QApplication
from gui import MainWindow

# --- Basic Logger Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())