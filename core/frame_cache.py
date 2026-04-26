import threading
from collections import OrderedDict
import numpy as np

class FrameCache:
    def __init__(self, max_memory_bytes):
        """
        Initializes the thread-safe LRU Frame Cache.
        :param max_memory_bytes: The total allowed memory limit in bytes.
        """
        self.max_memory_bytes = max_memory_bytes
        self.current_memory_bytes = 0
        
        # OrderedDict maintains insertion order. 
        # The first item is the oldest (Least Recently Used).
        # The last item is the newest (Most Recently Used).
        self.cache = OrderedDict()
        
        # A thread lock to prevent data corruption during simultaneous read/writes.
        self.lock = threading.Lock()

    def update_limit(self, new_limit_bytes):
        """Allows dynamically updating the cache limit from the UI slider."""
        with self.lock:
            self.max_memory_bytes = new_limit_bytes
            self._enforce_memory_limit()

    def get(self, frame_index):
        """
        Retrieves a frame from the cache.
        If found, marks it as the most recently used.
        """
        with self.lock:
            if frame_index in self.cache:
                # Move to the right side (Most Recently Used end)
                self.cache.move_to_end(frame_index)
                return self.cache[frame_index]
            return None

    def put(self, frame_index, frame_array):
        """
        Adds a decoded Numpy array frame to the cache.
        Automatically evicts the oldest frames if the memory limit is exceeded.
        """
        with self.lock:
            # If the frame is somehow already in cache, remove it first
            # to keep our current_memory_bytes calculation perfectly accurate.
            if frame_index in self.cache:
                old_frame = self.cache.pop(frame_index)
                self.current_memory_bytes -= old_frame.nbytes

            # Calculate the raw byte size of the incoming Numpy array
            frame_size = frame_array.nbytes

            # Safety check: If a single frame is larger than the entire cache limit, ignore it.
            if frame_size > self.max_memory_bytes:
                return

            # Add to cache (goes to the Most Recently Used end)
            self.cache[frame_index] = frame_array
            self.current_memory_bytes += frame_size

            # Evict older frames if we just exceeded the limit
            self._enforce_memory_limit()

    def _enforce_memory_limit(self):
        """
        Internal helper to pop the oldest frames until memory is under the limit.
        NOTE: Must only be called from inside a `with self.lock:` block!
        """
        while self.current_memory_bytes > self.max_memory_bytes and self.cache:
            # popitem(last=False) pops from the left side (the oldest item)
            evicted_index, evicted_array = self.cache.popitem(last=False)
            
            # Subtract the size of the evicted frame from our running total
            self.current_memory_bytes -= evicted_array.nbytes

    def clear(self):
        """Flushes the entire cache."""
        with self.lock:
            self.cache.clear()
            self.current_memory_bytes = 0