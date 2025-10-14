"""Enhanced base classes for audio sources"""

import asyncio
import re
import time  # ✅ ADD IF MISSING
import traceback  # ✅ ADD IF MISSING
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple, List
from pathlib import Path
from config.settings import Config

class AudioSource(ABC):
    """Base audio source class with common functionality"""
    
    def __init__(self):
        self.downloads_dir = Config.DOWNLOADS_DIR
        self.session = None
    
    @abstractmethod
    async def search(self, query: str) -> Optional[Dict[str, Any]]:
        """Search for audio content"""
        pass
    
    @abstractmethod
    async def search_playlist(self, playlist_url: str) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """Search for playlist content"""
        pass
    
    @abstractmethod
    def is_url_supported(self, url: str) -> bool:
        """Check if URL is supported by this source"""
        pass
    
    def clean_filename(self, filename: str) -> str:
        """Clean filename for filesystem safety"""
        # Remove invalid characters
        cleaned = re.sub(r'[<>:"/\\|?*]', '', filename)
        # FIXED: Proper escaping
        cleaned = re.sub(r'[^\w\s\-\.]', '', cleaned)  # Escape the hyphen
        # Normalize whitespace
        cleaned = re.sub(r'\s+', '_', cleaned.strip())
        # Limit length
        return cleaned[:100] if len(cleaned) > 100 else cleaned
    
    def validate_url(self, url: str) -> bool:
        """Validate URL format and domain"""
        if not url.startswith(('http://', 'https://')):
            return False
        
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            return bool(parsed.netloc and parsed.scheme)
        except:
            return False
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.session and not self.session.closed:
            import inspect
            if inspect.iscoroutinefunction(self.session.close):
                try:
                    await self.session.close()  # type: ignore[misc]
                except Exception:
                    pass
            else:
                try:
                    self.session.close()
                except Exception:
                    pass

class BaseDownloader:
    """Base downloader with common functionality"""
    
    def __init__(self):
        self.downloads_dir = Config.DOWNLOADS_DIR
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
    
    def get_file_path(self, title: str, extension: str = 'mp3') -> Path:
        """Get safe file path for download"""
        safe_title = self.clean_filename(title)
        return self.downloads_dir / f"{safe_title}.{extension}"
    
    def clean_filename(self, filename: str) -> str:
        """Clean filename for filesystem safety"""
        cleaned = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.'))
        return cleaned.replace(' ', '_').strip()[:100]
    
    async def validate_file(self, file_path: Path, min_size: int = 1000) -> bool:
        """Validate downloaded file"""
        try:
            if not file_path.exists():
                return False
            
            if file_path.stat().st_size < min_size:
                file_path.unlink(missing_ok=True)
                return False
            
            return True
        except Exception as e:
            logging.debug("Error validating file: %s", e)
            return False

class PlaylistSource(ABC):
    """Base playlist source class"""
    
    @abstractmethod
    async def get_playlist_info(self, url: str):
        """Get playlist information"""
        pass
    
    @abstractmethod
    async def get_playlist_tracks(self, url: str):
        """Get all tracks from playlist"""
        pass