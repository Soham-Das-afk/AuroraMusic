import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from config.settings import Config
import asyncio
import time

class HistoryManager:
    """Manages reading and writing playback history to a JSON file."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.history_file = Config.DATA_DIR / "playback_history.json"
            self._history_data: Dict[str, List[Dict[str, Any]]] = {}
            self._lock = asyncio.Lock()
            self._load_history()
            self._initialized = True

    def _load_history(self):
        """Loads the history from the JSON file into memory."""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self._history_data = json.load(f)
            else:
                self._history_data = {}
                self._save_history()
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"❌ Error loading playback history: {e}")
            self._history_data = {}

    def _save_history(self):
        """Saves the current in-memory history to the JSON file."""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self._history_data, f, indent=4)
        except IOError as e:
            logging.error(f"❌ Error saving playback history: {e}")

    async def add_to_history(self, guild_id: int, user_id: int, song_data: Dict[str, Any]):
        """Adds a song to the playback history for a specific guild."""
        async with self._lock:
            guild_str = str(guild_id)
            if guild_str not in self._history_data:
                self._history_data[guild_str] = []

            history_entry = {
                "user_id": user_id,
                "song": song_data,
                "timestamp": time.time()
            }

            self._history_data[guild_str].append(history_entry)

            max_history = getattr(Config, "MAX_HISTORY_SIZE", 50)
            if len(self._history_data[guild_str]) > max_history:
                self._history_data[guild_str].pop(0)

            self._save_history()
            logging.info(f"📜 Added to history for guild {guild_id}: {song_data.get('title')}")

    async def get_last_song(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Gets the most recently played song for a guild from the history."""
        async with self._lock:
            guild_str = str(guild_id)
            if guild_str in self._history_data and self._history_data[guild_str]:
                last_entry = self._history_data[guild_str].pop()
                self._save_history()
                return last_entry.get("song")
            return None

history_manager = HistoryManager()
