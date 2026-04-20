# core/project_manager.py

import os
import shutil
import time
from pathlib import Path
import msgpack
from enum import Enum
from dataclasses import asdict, fields
from .models import ProjectData, TrackData, ClipData
from .signal_hub import global_signals
from .app_config import app_config

class ProjectManager:
    """Handles the saving, loading, and state management of the Hive video project."""
    
    def __init__(self):
        self.current_project = None
        self.project_path = None

    @staticmethod
    def _msgpack_default(obj):
        """Allows msgpack to safely serialize Python Enums (like Easing)."""
        if isinstance(obj, Enum):
            return obj.value
        return obj

    def create_new_project(self, name="Untitled Project", project_type="standard"):
        res_setting = app_config.get_setting("default_resolution", "1920x1080 (HD)")
        fps_setting = app_config.get_setting("default_fps", "30")
        
        try:
            res_str = res_setting.split(" ")[0]
            w, h = map(int, res_str.split("x"))
            resolution = (w, h)
        except Exception:
            resolution = (1920, 1080)
            
        try:
            fps = float(fps_setting)
        except Exception:
            fps = 30.0

        self.current_project = ProjectData(
            name=name, 
            project_type=project_type,
            resolution=resolution,
            fps=fps
        )
        self.project_path = None
        
        global_signals.project_loaded.emit(self.current_project)
        return self.current_project

    def save_project(self, save_path=None, duration_str="00:00:00:00"):
        if not self.current_project:
            print("No active project to save.")
            return False
            
        if save_path:
            self.project_path = save_path
            
        if not self.project_path:
            print("No save path provided.")
            return False
            
        if not self.project_path.endswith('.hive'):
            self.project_path += '.hive'

        project_dict = asdict(self.current_project)
        
        try:
            with open(self.project_path, 'wb') as f:
                # FIX: Pass the enum handler to default= so keyframes save safely
                packed_data = msgpack.packb(project_dict, default=self._msgpack_default, use_bin_type=True)
                f.write(packed_data)
                
            app_config.add_recent_project(self.current_project.name, self.project_path, duration_str)
            
            global_signals.project_saved.emit(self.project_path)
            print(f"Project saved successfully to {self.project_path}")
            return True
        except Exception as e:
            print(f"Error saving project: {e}")
            return False

    def soft_delete_project(self, file_path):
        if not os.path.exists(file_path):
            return False
            
        try:
            path_obj = Path(file_path)
            parent_dir = path_obj.parent
            
            bin_dir = Path(app_config.default_project_path) / ".bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            
            if parent_dir.name == path_obj.stem:
                dest = bin_dir / parent_dir.name
                if dest.exists():
                    dest = bin_dir / f"{parent_dir.name}_{int(time.time())}"
                shutil.move(str(parent_dir), str(dest))
            else:
                dest = bin_dir / path_obj.name
                if dest.exists():
                    dest = bin_dir / f"{path_obj.stem}_{int(time.time())}{path_obj.suffix}"
                shutil.move(str(path_obj), str(dest))
                
            recent = app_config.data.get("recent_projects", [])
            recent = [p for p in recent if p["path"] != file_path]
            app_config.data["recent_projects"] = recent
            app_config._save()
            
            return True
        except Exception as e:
            print(f"Error deleting project: {e}")
            return False

    def get_trashed_projects(self):
        bin_dir = Path(app_config.default_project_path) / ".bin"
        if not bin_dir.exists():
            return []

        trashed = []
        now = time.time()
        for item in bin_dir.iterdir():
            mtime = item.stat().st_mtime
            days_passed = (now - mtime) / (24 * 3600)
            days_left = max(0, int(7 - days_passed))
            trashed.append({
                "name": item.name,
                "path": str(item),
                "days_left": days_left
            })
        return trashed

    def recover_project(self, trash_path):
        src = Path(trash_path)
        if not src.exists(): return False

        dest_dir = Path(app_config.default_project_path)
        dest = dest_dir / src.name

        counter = 2
        while dest.exists():
            dest = dest_dir / f"{src.stem}_{counter}{src.suffix}"
            counter += 1

        try:
            shutil.move(str(src), str(dest))
            if dest.is_dir():
                hive_files = list(dest.glob("*.hive"))
                if hive_files:
                    app_config.add_recent_project(dest.name, str(hive_files[0]))
            else:
                app_config.add_recent_project(dest.stem, str(dest))
            return True
        except Exception as e:
            print(f"Failed to recover: {e}")
            return False

    def permanent_delete(self, trash_path):
        src = Path(trash_path)
        if not src.exists(): return False
        try:
            if src.is_dir():
                shutil.rmtree(str(src))
            else:
                src.unlink()
            return True
        except Exception as e:
            print(f"Failed to delete permanently: {e}")
            return False
            
    def rename_project(self, old_path, new_name):
        if not os.path.exists(old_path):
            return False
            
        new_path = os.path.join(os.path.dirname(old_path), f"{new_name}.hive")
        
        if os.path.exists(new_path) and old_path != new_path:
            return False
            
        try:
            with open(old_path, 'rb') as f:
                project_dict = msgpack.unpackb(f.read(), raw=False)
            
            project_dict['name'] = new_name
            
            with open(new_path, 'wb') as f:
                packed_data = msgpack.packb(project_dict, default=self._msgpack_default, use_bin_type=True)
                f.write(packed_data)
                
            if old_path != new_path:
                os.remove(old_path)
                
            recent = app_config.data.get("recent_projects", [])
            duration_str = "00:00:00:00"
            for p in recent:
                if p["path"] == old_path:
                    duration_str = p.get("duration", "00:00:00:00")
                    break
                    
            recent = [p for p in recent if p["path"] != old_path]
            app_config.data["recent_projects"] = recent
            app_config.add_recent_project(new_name, new_path, duration_str)
            
            return True
            
        except Exception as e:
            print(f"Error renaming project: {e}")
            return False

    def load_project(self, load_path):
        if not os.path.exists(load_path):
            print("File does not exist.")
            return False
            
        try:
            with open(load_path, 'rb') as f:
                project_dict = msgpack.unpackb(f.read(), raw=False)
                
            self.current_project = self._rebuild_project_from_dict(project_dict)
            self.project_path = load_path
            
            app_config.add_recent_project(self.current_project.name, self.project_path)
            
            global_signals.project_loaded.emit(self.current_project)
            print(f"Project loaded successfully from {load_path}")
            return True
            
        except Exception as e:
            # Prevent silent failures if a corrupted file exists
            print(f"Failed to load project: {e}")
            return False

    def _rebuild_project_from_dict(self, data: dict) -> ProjectData:
        """Helper method to map dictionary lists back into TrackData and ClipData objects cleanly."""
        tracks_data = data.pop('tracks', [])
        tracks = []
        
        if 'resolution' in data and isinstance(data['resolution'], list):
            data['resolution'] = tuple(data['resolution'])
            
        clip_field_names = {f.name for f in fields(ClipData)}
        track_field_names = {f.name for f in fields(TrackData)}
        proj_field_names = {f.name for f in fields(ProjectData)}
        
        for t_data in tracks_data:
            clips_data = t_data.pop('clips', [])
            clips = []
            for c in clips_data:
                safe_c = {k: v for k, v in c.items() if k in clip_field_names}
                clips.append(ClipData(**safe_c))
                
            safe_t = {k: v for k, v in t_data.items() if k in track_field_names}
            tracks.append(TrackData(clips=clips, **safe_t))
            
        safe_p = {k: v for k, v in data.items() if k in proj_field_names}
        return ProjectData(tracks=tracks, **safe_p)

# Create a single global instance
project_manager = ProjectManager()