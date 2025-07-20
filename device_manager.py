import platform
import logging
from dataclasses import dataclass, field
from typing import List

# --- Library Imports ---
try:
    import screeninfo
    import soundcard as sc
    import cv2
except ImportError as e:
    logging.error(f"A required library is missing: {e}. Please run 'pip install -r requirements.txt'")
    exit()

# --- Data Structures for Devices ---
# Using dataclasses provides structure and type safety.

@dataclass
class Monitor:
    id: int
    name: str
    resolution: tuple[int, int]
    position: tuple[int, int]
    is_primary: bool

@dataclass
class AudioDevice:
    id: str  # The ID used by the soundcard library
    name: str
    is_input: bool  # True for Mic, False for Speaker
    is_loopback: bool = False
    is_default: bool = False

@dataclass
class Webcam:
    id: int  # The index used by OpenCV
    name: str
    status: str = "Unknown"

# --- Base Detector Class (Interface) ---

class BaseDeviceDetector:
    """An abstract base class defining the device detection interface."""
    def detect_monitors(self) -> List[Monitor]:
        raise NotImplementedError

    def detect_audio_devices(self) -> List[AudioDevice]:
        raise NotImplementedError

    def detect_webcams(self) -> List[Webcam]:
        raise NotImplementedError

# --- Default Concrete Implementation ---

class DefaultDeviceDetector(BaseDeviceDetector):
    """A default device detector that uses cross-platform libraries."""

    def detect_monitors(self) -> List[Monitor]:
        monitors = []
        try:
            for i, m in enumerate(screeninfo.get_monitors()):
                monitors.append(Monitor(
                    id=i,
                    name=m.name if m.name else f"Display {i}",
                    resolution=(m.width, m.height),
                    position=(m.x, m.y),
                    is_primary=m.is_primary
                ))
        except screeninfo.common.ScreenInfoError as e:
            logging.error(f"Could not detect monitors: {e}")
        return monitors

    def detect_audio_devices(self) -> List[AudioDevice]:
        devices = []
        try:
            # Outputs (Speakers/Headphones)
            default_speaker = sc.default_speaker()
            for dev in sc.all_speakers():
                devices.append(AudioDevice(
                    id=dev.id,
                    name=f"[Output] {dev.name}",
                    is_input=False,
                    is_default=(dev.id == default_speaker.id)
                ))
            
            # Inputs (Microphones)
            default_mic = sc.default_microphone()
            for dev in sc.all_microphones(include_loopback=True):
                devices.append(AudioDevice(
                    id=dev.id,
                    name=f"[Input] {dev.name}",
                    is_input=True,
                    is_loopback=dev.isloopback,
                    is_default=(dev.id == default_mic.id)
                ))
        except Exception as e:
            logging.error(f"Could not detect audio devices: {e}")
        return devices
        
    def detect_webcams(self) -> List[Webcam]:
        webcams = []
        api_preference = cv2.CAP_ANY
        if platform.system() == "Windows":
            api_preference = cv2.CAP_DSHOW

        for i in range(10):
            cap = cv2.VideoCapture(i, api_preference)
            if cap.isOpened():
                ret, frame = cap.read()
                status = "Active" if ret else "Present (in use or initializing)"
                webcams.append(Webcam(id=i, name=f"Webcam {i}", status=status))
                cap.release()
            else:
                break
        return webcams

# --- Factory Function ---

def get_device_detector() -> BaseDeviceDetector:
    """
    Factory function to get the appropriate device detector for the current OS.
    Currently returns the default for all, but can be expanded later.
    """
    # os = platform.system()
    # if os == "Windows":
    #     return WindowsDeviceDetector()
    # elif os == "Linux":
    #     return LinuxDeviceDetector()
    return DefaultDeviceDetector()