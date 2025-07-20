import logging
import time
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QGroupBox, QCheckBox, QLabel, QRadioButton, QButtonGroup,
    QScrollArea
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
import qdarkstyle
from device_manager import get_device_detector, Monitor, AudioDevice, Webcam

class DevicePoller(QThread):
    """A worker thread that polls for device changes and emits a signal."""
    devices_refreshed = pyqtSignal(list, list, list)

    def __init__(self, detector):
        super().__init__()
        self.detector = detector
        self.running = True
        self.last_state = ""

    def run(self):
        logging.info("Device poller thread started.")
        while self.running:
            monitors = self.detector.detect_monitors()
            audio_devices = self.detector.detect_audio_devices()
            webcams = self.detector.detect_webcams()
            
            # Create a simple representation of the state to check for changes
            current_state = f"{[m.id for m in monitors]},{[a.id for a in audio_devices]},{[w.id for w in webcams]}"
            
            if current_state != self.last_state:
                logging.info("Device change detected. Emitting signal.")
                self.last_state = current_state
                self.devices_refreshed.emit(monitors, audio_devices, webcams)
                
            time.sleep(5) # Poll every 5 seconds

    def stop(self):
        self.running = False
        logging.info("Device poller thread stopped.")


class MainWindow(QMainWindow):
    """The main application window."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multi Recorder - Device Selection")
        self.setGeometry(100, 100, 600, 700)
        self.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt6'))

        # Central Widget and Main Layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Device Detector
        self.detector = get_device_detector()

        # Create UI sections
        self._create_monitor_section()
        self._create_audio_section()
        self._create_webcam_section()
        self.main_layout.addStretch(1) # Pushes everything up
        self._create_action_bar()

        # Start the device poller
        self.poller = DevicePoller(self.detector)
        self.poller.devices_refreshed.connect(self.update_ui_with_devices)
        self.poller.start()

    def _clear_layout(self, layout):
        """Removes all widgets from a layout."""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _create_monitor_section(self):
        group_box = QGroupBox("Monitors & Screen Capture")
        self.monitor_layout = QVBoxLayout()
        group_box.setLayout(self.monitor_layout)
        self.main_layout.addWidget(group_box)

    def _create_audio_section(self):
        group_box = QGroupBox("Audio Devices")
        self.audio_layout = QVBoxLayout()
        group_box.setLayout(self.audio_layout)
        self.main_layout.addWidget(group_box)

    def _create_webcam_section(self):
        group_box = QGroupBox("Webcams")
        self.webcam_layout = QVBoxLayout()
        group_box.setLayout(self.webcam_layout)
        self.main_layout.addWidget(group_box)
        
    def _create_action_bar(self):
        action_bar = QHBoxLayout()
        action_bar.addStretch()
        record_button = QPushButton(" Record")
        record_button.setFixedHeight(40)
        record_button.setIcon(self.style().standardIcon(getattr(self.style().StandardPixmap, "SP_MediaPlay")))
        action_bar.addWidget(record_button)
        self.main_layout.addLayout(action_bar)

    def update_ui_with_devices(self, monitors, audio_devices, webcams):
        """Slot to handle the signal from the poller and refresh the UI."""
        # --- Update Monitors ---
        self._clear_layout(self.monitor_layout)
        if not monitors:
            self.monitor_layout.addWidget(QLabel("No monitors detected."))
        for monitor in monitors:
            # Main checkbox for the monitor
            monitor_checkbox = QCheckBox(f"Screen {monitor.id}: {monitor.resolution[0]}x{monitor.resolution[1]}")
            monitor_checkbox.setChecked(monitor.is_primary) # Default to recording primary

            # Options for how to record
            options_layout = QHBoxLayout()
            options_group = QButtonGroup(self)
            
            rb_fullscreen = QRadioButton("Fullscreen")
            rb_fullscreen.setChecked(True)
            rb_area = QRadioButton("Select Area")
            rb_window = QRadioButton("Select Window")
            
            options_group.addButton(rb_fullscreen)
            options_group.addButton(rb_area)
            options_group.addButton(rb_window)
            
            options_layout.addWidget(rb_fullscreen)
            options_layout.addWidget(rb_area)
            options_layout.addWidget(rb_window)
            
            options_widget = QWidget()
            options_widget.setLayout(options_layout)
            options_widget.setEnabled(monitor_checkbox.isChecked()) # Enable/disable based on checkbox
            
            # Connect checkbox to enable/disable radio buttons
            monitor_checkbox.toggled.connect(options_widget.setEnabled)
            
            self.monitor_layout.addWidget(monitor_checkbox)
            self.monitor_layout.addWidget(options_widget)
            
        # --- Update Audio ---
        self._clear_layout(self.audio_layout)
        if not audio_devices:
            self.audio_layout.addWidget(QLabel("No audio devices detected."))
        for device in audio_devices:
            default_str = " (Default)" if device.is_default else ""
            checkbox = QCheckBox(f"{device.name}{default_str}")
            # Default to recording the default input and any loopback/system audio
            if device.is_default and device.is_input:
                checkbox.setChecked(True)
            if device.is_loopback:
                 checkbox.setChecked(True)
            self.audio_layout.addWidget(checkbox)
            
        # --- Update Webcams ---
        self._clear_layout(self.webcam_layout)
        if not webcams:
            self.webcam_layout.addWidget(QLabel("No webcams detected."))
        for device in webcams:
            checkbox = QCheckBox(f"{device.name} ({device.status})")
            self.webcam_layout.addWidget(checkbox)

    def closeEvent(self, event):
        """Ensure the poller thread is stopped cleanly on exit."""
        self.poller.stop()
        self.poller.wait() # Wait for the thread to finish
        event.accept()