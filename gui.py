import logging
import time
import qdarkstyle
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QGroupBox, QCheckBox, QLabel, QRadioButton, QButtonGroup, QMessageBox
)

from PyQt6.QtCore import QThread, pyqtSignal, Qt, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QGuiApplication
from device_manager import get_device_detector, Monitor, AudioDevice, Webcam
from recorder import Recorder

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

class MainWindow(QMainWindow):
    """The main application window."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multi Recorder")
        self.setGeometry(100, 100, 550, 600)
        self.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt6'))

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)

        self.detector = get_device_detector()
        self.monitors = []
        self.recording_area = None
        self.is_recording = False
        self.recorder = None

        self._create_monitor_section()
        self._create_audio_section()
        self._create_webcam_section()
        self.main_layout.addStretch(1)
        self._create_action_bar()

        self.update_ui_with_devices(*self._get_current_devices())

    def _get_current_devices(self):
        return self.detector.detect_monitors(), self.detector.detect_audio_devices(), self.detector.detect_webcams()

    def _clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    # FIX: Merged the two _create_monitor_section methods into one correct one.
    def _create_monitor_section(self):
        self.monitor_group_box = QGroupBox("Screen Capture")
        self.monitor_layout = QVBoxLayout()
        self.monitor_layout.setSpacing(4)
        self.monitor_group_box.setLayout(self.monitor_layout)
        self.main_layout.addWidget(self.monitor_group_box)

    def _create_audio_section(self):
        self.audio_group_box = QGroupBox("Audio Devices")
        self.audio_layout = QVBoxLayout()
        self.audio_group_box.setLayout(self.audio_layout)
        self.main_layout.addWidget(self.audio_group_box)

    def _create_webcam_section(self):
        self.webcam_group_box = QGroupBox("Webcams")
        self.webcam_layout = QVBoxLayout()
        self.webcam_group_box.setLayout(self.webcam_layout)
        self.main_layout.addWidget(self.webcam_group_box)
        
    def _create_action_bar(self):
        self.record_button = QPushButton(" Record")
        self.record_button.setFixedHeight(40)
        self.record_button.setIcon(self.style().standardIcon(getattr(self.style().StandardPixmap, "SP_MediaPlay")))
        self.record_button.clicked.connect(self.toggle_recording)
        self.main_layout.addWidget(self.record_button)

    def update_ui_with_devices(self, monitors, audio_devices, webcams):
        self.monitors = monitors
        
        # --- Update Monitors UI ---
        self._clear_layout(self.monitor_layout)
        self.monitor_option_widgets = {}

        for monitor in monitors:
            container_layout = QVBoxLayout()
            checkbox = QCheckBox(f"Screen {monitor.id}: {monitor.resolution[0]}x{monitor.resolution[1]}")
            checkbox.setChecked(monitor.is_primary)
            
            options_widget = QWidget()
            options_layout = QHBoxLayout(options_widget)
            options_layout.setContentsMargins(20, 0, 0, 0) # Indent options
            
            rb_fullscreen = QRadioButton("Fullscreen")
            rb_fullscreen.setChecked(True)
            rb_area = QRadioButton("Select Area")
            btn_select_area = QPushButton("...")
            btn_select_area.setFixedSize(20, 20)
            btn_select_area.clicked.connect(self.select_area)
            lbl_area_dims = QLabel("")
            
            options_layout.addWidget(rb_fullscreen)
            options_layout.addWidget(rb_area)
            options_layout.addWidget(btn_select_area)
            options_layout.addWidget(lbl_area_dims)
            options_layout.addStretch()

            options_widget.setEnabled(checkbox.isChecked())
            checkbox.toggled.connect(options_widget.setEnabled)
            
            self.monitor_option_widgets[monitor.id] = {
                'checkbox': checkbox, 'rb_fullscreen': rb_fullscreen,
                'rb_area': rb_area, 'label': lbl_area_dims
            }
            container_layout.addWidget(checkbox)
            container_layout.addWidget(options_widget)
            self.monitor_layout.addLayout(container_layout)
        
        # FIX: Added missing UI generation for audio and webcams
        # --- Update Audio ---
        self._clear_layout(self.audio_layout)
        if not audio_devices: self.audio_layout.addWidget(QLabel("No audio devices detected."))
        for device in audio_devices:
            default_str = " (Default)" if device.is_default else ""
            self.audio_layout.addWidget(QCheckBox(f"{device.name}{default_str}"))

        # --- Update Webcams ---
        self._clear_layout(self.webcam_layout)
        if not webcams: self.webcam_layout.addWidget(QLabel("No webcams detected."))
        for device in webcams:
            self.webcam_layout.addWidget(QCheckBox(f"{device.name} ({device.status})"))

    def select_area(self):
        self.selection_overlay = SelectionOverlay()
        self.selection_overlay.area_selected.connect(self.on_area_selected)
        self.selection_overlay.show()

    def on_area_selected(self, rect: QRect):
        self.recording_area = (rect.x(), rect.y(), rect.width(), rect.height())
        for monitor_id, widgets in self.monitor_option_widgets.items():
            if widgets['rb_area'].isChecked():
                widgets['label'].setText(f"Area: {rect.width()}x{rect.height()}")
                break

    def toggle_recording(self):
        if self.is_recording:
            if self.recorder: self.recorder.stop()
            self.is_recording = False
            self.record_button.setText(" Record")
            self.record_button.setIcon(self.style().standardIcon(getattr(self.style().StandardPixmap, "SP_MediaPlay")))
            self.monitor_group_box.setEnabled(True)
            self.audio_group_box.setEnabled(True)
            self.webcam_group_box.setEnabled(True)
        else:
            settings = self.gather_recording_settings()
            if not settings: return
            
            self.recorder = Recorder(settings)
            self.recorder.start()
            
            self.is_recording = True
            self.record_button.setText(" Stop")
            self.record_button.setIcon(self.style().standardIcon(getattr(self.style().StandardPixmap, "SP_MediaStop")))
            self.monitor_group_box.setEnabled(False)
            self.audio_group_box.setEnabled(False)
            self.webcam_group_box.setEnabled(False)

    def gather_recording_settings(self) -> dict:
        """Collects all selected options from the GUI into a settings dictionary."""
        # FIX: Major rewrite to correctly read the UI state.
        for monitor_id, widgets in self.monitor_option_widgets.items():
            if widgets['checkbox'].isChecked():
                monitor = next((m for m in self.monitors if m.id == monitor_id), None)
                if not monitor: continue

                mode = 'fullscreen'
                if widgets['rb_area'].isChecked():
                    mode = 'area'
                    if not self.recording_area:
                        QMessageBox.warning(self, "Area Not Selected", "Please select an area to record for the chosen monitor.")
                        return None
                
                return {
                    "monitor": monitor,
                    "mode": mode,
                    "area_geo": self.recording_area if mode == 'area' else None,
                    "audio_devices": [], # TODO
                    "webcams": [], # TODO
                    "save_path": None
                }
        
        QMessageBox.warning(self, "No Screen Selected", "Please select a screen to record.")
        return None
        
    def closeEvent(self, event):
        if self.is_recording:
             self.recorder.stop()
        event.accept()