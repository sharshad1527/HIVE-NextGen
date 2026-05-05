# core/logger.py
import logging
import os
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from core.signal_hub import global_signals

class QtSignalHandler(logging.Handler):
    """
    Custom logging handler that emits a PySide6 signal for every log record.
    This allows the UI to update in a thread-safe manner.
    """
    def emit(self, record):
        log_entry = self.format(record)
        
        # Maintain a session buffer for the UI
        manager = LoggerManager()
        manager.log_buffer.append(log_entry)
        if len(manager.log_buffer) > manager.MAX_BUFFER_SIZE:
            manager.log_buffer.pop(0)
            
        global_signals.log_emitted.emit(log_entry, record.levelname)

class LoggerManager:
    """
    Manages the application-wide logging system.
    Handles file rotation, console output, and UI signal emission.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.logger = logging.getLogger("HIVE")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False # Prevent double logging if main logger is used
        
        # Formatter for logs
        self.formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        self.log_buffer = []
        self.MAX_BUFFER_SIZE = 300
        
        self._initialized = True

    def setup(self, logs_dir: Path, verbose: bool = False):
        """Initializes handlers: Console, File (Rotating), and Qt Signal."""
        # Clear existing handlers if any (re-initialization safety)
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        level = logging.DEBUG if verbose else logging.INFO
        self.logger.setLevel(level)

        # 1. Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(self.formatter)
        self.logger.addHandler(console_handler)

        # 2. File Handler (Timed Rotating: 5 days)
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / "hive.log"
        
        file_handler = TimedRotatingFileHandler(
            filename=str(log_file),
            when='D',
            interval=1,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(self.formatter)
        self.logger.addHandler(file_handler)

        # 3. Qt Signal Handler for Live Viewer
        qt_handler = QtSignalHandler()
        qt_handler.setFormatter(self.formatter)
        self.logger.addHandler(qt_handler)

        self.logger.info(f"Logging initialized. Level: {level}")
        self.logger.info(f"Log file: {log_file}")

    def set_level(self, level_name: str):
        """Dynamically updates the logging level."""
        level = getattr(logging, level_name.upper(), logging.INFO)
        self.logger.setLevel(level)
        self.logger.info(f"Logging level changed to: {level_name.upper()}")

# Global instance for easy access
hive_logger = LoggerManager().logger
logger_manager = LoggerManager()
