import io
import os
import time
import logging
import psutil
import qdarkstyle
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGroupBox, QCheckBox, QLabel, QRadioButton, QButtonGroup, QMessageBox, QDialog, QTextEdit)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QGuiApplication, QTextCursor
from device_manager import get_device_detector, Monitor, AudioDevice, Webcam
from recorder import Recorder

def adjust_rect_for_ffmpeg(rect: QRect) -> QRect:
    """Ensures the width and height of a QRect are even numbers."""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    w -= (w % 2)
    h -= (h % 2)
    return QRect(x, y, w, h)

class SelectionOverlay(QWidget):
    """A semi-transparent overlay widget for selecting a screen area."""
    area_selected = pyqtSignal(QRect)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(QGuiApplication.primaryScreen().virtualGeometry())
        self.begin = None
        self.end = None
        
    def paintEvent(self, event):
        if self.begin is None or self.end is None:
            return

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        
        selection_rect = QRect(self.begin, self.end).normalized()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(selection_rect, Qt.GlobalColor.transparent)
        
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(QPen(QColor(50, 200, 50), 2, Qt.PenStyle.SolidLine))
        painter.drawRect(selection_rect)
        
        painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        painter.setPen(QColor("white"))
        text = f"{selection_rect.width()} x {selection_rect.height()}"
        painter.drawText(selection_rect.bottomLeft() + QPoint(5, 20), text)

    def mousePressEvent(self, event):
        self.begin = event.pos()
        self.end = event.pos()
        self.update()

    def mouseMoveEvent(self, event):
        self.end = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        self.hide()
        selection_rect = QRect(self.begin, self.end).normalized()
        self.area_selected.emit(selection_rect)
        self.close()

