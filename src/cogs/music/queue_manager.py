import asyncio
from collections import deque
import random
import time
import logging
from utils.sources.youtube import youtube_handler
from utils.sources.search import search_song, search_playlist, is_playlist_url

class MusicQueue:
    """Enhanced music queue with caching support"""

    def __init__(self):
        self.queue = deque()  # Raw requests (not processed yet)
        self.processed_queue = deque()  # Processed, ready-to-play songs
        self.history = deque(maxlen=10)
        self.current = None
        self.volume = 100
        self.loop_mode = False
        self.position = 0
        self.start_time = 0
        self.processing = False  # Flag to prevent concurrent processing
        

    def add_request(self, request_data):
        """Add a raw request to the queue with proper order"""
        if 'order' not in request_data:
            existing_orders = [req.get('order', 0) for req in self.queue]
            next_order = max(existing_orders, default=0) + 1
            request_data['order'] = next_order

        if 'timestamp' not in request_data:
            request_data['timestamp'] = time.time()

        self.queue.append(request_data)

        query = request_data.get('query', 'Unknown')
        order = request_data.get('order', '?')

    def add_processed_song(self, song_data):
        """Add a processed song to the ready queue"""
        try:
            logging.info(f"🟢 Processed song queued: {song_data.get('title', 'Unknown')} requested_by={song_data.get('requested_by')}")
        except Exception:
            pass
        self.processed_queue.append(song_data)

    def get_next(self):
        """Get next processed song"""
        if self.current and self.current.get('title'):
            if not self.history or self.history[-1].get('id') != self.current.get('id'):
                self.history.append(self.current)
            else:
                pass

        if self.processed_queue:
            self.current = self.processed_queue.popleft()
            return self.current
        else:
            self.current = None
        return None

    def get_previous(self):
        """Get previous song - IMPROVED VERSION"""
        if not self.history:
            return None

        if self.current and self.current.get('title'):
            self.processed_queue.appendleft(self.current)

        previous_song = self.history.pop()

        self.current = previous_song

        return self.current

    def add_to_history(self, song_data):
        """Manually add a song to history (for better control)"""
        if song_data and song_data.get('title'):
            if not self.history or self.history[-1].get('id') != song_data.get('id'):
                self.history.append(song_data)

    def clear(self):
        """Clear all queues"""
        if self.current:
            pass

        self.queue.clear()
        self.processed_queue.clear()
        self.current = None
        

    def shuffle(self):
        """Shuffle processed queue"""
        queue_list = list(self.processed_queue)
        random.shuffle(queue_list)
        self.processed_queue = deque(queue_list)

    def set_volume(self, volume):
        """Set volume (10-200%)"""
        self.volume = max(10, min(200, volume))

    def update_current_song(self, song_data):
        """Update current song data (e.g. after conversion)"""
        self.current = song_data
        return self.volume

    def has_requests(self):
        """Check if there are unprocessed requests"""
        return len(self.queue) > 0

    def has_songs(self):
        """Check if there are processed songs ready to play"""
        return len(self.processed_queue) > 0

    def total_items(self):
        """Total items in both queues"""
        return len(self.queue) + len(self.processed_queue)

    def get_queue_info(self):
        """Get formatted queue information"""
        info = {
            'current': self.current,
            'next_songs': list(self.processed_queue)[:5],  # Next 5 songs
            'queue_size': len(self.processed_queue),
            'processing_size': len(self.queue),
            'total_size': self.total_items(),
            'loop_mode': self.loop_mode,
            'volume': self.volume,
            'history_size': len(self.history)
        }
        return info

    

class QueueManager:
    """Manages multiple guild queues"""

    def __init__(self):
        self.queues = {}
        self.locks = {}

    def get_queue(self, guild_id):
        """Get or create queue for guild"""
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue()
        return self.queues[guild_id]

    def get_lock(self, guild_id):
        """Get or create lock for guild"""
        if guild_id not in self.locks:
            self.locks[guild_id] = asyncio.Lock()
        return self.locks[guild_id]

    def remove_queue(self, guild_id):
        """Remove queue for guild"""
        if guild_id in self.queues:
            self.queues[guild_id].clear()
            del self.queues[guild_id]
        if guild_id in self.locks:
            del self.locks[guild_id]

    def get_all_active_guilds(self):
        """Get all guilds with active queues"""
        return list(self.queues.keys())

    def cleanup_empty_queues(self):
        """Remove empty queues"""
        empty_guilds = [
            guild_id for guild_id, queue in self.queues.items()
            if not queue.has_songs() and not queue.has_requests() and not queue.current
        ]

        for guild_id in empty_guilds:
            self.remove_queue(guild_id)

        return len(empty_guilds)

    async def add_to_queue(self, guild_id: int, query: str, requested_by: int):
        """Adds a song or playlist to the queue and returns info."""
        queue = self.get_queue(guild_id)
        playlist_info = None
        song_data = None

        if is_playlist_url(query):
            playlist_info, songs = await search_playlist(query)
            if not songs:
                return None, None
            for song in songs:
                song['requested_by'] = requested_by
                queue.add_request({'query': song.get('webpage_url') or song.get('title'), 'song_data': song, 'requested_by': requested_by})
            song_data = songs[0] # Return first song for immediate feedback
        else:
            song_data = await search_song(query)
            if not song_data:
                return None, None
            song_data['requested_by'] = requested_by
            queue.add_request({'query': song_data['webpage_url'], 'song_data': song_data, 'requested_by': requested_by})

        return song_data, playlist_info
