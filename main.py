import sys
import atexit
import psutil
import logging
import traceback
import functools
from PyQt6.QtWidgets import QApplication, QMessageBox
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

# A global list to track all active PIDs
# This is crucial for the atexit cleanup function
ALL_PIDS = set()

def cleanup_processes():
    """
    This function is registered with atexit and will be called on any exit.
    It ensures no FFmpeg processes are left behind.
    """
    if not ALL_PIDS:
        return
        
    logging.info(f"[ATExit Cleanup] Ensuring shutdown of {len(ALL_PIDS)} tracked PIDs.")
    for pid in list(ALL_PIDS):
        try:
            p = psutil.Process(pid)
            logging.warning(f"[ATExit Cleanup] Found orphaned process {pid}. Terminating.")
            p.kill()
        except psutil.NoSuchProcess:
            # Process already ended, which is good.
            pass
        except Exception as e:
            logging.error(f"[ATExit Cleanup] Error while cleaning up PID {pid}: {e}")

# Register the cleanup function to be called on exit
atexit.register(cleanup_processes)

def handle_exception(exc_type, exc_value, exc_traceback, window_instance):
    """Global exception hook to catch any uncaught exceptions."""
    logging.error("Unhandled exception caught!", exc_info=(exc_type, exc_value, exc_traceback))
    
    # Format the traceback for the user
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    error_message = (
        "The application has encountered a critical error and must close.\n\n"
        "All recordings have been stopped and any completed segments have been saved. "
        "Log files have been written to the last recording session folder for diagnosis.\n\n"
        f"Error Details:\n{tb_text}"
    )
    
    # --- Graceful Shutdown ---
    if window_instance and hasattr(window_instance, 'recorder') and window_instance.recorder:
        window_instance.recorder.stop()
        window_instance.save_logs_to_file()
        
    # Show the error to the user
    error_box = QMessageBox()
    error_box.setIcon(QMessageBox.Icon.Critical)
    error_box.setText(error_message)
    error_box.setWindowTitle("Critical Application Error")
    error_box.exec()
    
    # Exit the application
    sys.exit(1)



if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow(ALL_PIDS)

    # --- Set up the global exception hook ---
    # We use functools.partial to pass the window instance to our handler
    sys.excepthook = functools.partial(handle_exception, window_instance=window)

    # --- Set up the custom log handler ---
    log_handler = QtLogHandler(window.app_log_signal)
    log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    log_handler.setFormatter(log_format)
    
    # Add the handler to the root logger
    logging.getLogger().addHandler(log_handler)
    logging.getLogger().setLevel(logging.INFO)

    window.show()
    logging.info("Application started and logging is configured.")
    sys.exit(app.exec())