class LogViewerDialog(QDialog):
    """A simple dialog to display real-time logs."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Logs & Terminal Output")
        self.setGeometry(150, 150, 700, 400)
        
        layout = QVBoxLayout(self)
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Courier", 9))
        self.log_display.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        layout.addWidget(self.log_display)
        self.setModal(False) # Allow interaction with main window

    def append_log(self, text):
        """Appends a line of text to the log display."""
        self.log_display.moveCursor(QTextCursor.MoveOperation.End)
        self.log_display.insertPlainText(text)
        self.log_display.moveCursor(QTextCursor.MoveOperation.End)

class LogReaderThread(QThread):
    """Reads a stream (stdout/stderr) from a process and emits lines as signals."""
    log_line_received = pyqtSignal(str)
    
    def __init__(self, stream):
        super().__init__()
        self.stream = stream
        self.running = True

    def run(self):
        # Use io.TextIOWrapper to handle decoding and newlines correctly
        with io.TextIOWrapper(self.stream, encoding="utf-8", errors='ignore') as text_stream:
            while self.running and not text_stream.closed:
                try:
                    line = text_stream.readline()
                    if line:
                        self.log_line_received.emit(line)
                    else:
                        break # End of stream
                except Exception:
                    break

    def stop(self):
        self.running = False

class ProcessMonitorThread(QThread):
    """Monitors running processes and reports their status."""
    process_status_update = pyqtSignal(int, str) # pid, status ('running', 'exited_ok', 'exited_error')

    def __init__(self, processes):
        super().__init__()
        self.processes = processes
        self.running = True

    def run(self):
        while self.running:
            for process, task_name in self.processes:
                if process.poll() is None:
                    # Process is still running
                    self.process_status_update.emit(process.pid, "running")
                else:
                    # Process has exited
                    status = "exited_ok" if process.returncode == 0 else "exited_error"
                    self.process_status_update.emit(process.pid, status)
            self.msleep(2000) # Check every 2 seconds

    def stop(self):
        self.running = False

class ResourceMonitorThread(QThread):
    """Monitors disk space and RAM, emitting a warning if they are low."""
    low_resource_warning = pyqtSignal(str)

    def __init__(self, path_to_monitor, ram_threshold_gb=0.5, disk_threshold_gb=1.0):
        super().__init__()
        self.running = True
        self.path = path_to_monitor
        self.ram_threshold = ram_threshold_gb * (1024**3)
        self.disk_threshold = disk_threshold_gb * (1024**3)
        self.disk_warning_sent = False
        self.ram_warning_sent = False

    def run(self):
        while self.running:
            # Check Disk Space
            if not self.disk_warning_sent:
                disk_usage = psutil.disk_usage(self.path)
                if disk_usage.free < self.disk_threshold:
                    self.low_resource_warning.emit(f"Disk space is critically low! Only {disk_usage.free / (1024**3):.2f} GB remaining.")
                    self.disk_warning_sent = True # Only warn once
            
            # Check RAM
            if not self.ram_warning_sent:
                ram = psutil.virtual_memory()
                if ram.available < self.ram_threshold:
                    self.low_resource_warning.emit(f"Available RAM is critically low! Only {ram.available / (1024**3):.2f} GB remaining.")
                    self.ram_warning_sent = True # Only warn once
            
            self.msleep(30000) # Check every 30 seconds

    def stop(self):
        self.running = False        

class MainWindow(QMainWindow):
    """The main application window."""
    app_log_signal = pyqtSignal(str)

    def __init__(self, global_pid_set):
        super().__init__()
        self.global_pids = global_pid_set
        self.setWindowTitle("Multi Recorder")
        self.setGeometry(100, 100, 550, 600)
        self.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt6'))

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)
        self.resource_monitor_thread = None
        self.app_log_viewer = LogViewerDialog(self)
        self.app_log_viewer.setWindowTitle("Application Logs")
        # --- Connect the new signal to the viewer's slot ---
        self.app_log_signal.connect(self.app_log_viewer.append_log)        
        self.ffmpeg_log_viewer = LogViewerDialog(self)
        self.ffmpeg_log_viewer.setWindowTitle("FFmpeg Terminal Output")
        self.log_reader_threads = []
        self.process_monitor_thread = None
        self.pid_to_widget_map = {}     

        self.detector = get_device_detector()
        self.monitors, self.audio_devices, self.webcams = [], [], []
        self.ui_widgets = {'monitors': {}, 'audio': [], 'webcams': []}
        self.recording_area = None
        self.is_recording = False
        self.recorder = None

        self._create_ui_sections()
        self.update_ui_with_devices(*self._get_current_devices())

    def _get_current_devices(self):
        return self.detector.detect_monitors(), self.detector.detect_audio_devices(), self.detector.detect_webcams()

    def _clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _create_ui_sections(self):
        self.monitor_group_box = QGroupBox("Screen Capture")
        self.monitor_layout = QVBoxLayout()
        self.monitor_group_box.setLayout(self.monitor_layout)
        
        self.audio_group_box = QGroupBox("Audio Devices")
        self.audio_layout = QVBoxLayout()
        self.audio_group_box.setLayout(self.audio_layout)

        self.webcam_group_box = QGroupBox("Webcams")
        self.webcam_layout = QVBoxLayout()
        self.webcam_group_box.setLayout(self.webcam_layout)

        # --- Create a dedicated layout for the action buttons ---
        action_layout = QHBoxLayout()
        app_logs_button = QPushButton("Show App Logs")
        app_logs_button.clicked.connect(self.app_log_viewer.show)
        ffmpeg_logs_button = QPushButton("Show FFmpeg Output")
        ffmpeg_logs_button.clicked.connect(self.ffmpeg_log_viewer.show)
        
        self.record_button = QPushButton(" Record")
        self.record_button.setFixedHeight(40)
        self.record_button.setIcon(self.style().standardIcon(getattr(self.style().StandardPixmap, "SP_MediaPlay")))
        self.record_button.clicked.connect(self.toggle_recording)

        action_layout.addWidget(app_logs_button)
        action_layout.addWidget(ffmpeg_logs_button)
        action_layout.addStretch()
        action_layout.addWidget(self.record_button)

        self.main_layout.addWidget(self.monitor_group_box)
        self.main_layout.addWidget(self.audio_group_box)
        self.main_layout.addWidget(self.webcam_group_box)
        self.main_layout.addStretch(1) # Pushes action bar to the bottom
        self.main_layout.addLayout(action_layout) # Add the entire layout, not individual buttons


    def update_ui_with_devices(self, monitors, audio_devices, webcams):
        self.monitors, self.audio_devices, self.webcams = monitors, audio_devices, webcams
        
        self._clear_layout(self.monitor_layout)
        self.ui_widgets['monitors'] = {}
        for monitor in self.monitors:
            self._add_monitor_widget(monitor)

        self._clear_layout(self.audio_layout)
        self.ui_widgets['audio'] = []
        for device in self.audio_devices:
            self._add_audio_widget(device)

        self._clear_layout(self.webcam_layout)
        self.ui_widgets['webcams'] = []
        for device in self.webcams:
            self._add_webcam_widget(device)

    def _add_monitor_widget(self, monitor):
        # --- FIX: Correctly defined the layout hierarchy for the monitor widget ---
        # A vertical layout for the entire monitor entry
        entry_layout = QVBoxLayout()
        entry_layout.setSpacing(2)

        # A horizontal layout for the top line (status icon + checkbox)
        top_line_layout = QHBoxLayout()
        status_label = QLabel("⚪")
        checkbox = QCheckBox(f"Screen {monitor.id}: {monitor.resolution[0]}x{monitor.resolution[1]}")
        checkbox.setChecked(monitor.is_primary)
        top_line_layout.addWidget(status_label)
        top_line_layout.addWidget(checkbox)
        top_line_layout.addStretch()
        
        # The widget for indented options
        options_widget = QWidget()
        options_layout = QHBoxLayout(options_widget)
        options_layout.setContentsMargins(20, 0, 0, 0) # Indent options
        
        rb_fullscreen = QRadioButton("Fullscreen")
        rb_fullscreen.setChecked(True)
        rb_area = QRadioButton("Select Area")
        btn_select_area = QPushButton("Select rectangle")
        btn_select_area.setVisible(False) # Hide initially
        btn_select_area.clicked.connect(lambda checked=False, mid=monitor.id: self.select_area(mid))
        rb_area.toggled.connect(btn_select_area.setVisible) # Show/hide on toggle
        
        rb_window = QRadioButton("Select Window")
        btn_select_window = QPushButton("Select application")
        btn_select_window.setVisible(False) # Hide initially
        btn_select_window.setEnabled(False) # For future implementation
        rb_window.toggled.connect(btn_select_window.setVisible)
        
        lbl_area_dims = QLabel("")

        options_layout.addWidget(rb_fullscreen)
        options_layout.addWidget(rb_area)
        options_layout.addWidget(btn_select_area)
        options_layout.addWidget(rb_window)
        options_layout.addWidget(btn_select_window)
        options_layout.addStretch()
        options_layout.addWidget(lbl_area_dims)

        checkbox.toggled.connect(options_widget.setEnabled)
        options_widget.setEnabled(checkbox.isChecked())
        
        # Store all widget references
        self.ui_widgets['monitors'][monitor.id] = {
            'checkbox': checkbox, 'rb_fullscreen': rb_fullscreen, 'rb_area': rb_area, 
            'label': lbl_area_dims, 'area_geo': None, 'status_label': status_label
        }

        # Add the created layouts to the main entry layout
        entry_layout.addLayout(top_line_layout)
        entry_layout.addWidget(options_widget)
        
        # Add the complete entry to the screen capture group box
        self.monitor_layout.addLayout(entry_layout)         

    def _add_audio_widget(self, device):
        # FIX: Removed commented-out old code for clarity
        widget_layout = QHBoxLayout()
        status_label = QLabel("⚪")
        checkbox = QCheckBox(device.name)
        if device.is_default or device.is_loopback:
            checkbox.setChecked(True)
        widget_layout.addWidget(status_label)
        widget_layout.addWidget(checkbox)
        widget_layout.addStretch()
        
        self.ui_widgets['audio'].append({'checkbox': checkbox, 'device': device, 'status_label': status_label})
        self.audio_layout.addLayout(widget_layout)

    def _add_webcam_widget(self, device):
        # FIX: Removed commented-out old code for clarity
        widget_layout = QHBoxLayout()
        status_label = QLabel("⚪")
        checkbox = QCheckBox(f"{device.name} ({device.status})")
        if device.status == "Active":
            checkbox.setChecked(True)
        widget_layout.addWidget(status_label)
        widget_layout.addWidget(checkbox)
        widget_layout.addStretch()
        
        self.ui_widgets['webcams'].append({'checkbox': checkbox, 'device': device, 'status_label': status_label})
        self.webcam_layout.addLayout(widget_layout)

    def select_area(self, monitor_id):
        self.active_selection_monitor_id = monitor_id
        self.selection_overlay = SelectionOverlay()
        self.selection_overlay.area_selected.connect(self.on_area_selected)
        self.selection_overlay.show()

    def on_area_selected(self, rect: QRect):
        adjusted_rect = adjust_rect_for_ffmpeg(rect)
        logging.info(f"Area selected and adjusted: {adjusted_rect.x()},{adjusted_rect.y()} {adjusted_rect.width()}x{adjusted_rect.height()}")
        
        widgets = self.ui_widgets['monitors'][self.active_selection_monitor_id]
        widgets['area_geo'] = (adjusted_rect.x(), adjusted_rect.y(), adjusted_rect.width(), adjusted_rect.height())
        widgets['label'].setText(f"Area: {adjusted_rect.width()}x{adjusted_rect.height()}")
        widgets['rb_area'].setChecked(True)

    def toggle_recording(self):
        if self.is_recording:
            if self.recorder: self.recorder.stop()
            for thread in self.log_reader_threads:
                thread.stop()
            if self.resource_monitor_thread: self.resource_monitor_thread.stop()
            self.save_logs_to_file()                
            self.log_reader_threads = []            
            self.set_ui_state(recording=False)
            if self.process_monitor_thread: self.process_monitor_thread.stop()
            self.reset_status_indicators()
            self.set_ui_state(recording=False) 
            self.global_pids.clear() # Clear the global list on a clean stop           
        else:
            settings = self.gather_recording_settings()
            if not settings: return
            #self.log_viewer.log_display.clear() # Clear old logs            
            
            self.ffmpeg_log_viewer.log_display.clear()
            self.reset_status_indicators()
            self.set_status_for_selected("pending")

            self.recorder = Recorder(**settings)
            self.recorder.start()

            active_processes = self.recorder.get_active_processes()
            if active_processes:
                # --- Populate the global PID set ---
                for process, task_name in active_processes:
                    self.global_pids.add(process.pid)                
                self.build_pid_map(active_processes)
                self.start_log_readers(active_processes)
                                
                self.process_monitor_thread = ProcessMonitorThread(active_processes)
                self.process_monitor_thread.process_status_update.connect(self.on_process_status_update)
                self.process_monitor_thread.start()
                
                # Start resource monitoring
                self.resource_monitor_thread = ResourceMonitorThread(self.recorder.project_dir)
                self.resource_monitor_thread.low_resource_warning.connect(self.show_low_resource_warning)
                self.resource_monitor_thread.start()
                
                self.set_ui_state(recording=True)
            else:
                QMessageBox.critical(self, "Recording Failed", "Could not start any recording processes. Please check App Logs for errors.")
                self.reset_status_indicators()

    def start_log_readers(self, processes):
        for process, task_name in processes:
            for stream in [process.stdout, process.stderr]:
                thread = LogReaderThread(stream)
                thread.log_line_received.connect(self.ffmpeg_log_viewer.append_log)
                thread.start()
                self.log_reader_threads.append(thread)

    def show_low_resource_warning(self, message):
        """Shows a non-blocking warning message about low system resources."""
        QMessageBox.warning(self, "System Resource Warning", message)

    def save_logs_to_file(self):
        """Saves the content of the log viewers to files in the project directory."""
        if not self.recorder or not self.recorder.project_dir or not os.path.exists(self.recorder.project_dir):
            return
        
        try:
            app_log_content = self.app_log_viewer.log_display.toPlainText()
            ffmpeg_log_content = self.ffmpeg_log_viewer.log_display.toPlainText()

            with open(os.path.join(self.recorder.project_dir, "application.log"), "w", encoding="utf-8") as f:
                f.write(app_log_content)
            
            with open(os.path.join(self.recorder.project_dir, "ffmpeg_output.log"), "w", encoding="utf-8") as f:
                f.write(ffmpeg_log_content)
            
            logging.info("Log files saved successfully.")
        except Exception as e:
            logging.error(f"Could not save log files: {e}")

    def build_pid_map(self, processes):
        """Creates a map from process PID to the corresponding UI status label."""
        self.pid_to_widget_map = {}
        task_name_to_widget = {}
        # Create a lookup table from task name to widget
        for monitor_id, widgets in self.ui_widgets['monitors'].items():
            task_name_to_widget[f"Screen {monitor_id}"] = widgets['status_label']
        for widget_set in self.ui_widgets['audio'] + self.ui_widgets['webcams']:
            task_name_to_widget[f"Audio {widget_set['device'].name}"] = widget_set['status_label']
            task_name_to_widget[f"Webcam {widget_set['device'].name}"] = widget_set['status_label']
        
        # Map PID to widget using the lookup table
        for process, task_name in processes:
            if task_name in task_name_to_widget:
                self.pid_to_widget_map[process.pid] = task_name_to_widget[task_name]

    def on_process_status_update(self, pid, status):
        """Updates the status indicator icon based on process status."""
        if pid in self.pid_to_widget_map:
            label = self.pid_to_widget_map[pid]
            if status == "running":
                label.setText("<font color='green'>●</font>") # Green circle
            elif status == "exited_error":
                label.setText("<font color='red'>●</font>") # Red circle
            else: # exited_ok
                label.setText("<font color='grey'>⚪</font>") # Grey circle
        if status in ("exited_ok", "exited_error"):
            self.global_pids.discard(pid)

    def reset_status_indicators(self):
        """Resets all status icons to the default grey circle."""
        for widgets in self.ui_widgets['monitors'].values():
            widgets['status_label'].setText("⚪")
        for widget_set in self.ui_widgets['audio'] + self.ui_widgets['webcams']:
            widget_set['status_label'].setText("⚪")

    def set_status_for_selected(self, status):
        """Sets the status icon for all currently checked items."""
        if status == "pending":
            text = "<font color='orange'>●</font>" # Orange circle
            for monitor_id, widgets in self.ui_widgets['monitors'].items():
                if widgets['checkbox'].isChecked(): widgets['status_label'].setText(text)
            for widget_set in self.ui_widgets['audio'] + self.ui_widgets['webcams']:
                if widget_set['checkbox'].isChecked(): widget_set['status_label'].setText(text)

    def set_ui_state(self, recording: bool):
        self.is_recording = recording
        self.monitor_group_box.setEnabled(not recording)
        self.audio_group_box.setEnabled(not recording)
        self.webcam_group_box.setEnabled(not recording)
        if recording:
            self.record_button.setText(" Stop")
            self.record_button.setIcon(self.style().standardIcon(getattr(self.style().StandardPixmap, "SP_MediaStop")))
        else:
            self.record_button.setText(" Record")
            self.record_button.setIcon(self.style().standardIcon(getattr(self.style().StandardPixmap, "SP_MediaPlay")))

    def gather_recording_settings(self) -> dict:
        screen_tasks, webcam_tasks, audio_tasks = [], [], []

        for monitor_id, widgets in self.ui_widgets['monitors'].items():
            if widgets['checkbox'].isChecked():
                task = {'monitor': next(m for m in self.monitors if m.id == monitor_id)}
                if widgets['rb_area'].isChecked():
                    if not widgets['area_geo']:
                        QMessageBox.warning(self, "Area Not Selected", f"Please select an area for Screen {monitor_id}.")
                        return None
                    task['mode'] = 'area'
                    task['area_geo'] = widgets['area_geo']
                else:
                    task['mode'] = 'fullscreen'
                screen_tasks.append(task)
        
        for widget_set in self.ui_widgets['audio']:
            if widget_set['checkbox'].isChecked(): audio_tasks.append(widget_set['device'])
        
        for widget_set in self.ui_widgets['webcams']:
            if widget_set['checkbox'].isChecked(): webcam_tasks.append(widget_set['device'])

        if not screen_tasks and not webcam_tasks and not audio_tasks:
            QMessageBox.warning(self, "No Sources Selected", "Please select at least one screen, webcam, or audio source to record.")
            return None
            
        return {"screen_tasks": screen_tasks, "webcam_tasks": webcam_tasks, "audio_tasks": audio_tasks}

    def _clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def closeEvent(self, event):
        if self.is_recording: 
            self.recorder.stop()
            self.save_logs_to_file()
        # Ensure the process monitor thread is stopped before exiting
        if self.process_monitor_thread:
            self.process_monitor_thread.stop()
            self.process_monitor_thread.wait() # Wait for it to finish            
        for thread in self.log_reader_threads:
            thread.stop()        
        event.accept()    