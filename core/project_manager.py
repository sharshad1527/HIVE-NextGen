# core/project_manager.py

import os
import shutil
import time
from pathlib import Path
import copy
import msgpack
from enum import Enum
from dataclasses import asdict, fields
from .models import ProjectData, TrackData, ClipData
from .signal_hub import global_signals
from .app_config import app_config
from .logger import hive_logger

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

    def save_project(self, save_path=None, duration_str="00:00:00:00", is_autosave=False):
        if not self.current_project:
            hive_logger.warning("No active project to save.")
            return False
            
        if save_path:
            self.project_path = save_path
            
        if not self.project_path:
            hive_logger.warning("No save path provided for project save.")
            return False
            
        if not self.project_path.endswith('.hive'):
            self.project_path += '.hive'

        # --- Enhanced Backup Logic ---
        if not is_autosave and os.path.exists(self.project_path):
            self._create_timestamped_backup()

        save_target = self.project_path
        if is_autosave:
            save_target = self.project_path + ".autosave"

        project_dict = asdict(self.current_project)
        
        try:
            with open(save_target, 'wb') as f:
                packed_data = msgpack.packb(project_dict, default=self._msgpack_default, use_bin_type=True)
                f.write(packed_data)
                
            if not is_autosave:
                app_config.add_recent_project(self.current_project.name, self.project_path, duration_str)
                hive_logger.info(f"Project saved successfully to {self.project_path}")
            else:
                hive_logger.info(f"Rolling auto-save backup created: {save_target}")
                
            global_signals.project_saved.emit(self.project_path)
            return True
        except Exception as e:
            hive_logger.error(f"Error saving project to {save_target}: {e}")
            return False

    def _create_timestamped_backup(self):
        """Creates a timestamped backup in a 'backups/' sub-folder and maintains a 10-file limit."""
        try:
            project_dir = os.path.dirname(self.project_path)
            backup_dir = os.path.join(project_dir, "backups")
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_filename = f"backup_{timestamp}.hive"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            shutil.copy2(self.project_path, backup_path)
            
            # Retention Policy: Keep latest 10
            backups = sorted(
                [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith("backup_") and f.endswith(".hive")],
                key=os.path.getmtime
            )
            
            while len(backups) > 10:
                oldest = backups.pop(0)
                os.remove(oldest)
                hive_logger.debug(f"Removed old backup: {oldest}")
                
        except Exception as e:
            hive_logger.error(f"Failed to create timestamped backup: {e}")

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
            
            hive_logger.info(f"Project soft-deleted: {file_path}")
            return True
        except Exception as e:
            hive_logger.error(f"Error soft-deleting project {file_path}: {e}")
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
            hive_logger.info(f"Project recovered from {trash_path} to {dest}")
            return True
        except Exception as e:
            hive_logger.error(f"Failed to recover project {trash_path}: {e}")
            return False

    def permanent_delete(self, trash_path):
        src = Path(trash_path)
        if not src.exists(): return False
        try:
            if src.is_dir():
                shutil.rmtree(str(src))
            else:
                src.unlink()
            hive_logger.info(f"Project permanently deleted: {trash_path}")
            return True
        except Exception as e:
            hive_logger.error(f"Failed to delete permanently {trash_path}: {e}")
            return False
            
    def rename_project(self, old_path, new_name):
        """Robustly renames a project, handling directory renaming and in-memory state updates."""
        if not os.path.exists(old_path):
            hive_logger.error(f"Rename failed: Source file {old_path} does not exist.")
            return False
            
        old_dir = os.path.dirname(old_path)
        parent_dir = os.path.dirname(old_dir)
        new_dir = os.path.join(parent_dir, new_name)
        new_path = os.path.join(new_dir, f"{new_name}.hive")
        
        # Check if we are in a standard project folder structure (folder name == file stem)
        is_standard_structure = os.path.basename(old_dir) == Path(old_path).stem
        
        try:
            if is_standard_structure:
                # Rename the whole directory
                is_case_change_only = os.path.abspath(old_dir).lower() == os.path.abspath(new_dir).lower()
                
                if os.path.exists(new_dir) and not is_case_change_only:
                    hive_logger.error(f"Cannot rename: Directory {new_dir} already exists.")
                    return False
                
                # Perform directory rename if it actually changed
                if os.path.abspath(old_dir) != os.path.abspath(new_dir):
                    os.rename(old_dir, new_dir)
                
                # Update file path inside the new directory
                old_file_in_new_dir = os.path.join(new_dir, os.path.basename(old_path))
                if os.path.exists(old_file_in_new_dir):
                    if os.path.abspath(old_file_in_new_dir) != os.path.abspath(new_path):
                        if os.path.exists(new_path) and not is_case_change_only:
                            os.remove(new_path) # Fallback to prevent WinError 183 if ghost file exists
                        os.rename(old_file_in_new_dir, new_path)
            else:
                # Just rename the file
                is_case_change_only = os.path.abspath(old_path).lower() == os.path.abspath(new_path).lower()
                if os.path.exists(new_path) and not is_case_change_only:
                    hive_logger.error(f"Cannot rename: File {new_path} already exists.")
                    return False
                if os.path.abspath(old_path) != os.path.abspath(new_path):
                    os.rename(old_path, new_path)
                new_dir = old_dir # Dir didn't change

            # Update in-memory state
            if self.current_project:
                self.current_project.name = new_name
            self.project_path = new_path
            
            # Update project data inside the file
            with open(new_path, 'rb') as f:
                project_dict = msgpack.unpackb(f.read(), raw=False)
            
            project_dict['name'] = new_name
            
            with open(new_path, 'wb') as f:
                packed_data = msgpack.packb(project_dict, default=self._msgpack_default, use_bin_type=True)
                f.write(packed_data)
            
            # Update app_config recent projects
            recent = app_config.data.get("recent_projects", [])
            duration_str = "00:00:00:00"
            
            # Normalize paths for comparison to avoid duplication issues
            def norm(p): return os.path.normpath(p).replace('\\', '/')
            
            norm_old = norm(old_path)
            
            for p in recent:
                if norm(p["path"]) == norm_old:
                    duration_str = p.get("duration", "00:00:00:00")
                    break
                    
            recent = [p for p in recent if norm(p["path"]) != norm_old]
            app_config.data["recent_projects"] = recent
            app_config.add_recent_project(new_name, new_path, duration_str)
            
            # Notify UI
            global_signals.project_renamed.emit(new_name)
            
            hive_logger.info(f"Project robustly renamed to {new_name} at {new_path}")
            return True
            
        except Exception as e:
            hive_logger.error(f"Error renaming project: {e}")
            return False

    def load_project(self, load_path):
        if not os.path.exists(load_path):
            # Try to recover from autosave or bak if the main is missing
            autosave_path = load_path + ".autosave"
            bak_path = load_path + ".bak"
            
            if os.path.exists(autosave_path):
                hive_logger.warning(f"Main project missing. Recovering from autosave: {autosave_path}")
                load_path = autosave_path
            elif os.path.exists(bak_path):
                hive_logger.warning(f"Main project missing. Recovering from backup: {bak_path}")
                load_path = bak_path
            else:
                hive_logger.error(f"Failed to load project: File does not exist at {load_path}")
                return False
            
        try:
            with open(load_path, 'rb') as f:
                data = f.read()
                project_dict = msgpack.unpackb(data, raw=False)
                
            self.current_project = self._rebuild_project_from_dict(project_dict)
            self.project_path = load_path.replace(".autosave", "").replace(".bak", "")
            
            # Preserve existing duration in config during load to prevent 00:00:00 resets
            existing_duration = "00:00:00:00"
            for p in app_config.data.get("recent_projects", []):
                if os.path.normpath(p["path"]) == os.path.normpath(self.project_path):
                    existing_duration = p.get("duration", "00:00:00:00")
                    break
            
            app_config.add_recent_project(self.current_project.name, self.project_path, duration_str=existing_duration)
            
            global_signals.project_loaded.emit(self.current_project)
            hive_logger.info(f"Project loaded successfully from {load_path}")
            return True
            
        except Exception as e:
            hive_logger.error(f"Primary load failed for {load_path}: {e}")
            # If main failed, try bak
            if not load_path.endswith(".bak") and not load_path.endswith(".autosave"):
                bak_path = load_path + ".bak"
                if os.path.exists(bak_path):
                    hive_logger.info(f"Attempting emergency recovery from .bak...")
                    return self.load_project(bak_path)
            return False

    def export_portable_project(self, target_zip_path):
        """Bundles the .hive project and all its media into a .hivezip file."""
        if not self.current_project or not self.project_path:
            return False
            
        import zipfile
        import tempfile
        
        try:
            with zipfile.ZipFile(target_zip_path, 'w', zipfile.ZIP_DEFLATED) as zhive:
                # 1. Save a clean copy of the project data
                temp_proj = copy.deepcopy(self.current_project)
                
                # 2. Collect all media paths and copy files
                media_mapping = {} # Original Path -> Relative ZIP Path
                
                # Check clips in all tracks
                for track in temp_proj.tracks:
                    for clip in track.clips:
                        if clip.file_path and os.path.exists(clip.file_path):
                            if clip.file_path not in media_mapping:
                                ext = os.path.splitext(clip.file_path)[1]
                                rel_path = f"media/asset_{len(media_mapping)}{ext}"
                                media_mapping[clip.file_path] = rel_path
                                zhive.write(clip.file_path, rel_path)
                            
                            clip.file_path = media_mapping[clip.file_path]
                
                # Check media bin
                new_bin = []
                for p in temp_proj.media_bin:
                    if os.path.exists(p):
                        if os.path.isdir(p):
                            # For now, we only bundle individual files used in timeline or direct in bin
                            # Folders are tricky, we'll skip the folder structure and just keep used files
                            pass
                        else:
                            if p not in media_mapping:
                                ext = os.path.splitext(p)[1]
                                rel_path = f"media/asset_{len(media_mapping)}{ext}"
                                media_mapping[p] = rel_path
                                zhive.write(p, rel_path)
                            new_bin.append(media_mapping[p])
                temp_proj.media_bin = new_bin
                
                # 3. Write modified .hive file to ZIP
                project_dict = asdict(temp_proj)
                packed_data = msgpack.packb(project_dict, default=self._msgpack_default, use_bin_type=True)
                zhive.writestr(f"{temp_proj.name}.hive", packed_data)
                
            hive_logger.info(f"Exported portable project to {target_zip_path}")
            return True
        except Exception as e:
            hive_logger.error(f"Portable export failed: {e}")
            return False

    def import_portable_project(self, zip_path, extract_root):
        """Unzips a .hivezip into the projects folder and returns the path to the extracted .hive file."""
        import zipfile
        if not os.path.exists(zip_path): return None
        
        try:
            project_name = os.path.splitext(os.path.basename(zip_path))[0]
            extract_dir = os.path.join(extract_root, project_name)
            
            # Prevent overwriting existing project with same name
            counter = 1
            while os.path.exists(extract_dir):
                extract_dir = os.path.join(extract_root, f"{project_name}_{counter}")
                counter += 1
                
            os.makedirs(extract_dir, exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zhive:
                zhive.extractall(extract_dir)
                
                # Locate the .hive file
                hive_files = list(Path(extract_dir).glob("*.hive"))
                if not hive_files:
                    return None
                    
                hive_path = str(hive_files[0])
                
                # Fix up media paths to be absolute on the new machine
                with open(hive_path, 'rb') as f:
                    project_dict = msgpack.unpackb(f.read(), raw=False)
                
                def fix_paths(data):
                    if isinstance(data, dict):
                        if "file_path" in data and data["file_path"] and data["file_path"].startswith("media/"):
                            data["file_path"] = os.path.join(extract_dir, data["file_path"]).replace('\\', '/')
                        for v in data.values(): fix_paths(v)
                    elif isinstance(data, list):
                        for i in range(len(data)):
                            if isinstance(data[i], str) and data[i].startswith("media/"):
                                data[i] = os.path.join(extract_dir, data[i]).replace('\\', '/')
                            else:
                                fix_paths(data[i])

                fix_paths(project_dict)
                
                # Ensure media_bin includes all extracted assets so they appear in the Media Tab
                media_dir = os.path.join(extract_dir, "media")
                if os.path.exists(media_dir):
                    extracted_assets = [os.path.join(media_dir, f).replace('\\', '/') for f in os.listdir(media_dir)]
                    # Merge with existing bin (which were just fixed by fix_paths)
                    current_bin = project_dict.get('media_bin', [])
                    project_dict['media_bin'] = list(set(current_bin + extracted_assets))

                # Save the fixed version
                packed_data = msgpack.packb(project_dict, default=self._msgpack_default, use_bin_type=True)
                with open(hive_path, 'wb') as f:
                    f.write(packed_data)
                
                # Register in recents
                app_config.add_recent_project(project_dict.get('name', 'Imported Project'), hive_path)
                
                hive_logger.info(f"Imported portable project to {hive_path}")
                return hive_path
                
        except Exception as e:
            hive_logger.error(f"Portable import failed: {e}")
            return None
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
