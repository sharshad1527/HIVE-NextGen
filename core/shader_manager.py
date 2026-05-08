import os
import time
import re
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from PySide6.QtCore import QObject, Signal, QFileSystemWatcher
from PySide6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram
from PySide6.QtGui import QOpenGLFunctions
from core.logger import hive_logger

class ShaderManager(QObject):
    """
    Centralized registry for OpenGL shader programs with hot-reloading,
    preprocessing (#include), and uniform caching.
    """
    shader_reloaded = Signal(str) # Emits program name when reloaded

    def __init__(self):
        super().__init__()
        self.programs: Dict[str, QOpenGLShaderProgram] = {}
        self.shader_paths: Dict[str, str] = {} # program_name -> file_path
        self.uniform_caches: Dict[str, Dict[str, int]] = {} # program_name -> {uniform_name -> location}
        self.include_paths: List[Path] = [Path(__file__).parent / "shaders"]
        
        self.watcher = QFileSystemWatcher()
        self.watcher.fileChanged.connect(self._on_file_changed)
        
        # Track which program depends on which file (including #includes)
        self.file_dependencies: Dict[str, List[str]] = {} # file_path -> [program_names]

    def get_program(self, name: str) -> Optional[QOpenGLShaderProgram]:
        """Returns a compiled shader program by name."""
        return self.programs.get(name)

    def load_program(self, name: str, file_path: str) -> bool:
        """
        Loads and compiles a shader program from a single file.
        The file should contain both vertex and fragment shaders separated by
        '// #shader vertex' and '// #shader fragment' tags.
        """
        full_path = str(Path(file_path).absolute())
        self.shader_paths[name] = full_path
        
        success = self._compile_program(name, full_path)
        
        if success:
            if full_path not in self.watcher.files():
                self.watcher.addPath(full_path)
            
            # Update dependency mapping
            if full_path not in self.file_dependencies:
                self.file_dependencies[full_path] = []
            if name not in self.file_dependencies[full_path]:
                self.file_dependencies[full_path].append(name)
                
        return success

    def _compile_program(self, name: str, file_path: str) -> bool:
        """Internal method to compile and link a program."""
        hive_logger.debug(f"ShaderManager: Starting compilation for '{name}' from {file_path}")
        try:
            with open(file_path, 'r') as f:
                source = f.read()
        except Exception as e:
            hive_logger.error(f"ShaderManager: Failed to read {file_path}: {e}")
            return False

        # Preprocess source (handle #include and split vertex/fragment)
        processed_source, dependencies = self._preprocess(source, Path(file_path).parent)
        hive_logger.debug(f"ShaderManager: Preprocessing complete for '{name}'. Dependencies: {len(dependencies)}")
        
        # Track include dependencies for hot-reloading
        for dep in dependencies:
            dep_path = str(dep.absolute())
            if dep_path not in self.watcher.files():
                self.watcher.addPath(dep_path)
            if dep_path not in self.file_dependencies:
                self.file_dependencies[dep_path] = []
            if name not in self.file_dependencies[dep_path]:
                self.file_dependencies[dep_path].append(name)

        # Split into vertex and fragment sources
        v_source, f_source = self._split_source(processed_source)
        if not v_source or not f_source:
            hive_logger.error(f"ShaderManager: Missing vertex or fragment tag in {file_path}")
            return False

        program = QOpenGLShaderProgram()
        
        # Compile Vertex Shader
        if not program.addShaderFromSourceCode(QOpenGLShader.Vertex, v_source):
            hive_logger.error(f"ShaderManager: Vertex Shader Error ({name}):\n{program.log()}")
            return False
        hive_logger.debug(f"ShaderManager: Vertex shader compiled for '{name}'")
            
        # Compile Fragment Shader
        if not program.addShaderFromSourceCode(QOpenGLShader.Fragment, f_source):
            hive_logger.error(f"ShaderManager: Fragment Shader Error ({name}):\n{program.log()}")
            return False
        hive_logger.debug(f"ShaderManager: Fragment shader compiled for '{name}'")

        # Link Program
        if not program.link():
            hive_logger.error(f"ShaderManager: Link Error ({name}):\n{program.log()}")
            return False

        self.programs[name] = program
        self.uniform_caches[name] = {} # Reset uniform cache
        
        hive_logger.info(f"ShaderManager: Program '{name}' compiled and linked successfully.")
        return True

    def _preprocess(self, source: str, base_path: Path) -> Tuple[str, List[Path]]:
        """Handles #include directives recursively."""
        dependencies = []
        
        def replace_include(match):
            include_file = match.group(1)
            # Try relative to current file, then in standard include paths
            search_paths = [base_path] + self.include_paths
            
            for path in search_paths:
                full_path = path / include_file
                if full_path.exists():
                    dependencies.append(full_path)
                    with open(full_path, 'r') as f:
                        include_content = f.read()
                    # Recursively preprocess the included content
                    processed, deps = self._preprocess(include_content, full_path.parent)
                    dependencies.extend(deps)
                    return processed
            
            hive_logger.warning(f"ShaderManager: Could not find include file '{include_file}'")
            return f"// Failed include: {include_file}"

        # Match #include "file.glsl" or #include <file.glsl>
        include_pattern = re.compile(r'^\s*#include\s+["<](.*)[">]\s*$', re.MULTILINE)
        processed_source = include_pattern.sub(replace_include, source)
        
        return processed_source, dependencies

    def _split_source(self, source: str) -> Tuple[Optional[str], Optional[str]]:
        """Splits the combined source into vertex and fragment components."""
        # Using more robust split based on the tags
        parts = re.split(r'//\s*#shader\s+', source, flags=re.IGNORECASE)
        
        v_source = None
        f_source = None
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            if part.lower().startswith('vertex'):
                v_source = part[6:].strip() # Remove 'vertex'
            elif part.lower().startswith('fragment'):
                f_source = part[8:].strip() # Remove 'fragment'
        
        if v_source:
            hive_logger.debug(f"ShaderManager: Vertex source found ({len(v_source)} chars)")
        else:
            hive_logger.warning("ShaderManager: Vertex source NOT FOUND")
            
        if f_source:
            hive_logger.debug(f"ShaderManager: Fragment source found ({len(f_source)} chars)")
        else:
            hive_logger.warning("ShaderManager: Fragment source NOT FOUND")
            
        return v_source, f_source

    def get_uniform_location(self, program_name: str, uniform_name: str) -> int:
        """Returns cached uniform location, or queries and caches it if missing."""
        program = self.programs.get(program_name)
        if not program:
            return -1
            
        cache = self.uniform_caches.get(program_name, {})
        if uniform_name in cache:
            return cache[uniform_name]
            
        location = program.uniformLocation(uniform_name)
        cache[uniform_name] = location
        return location

    def _on_file_changed(self, path: str):
        """Handle hot-reloading when a shader file or include is modified."""
        hive_logger.debug(f"ShaderManager: File changed: {path}")
        
        # Some editors do a delete + create, which can trigger fileChanged with non-existent path
        # or remove it from the watcher.
        if not os.path.exists(path):
            # Wait a tiny bit and re-add if it comes back
            time.sleep(0.05)
            if os.path.exists(path):
                self.watcher.addPath(path)
            else:
                return

        programs_to_reload = self.file_dependencies.get(path, [])
        for name in programs_to_reload:
            hive_logger.info(f"ShaderManager: Hot-reloading program '{name}' due to change in {path}")
            if self._compile_program(name, self.shader_paths[name]):
                self.shader_reloaded.emit(name)

# Singleton access
_shader_manager = None

def get_shader_manager() -> ShaderManager:
    global _shader_manager
    if _shader_manager is None:
        _shader_manager = ShaderManager()
    return _shader_manager
