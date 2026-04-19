# core/font_manager.py
"""
Font discovery, Google Fonts download, and favorites management.
Provides system fonts + downloaded fonts + searchable curated Google Fonts catalog.
"""

import os
import json
import zipfile
import io
import re
import threading
from pathlib import Path
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import QObject, Signal

from core.app_config import app_config

# ---------------------------------------------------------------------------
# Curated catalog of popular Google Fonts (name -> weight variants available)
# ---------------------------------------------------------------------------
GOOGLE_FONTS_CATALOG = [
    "Roboto", "Open Sans", "Lato", "Montserrat", "Poppins", "Inter",
    "Oswald", "Raleway", "Nunito", "Ubuntu", "Merriweather", "Playfair Display",
    "PT Sans", "Rubik", "Work Sans", "Quicksand", "Barlow", "Karla",
    "Fira Sans", "Mulish", "Kanit", "Titillium Web", "Hind", "DM Sans",
    "Josefin Sans", "Archivo", "Cabin", "Overpass", "Manrope", "Outfit",
    "Sour Gummy", "Bebas Neue", "Anton", "Lobster", "Pacifico",
    "Permanent Marker", "Satisfy", "Dancing Script", "Shadows Into Light",
    "Indie Flower", "Caveat", "Comfortaa", "Righteous", "Bangers",
    "Bungee", "Russo One", "Teko", "Orbitron", "Press Start 2P",
    "Audiowide", "Black Ops One", "Fugaz One", "Faster One", "Bungee Shade",
    "Fredoka One", "Lilita One", "Passion One", "Titan One",
    "Abril Fatface", "Alfa Slab One", "Arvo", "Bitter", "Crete Round",
    "Domine", "Libre Baskerville", "Lora", "Noto Serif", "Roboto Slab",
    "Source Serif Pro", "Zilla Slab", "Crimson Text", "EB Garamond",
    "IBM Plex Serif", "Spectral", "PT Serif", "Vollkorn", "Cormorant Garamond",
    "Space Grotesk", "Space Mono", "JetBrains Mono", "Fira Code",
    "Source Code Pro", "Inconsolata", "IBM Plex Mono", "Roboto Mono",
    "Cousine", "Anonymous Pro", "Cutive Mono", "Share Tech Mono",
    "Nanum Gothic", "Nanum Myeongjo", "Black Han Sans", "Do Hyeon",
    "Jua", "Sunflower", "Gothic A1", "Single Day",
    "Baloo 2", "Chakra Petch", "Exo 2", "Fredoka", "Lexend",
    "Nunito Sans", "Plus Jakarta Sans", "Red Hat Display", "Sora",
    "Urbanist", "Yanone Kaffeesatz", "Zen Kaku Gothic New",
    "Noto Sans", "Noto Sans JP", "Noto Sans KR", "Noto Sans SC",
    "Noto Sans TC", "Noto Sans Arabic", "Noto Sans Thai",
    "Sarabun", "Prompt", "Mitr", "Itim", "Kodchasan",
    "Sacramento", "Great Vibes", "Alex Brush", "Allura",
    "Cinzel", "Cinzel Decorative", "Yeseva One",
    "Secular One", "Assistant", "Varela Round", "Heebo",
    "Catamaran", "Mukta", "Hind Siliguri", "Yantramanav",
    "Pathway Extreme", "Figtree", "Geist", "Gabarito",
    "Onest", "Bricolage Grotesque", "Afacad", "Instrument Sans",
    "Climate Crisis", "Silkscreen", "Jersey 10", "Pixelify Sans",
    "Micro 5", "Jacquard 12", "Foldit", "Rubik Glitch",
    "Rubik Vinyl", "Rubik Burned", "Rubik Dirt",
    "Rubik Iso", "Rubik Marker Hatch", "Rubik Storm",
    "Bungee Inline", "Bungee Outline", "Bungee Hairline",
]


