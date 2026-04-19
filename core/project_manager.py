#core/project_manager.py

import os
import shutil
import time
from pathlib import Path
import msgpack
from dataclasses import asdict
from .models import ProjectData, TrackData, ClipData
from .signal_hub import global_signals
from .app_config import app_config  # <-- Import our new memory brain

class ProjectManager:
    """Handles the saving, loading, and state management of the Hive video project."""
    
    def __init__(self):
        self.current_project = None
        self.project_path = None

    def create_new_project(self, name="Untitled Project", project_type="standard"):
        """Creates a fresh, empty project in memory, using user default settings."""
        # 1. Fetch user defaults from AppConfig
        res_setting = app_config.get_setting("default_resolution", "1920x1080 (HD)")
        fps_setting = app_config.get_setting("default_fps", "30")
        
        # 2. Parse "1920x1080 (HD)" -> (1920, 1080)
        try:
            res_str = res_setting.split(" ")[0]
            w, h = map(int, res_str.split("x"))
            resolution = (w, h)
        except Exception:
            resolution = (1920, 1080)
            
        # 3. Parse "23.976" -> 23.976
        try:
            fps = float(fps_setting)
        except Exception:
            fps = 30.0

        # 4. Instantiate the project with the customized settings
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
        """Saves the current project state to a binary .hive file using msgpack."""
        if not self.current_project:
            print("No active project to save.")
            return False
            
        if save_path:
            self.project_path = save_path
            
        if not self.project_path:
            print("No save path provided.")
            return False
            
        # Ensure the file has the correct extension
        if not self.project_path.endswith('.hive'):
            self.project_path += '.hive'

        # 1. Convert the Python Dataclass into a standard dictionary
        project_dict = asdict(self.current_project)
        
        # 2. Write it quickly as binary using MessagePack
        try:
            with open(self.project_path, 'wb') as f:
                packed_data = msgpack.packb(project_dict, use_bin_type=True)
                f.write(packed_data)
                
            # Log this into the Hub's memory!
            app_config.add_recent_project(self.current_project.name, self.project_path, duration_str)
            
            global_signals.project_saved.emit(self.project_path)
            print(f"Project saved successfully to {self.project_path}")
            return True
        except Exception as e:
            print(f"Error saving project: {e}")
            return False

    def soft_delete_project(self, file_path):
        """Moves a project folder/file to the .bin directory instead of permanent deletion."""
        if not os.path.exists(file_path):
            return False
            
        try:
            path_obj = Path(file_path)
            parent_dir = path_obj.parent
            
            # Setup bin directory
            bin_dir = Path(app_config.default_project_path) / ".bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            
            # If the parent dir has the exact same name as the project (our folder structure), move the whole folder
            if parent_dir.name == path_obj.stem:
                dest = bin_dir / parent_dir.name
                if dest.exists():
                    dest = bin_dir / f"{parent_dir.name}_{int(time.time())}"
                shutil.move(str(parent_dir), str(dest))
            else:
                # Fallback for old projects not in dedicated folders: just move the file
                dest = bin_dir / path_obj.name
                if dest.exists():
                    dest = bin_dir / f"{path_obj.stem}_{int(time.time())}{path_obj.suffix}"
                shutil.move(str(path_obj), str(dest))
                
            # Remove from recent memory
            recent = app_config.data.get("recent_projects", [])
            recent = [p for p in recent if p["path"] != file_path]
            app_config.data["recent_projects"] = recent
            app_config._save()
            
            return True
        except Exception as e:
            print(f"Error deleting project: {e}")
            return False

    def get_trashed_projects(self):
        """Returns a list of items currently in the trash bin."""
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
        """Restores a project from the trash back to the main projects folder."""
        src = Path(trash_path)
        if not src.exists(): return False

        dest_dir = Path(app_config.default_project_path)
        dest = dest_dir / src.name

        # Prevent overwriting existing projects
        counter = 2
        while dest.exists():
            dest = dest_dir / f"{src.stem}_{counter}{src.suffix}"
            counter += 1

        try:
            shutil.move(str(src), str(dest))
            # Try to find the .hive file inside to add to recents automatically
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
        """Deletes a project permanently from the disk."""
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
        """Renames a physical project file and updates its internal memory state."""
        if not os.path.exists(old_path):
            return False
            
        new_path = os.path.join(os.path.dirname(old_path), f"{new_name}.hive")
        
        # Avoid overwriting existing projects
        if os.path.exists(new_path) and old_path != new_path:
            return False
            
        try:
            # 1. Read binary data and update the internal project name
            with open(old_path, 'rb') as f:
                project_dict = msgpack.unpackb(f.read(), raw=False)
            
            project_dict['name'] = new_name
            
            # 2. Write it quickly to the new file
            with open(new_path, 'wb') as f:
                packed_data = msgpack.packb(project_dict, use_bin_type=True)
                f.write(packed_data)
                
            # 3. Clean up old file
            if old_path != new_path:
                os.remove(old_path)
                
            # 4. Update the AppConfig Recent list memory
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
        """Loads a .hive binary file and rebuilds the ProjectData object."""
        if not os.path.exists(load_path):
            print("File does not exist.")
            return False
            
        try:
            with open(load_path, 'rb') as f:
                # 1. Read binary data back into a dictionary
                project_dict = msgpack.unpackb(f.read(), raw=False)
                
            # 2. Rebuild the Dataclasses from the dictionary
            self.current_project = self._rebuild_project_from_dict(project_dict)
            self.project_path = load_path
            
            # Log this into the Hub's memory!
            app_config.add_recent_project(self.current_project.name, self.project_path)
            
            global_signals.project_loaded.emit(self.current_project)
            print(f"Project loaded successfully from {load_path}")
            return True
            
        except Exception as e:
            print(f"Failed to load project: {e}")
            return False

    def _rebuild_project_from_dict(self, data: dict) -> ProjectData:
        """Helper method to map dictionary lists back into TrackData and ClipData objects."""
        tracks_data = data.pop('tracks', [])
        tracks = []
        
        # FIX: msgpack deserializes tuples as lists — convert resolution back to tuple
        if 'resolution' in data and isinstance(data['resolution'], list):
            data['resolution'] = tuple(data['resolution'])
        
        for t_data in tracks_data:
            clips_data = t_data.pop('clips', [])
            clips = [ClipData(**c) for c in clips_data]
            tracks.append(TrackData(clips=clips, **t_data))
            
        return ProjectData(tracks=tracks, **data)

# Create a single global instance
project_manager = ProjectManager()