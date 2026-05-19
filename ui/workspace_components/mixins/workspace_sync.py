import os
import shutil
from core.project_manager import project_manager
from core.app_config import app_config
from core.signal_hub import global_signals
from core.logger import hive_logger as logger
from ui.workspace_components.project_settings_dialog import ProjectSettingsDialog

class WorkspaceSyncMixin:
    """Mixin for synchronizing workspace state with project data and settings."""
    def _on_project_loaded(self, project_data):
        logger.info(f"Workspace: Project loaded, updating settings labels")
        self._update_settings_labels(project_data)

    def _open_project_settings(self):
        if not project_manager.current_project:
            return
            
        was_copy_enabled = app_config.get_setting("copy_media_to_project", False)
            
        dialog = ProjectSettingsDialog(
            project_manager.current_project.resolution, 
            project_manager.current_project.fps, 
            self
        )
        
        if dialog.exec():
            now_copy_enabled = dialog.chk_copy_media.isChecked()
            app_config.set_setting("copy_media_to_project", now_copy_enabled)
            
            new_resolution = dialog.get_resolution()
            new_fps = dialog.get_fps()
            
            logger.info(f"Workspace: Project settings updated: res={new_resolution}, fps={new_fps}")
            project_manager.current_project.resolution = new_resolution
            project_manager.current_project.fps = new_fps
            
            self._update_settings_labels(project_manager.current_project)
            project_manager.save_project()
            
            global_signals.project_resolution_changed.emit(new_resolution)
            
            if now_copy_enabled and not was_copy_enabled:
                self._retroactively_copy_media()

    def _retroactively_copy_media(self):
        proj_dir = os.path.dirname(project_manager.project_path) if project_manager.project_path else None
        if not proj_dir: return

        logger.info("Workspace: Retroactively copying media to project directory")
        media_dir = os.path.join(proj_dir, "media")
        os.makedirs(media_dir, exist_ok=True)

        updated_paths = []
        path_mapping = {}
        changed = False

        for path in project_manager.current_project.media_bin:
            filename = os.path.basename(path)
            dest_path = os.path.join(media_dir, filename).replace('\\', '/')

            old_abs = os.path.abspath(path)
            dest_abs = os.path.abspath(dest_path)

            if not os.path.exists(dest_path) or old_abs != dest_abs:
                try:
                    shutil.copy2(path, dest_path)
                    updated_paths.append(dest_path)
                    path_mapping[old_abs] = dest_path
                    changed = True
                except Exception as e:
                    logger.error(f"Workspace: Failed to retroactively copy media file {path}: {e}")
                    updated_paths.append(path)
            else:
                updated_paths.append(path)

        if changed:
            logger.info(f"Workspace: Successfully copied {len(path_mapping)} media files; updating project manifest")
            project_manager.current_project.media_bin = updated_paths
            
            for track in project_manager.current_project.tracks:
                for clip in track.clips:
                    if clip.file_path:
                        c_abs = os.path.abspath(clip.file_path)
                        if c_abs in path_mapping:
                            clip.file_path = path_mapping[c_abs]

            project_manager.save_project()
            self.load_media_bin_from_paths(updated_paths)
            global_signals.project_loaded.emit(project_manager.current_project)

    def _update_settings_labels(self, project):
        if not project: return
        res = project.resolution
        fps = project.fps
        
        res_str = f"{res[0]}x{res[1]}"
        if res == (3840, 2160): res_str += " (4K)"
        elif res == (1920, 1080): res_str += " (HD)"
        elif res == (1080, 1920): res_str += " (9:16 Vertical)"
        elif res == (1080, 1080): res_str += " (Square)"
            
        self.lbl_res_value.setText(res_str)
        fps_str = str(fps).rstrip('0').rstrip('.') if fps % 1 == 0 else str(fps)
        self.lbl_fps_value.setText(f"{fps_str} fps")