class FontManager(QObject):
    """Singleton font manager providing system + downloaded fonts with favorites."""
    
    font_downloaded = Signal(str)  # Emits family name when a font finishes downloading
    download_progress = Signal(str, str)  # Emits (font_name, status_message)
    download_failed = Signal(str, str)    # Emits (font_name, error_message)
    
    def __init__(self):
        super().__init__()
        self._fonts_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "assets" / "fonts"
        self._fonts_dir.mkdir(parents=True, exist_ok=True)
        
        self._favorites = set()
        self._recent = []
        self._downloaded_families = set()
        self._system_families = []
        self._initialized = False
        
    def _ensure_initialized(self):
        if not self._initialized:
            self._initialized = True
            self._load_preferences()
            self._register_downloaded_fonts()
            self._refresh_system_fonts()
    
    # --- Discovery ---
    
    def _refresh_system_fonts(self):
        """Get all available font families from Qt's font database."""
        db = QFontDatabase()
        self._system_families = sorted(set(db.families()))
    
    def _register_downloaded_fonts(self):
        """Register all .ttf/.otf files in the app's fonts directory with Qt."""
        if not self._fonts_dir.exists():
            return
        
        for font_file in self._fonts_dir.glob("**/*.ttf"):
            font_id = QFontDatabase.addApplicationFont(str(font_file))
            if font_id >= 0:
                families = QFontDatabase.applicationFontFamilies(font_id)
                self._downloaded_families.update(families)
        
        for font_file in self._fonts_dir.glob("**/*.otf"):
            font_id = QFontDatabase.addApplicationFont(str(font_file))
            if font_id >= 0:
                families = QFontDatabase.applicationFontFamilies(font_id)
                self._downloaded_families.update(families)
        
        # Refresh system fonts after registering new ones
        self._refresh_system_fonts()
    
    def get_all_fonts(self):
        """Returns a sorted list of all available font families (system + downloaded)."""
        self._ensure_initialized()
        return self._system_families
    
    def get_downloaded_fonts(self):
        """Returns font families that were downloaded via this manager."""
        self._ensure_initialized()
        return sorted(self._downloaded_families)
    
    def get_google_catalog(self):
        """Returns the curated list of Google Fonts available for download."""
        return GOOGLE_FONTS_CATALOG
    
    def get_downloadable_fonts(self):
        """Returns Google Fonts that are NOT yet installed/downloaded."""
        self._ensure_initialized()
        available = set(self._system_families)
        return [f for f in GOOGLE_FONTS_CATALOG if f not in available]
    
    def is_downloaded(self, family_name):
        """Check if a font was downloaded (vs system-installed)."""
        self._ensure_initialized()
        return family_name in self._downloaded_families
    
    # --- Favorites ---
    
    def get_favorites(self):
        """Returns the user's favorite font families."""
        self._ensure_initialized()
        return sorted(self._favorites)
    
    def toggle_favorite(self, family_name):
        """Add or remove a font from favorites."""
        self._ensure_initialized()
        if family_name in self._favorites:
            self._favorites.discard(family_name)
        else:
            self._favorites.add(family_name)
        self._save_preferences()
    
    def is_favorite(self, family_name):
        self._ensure_initialized()
        return family_name in self._favorites
    
    # --- Recent ---
    
    def get_recent(self):
        """Returns recently used fonts (max 10)."""
        self._ensure_initialized()
        return self._recent[:10]
    
    def mark_used(self, family_name):
        """Moves a font to the top of the recent list."""
        self._ensure_initialized()
        if family_name in self._recent:
            self._recent.remove(family_name)
        self._recent.insert(0, family_name)
        self._recent = self._recent[:20]  # Keep max 20
        self._save_preferences()
    
    # --- Google Fonts Download ---
    
    def download_font(self, family_name):
        """Downloads a Google Font in a background thread."""
        thread = threading.Thread(target=self._download_worker, args=(family_name,), daemon=True)
        thread.start()
    
    def _download_worker(self, family_name):
        """Background thread: downloads font from Google Fonts API."""
        import urllib.request
        import urllib.error
        
        try:
            self.download_progress.emit(family_name, "Connecting...")
            
            # Use Google Fonts CSS API with old Android User-Agent to force TTF returns
            UA = "Mozilla/5.0 (Linux; U; Android 4.1.1; en-gb; Build/KLP) AppleWebKit/534.30 (KHTML, like Gecko) Version/4.0 Safari/534.30"
            encoded_name = family_name.replace(" ", "+")
            css_url = f"https://fonts.googleapis.com/css2?family={encoded_name}:wght@100;200;300;400;500;600;700;800;900&display=swap"
            
            req = urllib.request.Request(css_url, headers={"User-Agent": UA})
            
            try:
                with urllib.request.urlopen(req, timeout=15) as response:
                    css_text = response.read().decode("utf-8")
            except Exception:
                # If css2 fails, try the older api
                css_url = f"https://fonts.googleapis.com/css?family={encoded_name}"
                req = urllib.request.Request(css_url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=15) as response:
                    css_text = response.read().decode("utf-8")
                    
            # Parse URLs from the CSS
            ttf_urls = set(re.findall(r'url\((https?://[^)]+)\)', css_text))
            
            if not ttf_urls:
                # Fallback: try the ZIP download
                self._download_zip_fallback(family_name)
                return
            
            # Create font family directory
            font_dir = self._fonts_dir / family_name.replace(" ", "_")
            font_dir.mkdir(parents=True, exist_ok=True)
            
            self.download_progress.emit(family_name, f"Downloading {len(ttf_urls)} variants...")
            
            for i, url in enumerate(ttf_urls):
                clean_name = family_name.replace(' ', '_')
                dest = font_dir / f"{clean_name}_{i}.ttf"
                
                if not dest.exists():
                    req = urllib.request.Request(url, headers={"User-Agent": UA})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        with open(dest, "wb") as f:
                            f.write(resp.read())
                
                # Register with Qt
                font_id = QFontDatabase.addApplicationFont(str(dest))
                if font_id >= 0:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    self._downloaded_families.update(families)
            
            self._refresh_system_fonts()
            self.download_progress.emit(family_name, "Complete!")
            self.font_downloaded.emit(family_name)
            
        except Exception as e:
            self.download_failed.emit(family_name, str(e))
    
    def _download_zip_fallback(self, family_name):
        """Fallback: Download from Google Fonts ZIP endpoint."""
        import urllib.request
        
        try:
            encoded_name = family_name.replace(" ", "+")
            zip_url = f"https://fonts.google.com/download?family={encoded_name}"
            
            req = urllib.request.Request(zip_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            })
            
            self.download_progress.emit(family_name, "Downloading ZIP...")
            
            with urllib.request.urlopen(req, timeout=30) as response:
                zip_data = response.read()
            
            font_dir = self._fonts_dir / family_name.replace(" ", "_")
            font_dir.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(('.ttf', '.otf')) and not name.startswith('__'):
                        zf.extract(name, font_dir)
                        extracted_path = font_dir / name
                        font_id = QFontDatabase.addApplicationFont(str(extracted_path))
                        if font_id >= 0:
                            families = QFontDatabase.applicationFontFamilies(font_id)
                            self._downloaded_families.update(families)
            
            self._refresh_system_fonts()
            self.download_progress.emit(family_name, "Complete!")
            self.font_downloaded.emit(family_name)
            
        except Exception as e:
            self.download_failed.emit(family_name, str(e))
    
    # --- Persistence ---
    
    def _get_prefs_path(self):
        return self._fonts_dir / "_font_prefs.json"
    
    def _load_preferences(self):
        path = self._get_prefs_path()
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._favorites = set(data.get("favorites", []))
                self._recent = data.get("recent", [])
            except Exception:
                pass
    
    def _save_preferences(self):
        path = self._get_prefs_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "favorites": sorted(self._favorites),
                    "recent": self._recent[:20]
                }, f, indent=2)
        except Exception:
            pass


# Global singleton
font_manager = FontManager()
