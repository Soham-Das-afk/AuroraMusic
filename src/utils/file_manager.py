import os
import time
from pathlib import Path
from config.settings import Config

class FileManager:
    """Manage downloaded music files with configurable retention"""
    
    def __init__(self):
        self.downloads_dir = Config.DOWNLOADS_DIR
        self.max_age_hours = 24  # Keep files for 24 hours
        self.max_files = 100     # Keep max 100 files
    
    async def cleanup_old_files(self):
        """Clean up old downloaded files"""
        try:
            if not self.downloads_dir.exists():
                return
            
            current_time = time.time()
            files = list(self.downloads_dir.glob("*.mp3"))
            
            # Sort by modification time (oldest first)
            files.sort(key=lambda f: f.stat().st_mtime)
            
            deleted_count = 0
            
            # Delete files older than max_age_hours
            for file_path in files:
                file_age = current_time - file_path.stat().st_mtime
                age_hours = file_age / 3600
                
                if age_hours > self.max_age_hours:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                        print(f"🗑️ Deleted old file: {file_path.name}")
                    except Exception as e:
                        print(f"❌ Error deleting {file_path.name}: {e}")
            
            # If still too many files, delete oldest ones
            remaining_files = list(self.downloads_dir.glob("*.mp3"))
            if len(remaining_files) > self.max_files:
                remaining_files.sort(key=lambda f: f.stat().st_mtime)
                excess_files = remaining_files[:-self.max_files]
                
                for file_path in excess_files:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                        print(f"🗑️ Deleted excess file: {file_path.name}")
                    except Exception as e:
                        print(f"❌ Error deleting {file_path.name}: {e}")
            
            if deleted_count > 0:
                print(f"🧹 Cleanup complete: {deleted_count} files deleted")
            
        except Exception as e:
            print(f"❌ Error during cleanup: {e}")
    
    def get_storage_info(self):
        """Get storage information"""
        try:
            if not self.downloads_dir.exists():
                return {"files": 0, "size_mb": 0}
            
            files = list(self.downloads_dir.glob("*.mp3"))
            total_size = sum(f.stat().st_size for f in files)
            
            return {
                "files": len(files),
                "size_mb": round(total_size / (1024 * 1024), 2)
            }
        except Exception:
            return {"files": 0, "size_mb": 0}