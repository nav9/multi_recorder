import logging
import platform
import os
import datetime
import ffmpeg
import subprocess
import re

def sanitize_filename(name: str) -> str:
    """Removes invalid characters from a string to make it a valid filename."""
    # Remove bracketed prefixes like [Input]
    name = re.sub(r'\[.*?\]\s*', '', name)
    # Replace invalid chars with an underscore
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()

class Recorder:
    """
    Manages multiple, independent FFmpeg processes for failsafe recording.
    Each screen, webcam, or audio source gets its own process.
    """
    def __init__(self, screen_tasks, webcam_tasks, audio_tasks, save_path=None):
        self.screen_tasks = screen_tasks
        self.webcam_tasks = webcam_tasks
        self.audio_tasks = audio_tasks
        self.save_path = save_path
        
        self.processes = [] # Now stores tuples of (process, task_name)
        self.system = platform.system()
        
        self.project_dir = self._create_project_directory()

    def _create_project_directory(self) -> str:
        base_path = self.save_path or os.path.join(os.path.expanduser('~'), 'Videos')
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        project_path = os.path.join(base_path, f"Multi_Recorder_{timestamp}")
        try:
            os.makedirs(project_path, exist_ok=True)
            logging.info(f"Created project directory: {project_path}")
            return project_path
        except OSError as e:
            logging.error(f"Failed to create project directory: {e}")
            return base_path

    def start(self):
        """Launches one FFmpeg process for each recording task."""
        # --- Launch Screen Recording Processes ---
        for task in self.screen_tasks:
            try:
                stream = self._get_screen_input(task)
                filename = os.path.join(self.project_dir, f"{sanitize_filename(task['monitor'].name)}.mp4")
                output = ffmpeg.output(stream, filename, vcodec='libx264', pix_fmt='yuv420p', r=30)
                self._launch_process(output, f"Screen {task['monitor'].id}")
            except Exception as e:
                logging.error(f"Failed to start recording for Screen {task['monitor'].id}: {e}")

        # --- Launch Webcam Recording Processes ---
        for task in self.webcam_tasks:
            try:
                stream = self._get_webcam_input(task)
                filename = os.path.join(self.project_dir, f"{sanitize_filename(task.name)}.mp4")
                output = ffmpeg.output(stream, filename, vcodec='libx264', pix_fmt='yuv420p', r=30)
                self._launch_process(output, f"Webcam {task.name}")
            except Exception as e:
                logging.error(f"Failed to start recording for Webcam {task.name}: {e}")
        
        # --- Launch Audio Recording Processes ---
        for task in self.audio_tasks:
            try:
                stream = self._get_audio_input(task)
                filename = os.path.join(self.project_dir, f"{sanitize_filename(task.name)}.mp3")
                output = ffmpeg.output(stream, filename, acodec='libmp3lame', audio_bitrate='192k')
                self._launch_process(output, f"Audio {task.name}")
            except Exception as e:
                logging.error(f"Failed to start recording for Audio {task.name}: {e}")

    def _launch_process(self, stream, task_name):
        """Compiles and runs a single FFmpeg command, capturing its output."""
        args = ffmpeg.compile(stream, overwrite_output=True)
        logging.info(f"Starting process for {task_name}: ffmpeg {' '.join(args)}")
        
        process = subprocess.Popen(
            args, # Use the args list directly
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.processes.append((process, task_name))
        logging.info(f"Process for {task_name} started with PID: {process.pid}")

    def get_active_processes(self):
        """Returns the list of currently running subprocess objects."""
        return self.processes

    def stop(self):
        """Stops all active FFmpeg recording processes gracefully."""
        for process, task_name in self.processes:
            try:
                process.communicate(input=b'q', timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        logging.info(f"Stopped {len(self.processes)} recording processes.")
        self.processes = []

    def _get_screen_input(self, task):
        """Constructs the correct FFmpeg input stream for screen capture."""
        monitor = task['monitor']
        mode = task['mode']
        x, y, w, h = 0, 0, 0, 0

        if mode == 'fullscreen':
            x, y = monitor.position
            w, h = monitor.resolution
        elif mode == 'area':
            x, y, w, h = task['area_geo']
        else:
            raise ValueError(f"Invalid screen capture mode: {mode}")

        input_options = {'s': f'{w}x{h}', 'framerate': 30, 'draw_mouse': '1'}
        
        if self.system == "Windows":
            return ffmpeg.input('desktop', f='gdigrab', offset_x=x, offset_y=y, **input_options)
        elif self.system == "Linux":
            display = os.environ.get('DISPLAY', ':0.0')
            return ffmpeg.input(f'{display}+{x},{y}', f='x11grab', **input_options)
        elif self.system == "Darwin":
            # Mac screen capture requires the correct device index for the screen
            return ffmpeg.input(f'{monitor.id}:none', f='avfoundation', **input_options)
        
        raise OSError(f"Unsupported OS for screen capture: {self.system}")

    def _get_webcam_input(self, cam_device):
        """Constructs the FFmpeg input stream for a webcam."""
        if self.system == "Windows":
            # soundcard names don't work here, we assume a simple name for dshow
            return ffmpeg.input(f'video=Webcam {cam_device.id}', f='dshow')
        elif self.system == "Linux":
            return ffmpeg.input(f'/dev/video{cam_device.id}')
        
        raise OSError(f"Unsupported OS for webcam capture: {self.system}")

    def _get_audio_input(self, audio_device):
        """Constructs the FFmpeg input stream for an audio device."""
        if self.system == "Windows":
            # Use the device name as the identifier for dshow
            return ffmpeg.input(f'audio={audio_device.name.replace("[Output] ", "").replace("[Input] ", "")}', f='dshow', ac=2)
        elif self.system == "Linux":
            # The device ID from soundcard is what PulseAudio needs
            return ffmpeg.input(audio_device.id, f='pulse', ac=2)
            
        raise OSError(f"Unsupported OS for audio capture: {self.system}")

