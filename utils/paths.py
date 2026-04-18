import os
from pathlib import Path

def get_project_root() -> Path:
    """Returns project root directory."""
    return Path(__file__).parent.parent

def get_asset_path(*paths) -> str:
    """Returns absolute path to an asset, constructed dynamically."""
    return str(get_project_root().joinpath("assets", *paths))
