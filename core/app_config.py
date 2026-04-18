# core/app_config.py

import os
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

class AppConfig:
    """Handles global app settings, memory (Recent Projects), and caching."""
    
    def __init__(self):
        self.config_dir = Path.home() / ".hive_editor"
        self.config_file = self.config_dir / "config.json"
        
        # Setup Default Paths
        self.default_project_path = Path.home() / "Documents" / "HAVE_Projects"
        self.default_export_path = Path.home() / "Videos" / "HAVE_Exports"
        self.proxy_cache_path = self.config_dir / "proxies" 
        self.thumbnail_cache_path = self.config_dir / "thumbnails"
        self.waveform_cache_path = self.config_dir / "waveforms"
        
        # Ensure directories exist
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.default_project_path.mkdir(parents=True, exist_ok=True)
        self.default_export_path.mkdir(parents=True, exist_ok=True)
        self.proxy_cache_path.mkdir(parents=True, exist_ok=True)
        self.thumbnail_cache_path.mkdir(parents=True, exist_ok=True)
        self.waveform_cache_path.mkdir(parents=True, exist_ok=True)
        
        self.data = self._load()
        
        # Initialize default settings if they don't exist
        self.settings = self.data.get("settings", {
            "language": "English",
            "theme": "Dark",
            "default_image_duration": 5.0,
            "default_transition_duration": 1.0,
            "auto_save_enabled": True,
            "auto_save_interval": 5,
            "default_resolution": "1920x1080",
            "default_fps": "30",
            "hardware_acceleration": True,
            "auto_proxies": True,
            "proxy_resolution": "360p",
            "export_format": "MP4",
            "export_codec": "H.264",
            "copy_media_to_project": False # New Option
        })
        
        # Clean up the trash bin automatically
        self.cleanup_bin()

    def cleanup_bin(self):
        """Automatically deletes projects in the .bin folder older than 7 days."""
        bin_dir = self.default_project_path / ".bin"
        if not bin_dir.exists():
            return
            
        now = time.time()
        seven_days = 7 * 24 * 60 * 60
        
        for item in bin_dir.iterdir():
            try:
                # Check modification time
                if now - item.stat().st_mtime > seven_days:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
            except Exception as e:
                print(f"Failed to cleanup bin item {item}: {e}")

    def _load(self):
        """Loads the configuration file if it exists."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    
                    saved_path = data.get("default_project_path")
                    if saved_path and os.path.exists(saved_path):
                        self.default_project_path = Path(saved_path)
                        
                    saved_export = data.get("default_export_path")
                    if saved_export and os.path.exists(saved_export):
                        self.default_export_path = Path(saved_export)
                        
                    return data
            except Exception as e:
                print(f"Error loading config: {e}")
        return {"recent_projects": [], "settings": {}}

    def _save(self):
        """Saves the current state to the disk."""
        self.data["default_project_path"] = str(self.default_project_path)
        self.data["default_export_path"] = str(self.default_export_path)
        self.data["settings"] = self.settings
        with open(self.config_file, 'w') as f:
            json.dump(self.data, f, indent=4)

    # --- Generic Settings Accessors ---
    def get_setting(self, key, default_value=None):
        return self.settings.get(key, default_value)

    def set_setting(self, key, value):
        self.settings[key] = value
        self._save()

    def set_default_project_path(self, new_path):
        """Updates and saves the default project directory."""
        if os.path.exists(new_path):
            self.default_project_path = Path(new_path)
            self._save()
            
    def set_default_export_path(self, new_path):
        """Updates and saves the default export directory."""
        if os.path.exists(new_path):
            self.default_export_path = Path(new_path)
            self._save()

    def get_recent_projects(self):
        """Returns the list of recent projects, automatically pruning deleted files."""
        recent = self.data.get("recent_projects", [])
        valid_projects = [p for p in recent if os.path.exists(p["path"])]
        if len(valid_projects) != len(recent):
            self.data["recent_projects"] = valid_projects
            self._save()
        return valid_projects

    def add_recent_project(self, name, path, duration_str="00:00:00:00"):
        """Logs a project to the recent list and moves it to the top."""
        recent = self.data.get("recent_projects", [])
        recent = [p for p in recent if p["path"] != path]
        recent.insert(0, {
            "name": name,
            "path": path,
            "date": datetime.now().strftime("%b %d, %Y"),
            "duration": duration_str
        })
        self.data["recent_projects"] = recent[:12]
        self._save()

    # --- Cache Management ---

    def calculate_cache_size(self):
        """Scans the proxy and thumbnail folders and returns a human-readable size."""
        total_size = 0
        for cache_dir in [self.proxy_cache_path, self.thumbnail_cache_path, self.waveform_cache_path]:
            if cache_dir.exists():
                for dirpath, _, filenames in os.walk(cache_dir):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        if not os.path.islink(fp):
                            total_size += os.path.getsize(fp)
        
        if total_size == 0:
            return "0 MB"
        elif total_size < 1024 * 1024:
            return f"{total_size / 1024:.2f} KB"
        elif total_size < 1024 * 1024 * 1024:
            return f"{total_size / (1024 * 1024):.2f} MB"
        else:
            return f"{total_size / (1024 * 1024 * 1024):.2f} GB"

    def clear_cache(self):
        """Deletes all generated proxy and thumbnail files."""
        freed_space = self.calculate_cache_size()
        for cache_dir in [self.proxy_cache_path, self.thumbnail_cache_path, self.waveform_cache_path]:
            if cache_dir.exists():
                for filename in os.listdir(cache_dir):
                    file_path = os.path.join(cache_dir, filename)
                    try:
                        if os.path.isfile(file_path) or os.path.islink(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as e:
                        print(f"Failed to delete {file_path}. Reason: {e}")
        return freed_space

# Global instance
app_config = AppConfig()