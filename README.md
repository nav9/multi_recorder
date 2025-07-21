# Multi Recorder

**License:** MIT License

Multi Recorder is a cross-platform (Windows, macOS, Linux) desktop application for recording audio and video from multiple sources simultaneously. It is designed for users who need a powerful, flexible, and easy-to-use tool for screen capture, tutorials, presentations, and more.

The entire application is self-contained, requiring no external software installations by the end-user.

# Explanation of the initial WARN and ERROR Messages
These are harmless and are a normal part of the webcam detection process.  
* [ WARN:0@... ] cap_v4l.cpp:997 open VIDEOIO(V4L2:/dev/video1): can't open camera by index  
* [ ERROR:0@... ] obsensor_uvc_stream_channel.cpp:159 ... Camera index out of range  
**Reason:** The `detect_webcams` function is designed to be robust. It doesn't know how many cameras you have, so it probes for them sequentially. It tries to open `/dev/video0`, then `/dev/video1`, then `/dev/video2`, and so on. When it tries to open an index that does not exist (like `/dev/video1` when you only have one camera at `/dev/video0`), the underlying Linux library (V4L2) and the specific device driver library (Orbbec ObSensor) correctly report "I can't find a camera at this index." The Python code sees this failure, understands there are no more cameras, and stops looking. They can be safely ignored. 

## Core Features (Planned)

*   **Cross-Platform:** Works on Windows, macOS, and Linux.
*   **Dynamic Source Detection:** Automatically detects all connected monitors, webcams, and microphones. It also detects active signals and supports hot-plugging (connecting/disconnecting devices while the app is running).
*   **Flexible Recording Options:**
    *   Record the entire screen, a specific application window, or a custom area.
    *   Full support for multi-monitor setups.
*   **Multi-Source Recording:** Capture video and audio from multiple sources at once, with each source saved to a separate file for post-production flexibility.
*   **Advanced Settings:**
    *   Choose from quality presets or customize codecs, bitrates, and FPS.
    *   Save recordings in timed segments.
    *   Toggle recording of the mouse pointer.
*   **Post-Production Tools:** An integrated tool to stitch together video and audio segments/tracks after recording.
*   **User-Friendly GUI:**
    *   A compact, modern dark theme.
    *   Intuitive layout that remembers user settings.
    *   System tray controls for pausing and stopping.
*   **Automation:**
    *   Schedule recordings for specific start/end times.
    *   Set custom global hotkeys for start, pause, and stop.

## Getting Started (Developer Guide)

This guide is for setting up the development environment.

### Prerequisites

*   Python 3.8+
*   FFmpeg: You must have the FFmpeg executable installed and available in your system's PATH. This is for development only; the final application will bundle FFmpeg.
    *   **Windows:** Download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) and add the `bin` folder to your PATH.
    *   **macOS:** `brew install ffmpeg`
    *   **Linux (Ubuntu/Debian):** `sudo apt update && sudo apt install ffmpeg`

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd multi_recorder
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install the required packages:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    python main.py
    ```

## Testing

Refer to the `test_cases.md` file for instructions on how to test the application's functionality during development.
