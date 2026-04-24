# core/video_decoder.py
import queue
import time
import cv2
import os
import threading
from PySide6.QtCore import QThread
os.environ["OPENCV_FFMPEG_THREADS"] = "1"

class VideoDecoder(QThread):
    """
    The Producer Thread: Bakes frames in the background and places them on the warming rack (queue).
    """
    def __init__(self, file_path, buffer_size=30):
        super().__init__()
        self.file_path = file_path
        
        # This is our warming rack. maxsize=30 prevents us from eating up all your RAM.
        self.frame_queue = queue.Queue(maxsize=buffer_size)
        self._run_flag = True

        # Thread-Safety Locks to prevent FFmpeg crashes
        self._seek_requested = False
        self._seek_target_ms = 0.0
        self._seek_lock = threading.Lock()
        
        # Step 1: Open the video file using OpenCV
        self.cap = cv2.VideoCapture(self.file_path)

    def stop(self):
        """Safely stops the thread and closes the video file."""
        self._run_flag = False
        self.wait()
        
        # Step 2: Always release the video file when done, otherwise Windows locks it!
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()

    def seek_to(self, logical_time):
        """Called when the user clicks somewhere new on the timeline."""
        with self.frame_queue.mutex:
            self.frame_queue.queue.clear()

        with self._seek_lock:
            self._seek_requested = True
            self._seek_target_ms = logical_time * 10.0

    def run(self):
        """The background loop that runs constantly while the video plays."""
        while self._run_flag:

            with self._seek_lock:
                if self._seek_requested:
                    self.cap.set(cv2.CAP_PROP_POS_MSEC, self._seek_target_ms)
                    self._seek_requested = False
                    continue
            
            # If the warming rack has space, bake another frame!
            if not self.frame_queue.full():
                ret, frame = self.cap.read()
                
                if ret:
                    # Find out exactly what time this specific frame belongs to
                    current_ms = self.cap.get(cv2.CAP_PROP_POS_MSEC)
                    logical_pos = current_ms / 10.0
                    
                    # Put the frame and its timestamp on the rack for the waiter (RenderEngine) to grab
                    self.frame_queue.put((logical_pos, frame))
                else:
                    # Video is over, or we hit an error. Just wait a moment.
                    time.sleep(0.05)
            else:
                # The rack is full! We successfully pre-loaded 30 frames.
                # Sleep for 10 milliseconds to let your CPU cool down.
                time.sleep(0.01)