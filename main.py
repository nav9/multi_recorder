import sys
import logging
from PyQt6.QtWidgets import QApplication
from gui import MainWindow

# --- Basic Logger Configuration ---
class QtLogHandler(logging.Handler):
    """A logging handler that emits a signal for each record."""
    def __init__(self, log_signal):
        super().__init__()
        self.log_signal = log_signal

    def emit(self, record):
        msg = self.format(record)
        self.log_signal.emit(msg + '\n')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    
    # --- FIX: Set up the custom log handler ---
    log_handler = QtLogHandler(window.app_log_signal)
    log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    log_handler.setFormatter(log_format)
    
    # Add the handler to the root logger
    logging.getLogger().addHandler(log_handler)
    logging.getLogger().setLevel(logging.INFO)

    window.show()
    logging.info("Application started and logging is configured.")
    sys.exit(app.exec())