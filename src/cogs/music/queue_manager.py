import asyncio
from collections import deque
import random
import time

# ✅ Add metadata cache to MusicQueue
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
        self.cache = {}  # Cache for preloaded players
        self.processing = False  # Flag to prevent concurrent processing
        self.metadata_cache = {}  # Cache song metadata
        self.cache_expiry = {}    # Track cache expiration
        
    def add_request(self, request_data):
        """Add a raw request to the queue with proper order"""
        # ✅ FIXED: Calculate order based on total requests added (not current queue length)
        if 'order' not in request_data:
            # Calculate proper order based on existing requests
            existing_orders = [req.get('order', 0) for req in self.queue]
            next_order = max(existing_orders, default=0) + 1
            request_data['order'] = next_order
    
        # Add timestamp if not present
        if 'timestamp' not in request_data:
            request_data['timestamp'] = time.time()
    
        self.queue.append(request_data)
        
        query = request_data.get('query', 'Unknown')
        order = request_data.get('order', '?')
        print(f"📋 [QUEUE] Added request #{order}: {query[:30]}")
    
    def add_processed_song(self, song_data):
        """Add a processed song to the ready queue"""
        self.processed_queue.append(song_data)
        
    def get_next(self):
        """Get next processed song"""
        # ✅ Only add to history if we actually had a current song
        if self.current and self.current.get('title'):
            # Avoid duplicate entries in history
            if not self.history or self.history[-1].get('id') != self.current.get('id'):
                self.history.append(self.current)
                print(f"📝 Added to history: {self.current.get('title', 'Unknown')}")
            else:
                print(f"📝 Song already in history, skipping: {self.current.get('title', 'Unknown')}")

        if self.processed_queue:
            self.current = self.processed_queue.popleft()
            print(f"🎵 Now current: {self.current.get('title', 'Unknown')}")
            return self.current
        else:
            self.current = None
            print("📭 No more songs in queue")
        return None
        
    def get_previous(self):
        """Get previous song - IMPROVED VERSION"""
        if not self.history:
            print("📭 No previous songs in history")
            return None
        
        # ✅ FIXED: Don't add current to processed_queue if it's None
        if self.current and self.current.get('title'):
            print(f"🔄 Moving current song back to front: {self.current.get('title', 'Unknown')}")
            self.processed_queue.appendleft(self.current)
        
        # ✅ Get the last song from history
        previous_song = self.history.pop()
        
        # ✅ CRITICAL: Set this as current immediately
        self.current = previous_song
        print(f"⏮️ Retrieved previous: {previous_song.get('title', 'Unknown')}")
        
        return self.current

    def add_to_history(self, song_data):
        """Manually add a song to history (for better control)"""
        if song_data and song_data.get('title'):
            # Avoid duplicates
            if not self.history or self.history[-1].get('id') != song_data.get('id'):
                self.history.append(song_data)
                print(f"📝 Manually added to history: {song_data.get('title', 'Unknown')}")
        
    def clear(self):
        """Clear all queues"""
        if self.current:
            print(f"🗑️ Clearing current song: {self.current.get('title', 'Unknown')}")
    
        self.queue.clear()
        self.processed_queue.clear()
        self.current = None
        self.cache.clear()
        print("🗑️ All queues cleared")
        
    def shuffle(self):
        """Shuffle processed queue"""
        queue_list = list(self.processed_queue)
        random.shuffle(queue_list)
        self.processed_queue = deque(queue_list)
        
    def set_volume(self, volume):
        """Set volume (10-200%)"""
        self.volume = max(10, min(200, volume))
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
    
    def cache_metadata(self, song_id, metadata, ttl=3600):
        """Cache song metadata with TTL"""
        import time
        self.metadata_cache[song_id] = metadata
        self.cache_expiry[song_id] = time.time() + ttl
    
    def get_cached_metadata(self, song_id):
        """Get cached metadata if not expired"""
        import time
        if song_id in self.metadata_cache:
            if time.time() < self.cache_expiry.get(song_id, 0):
                return self.metadata_cache[song_id]
            else:
                # Expired, remove
                self.metadata_cache.pop(song_id, None)
                self.cache_expiry.pop(song_id, None)
        return None
    
    def get_cache_info(self):
        """Get detailed cache information"""
        cache_info = {
            'cached_count': len(self.cache),
            'cached_songs': [],
            'next_songs': [],
            'cache_coverage': 0
        }
        
        # Get list of cached songs
        for url, player in self.cache.items():
            # Try to find the song title from processed queue
            cached_title = 'Unknown'
            for song in self.processed_queue:
                if song['webpage_url'] == url:
                    cached_title = song.get('title', 'Unknown')[:50]
                    break
            cache_info['cached_songs'].append(cached_title)
        
        # Get next songs in queue
        processed_list = list(self.processed_queue)
        for i in range(min(3, len(processed_list))):
            song = processed_list[i]
            is_cached = song['webpage_url'] in self.cache
            cache_info['next_songs'].append({
                'title': song.get('title', 'Unknown')[:50],
                'cached': is_cached
            })
        
        # Calculate cache coverage
        if processed_list:
            cached_next = sum(1 for song in processed_list[:2] if song['webpage_url'] in self.cache)
            cache_info['cache_coverage'] = (cached_next / min(2, len(processed_list))) * 100
        
        return cache_info

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