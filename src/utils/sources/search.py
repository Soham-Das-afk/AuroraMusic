import asyncio
import re
from typing import Optional, Tuple, List, Dict, Any
from .spotify import spotify_handler
from .youtube import youtube_handler  # ✅ Import the singleton instance

# ✅ Add input validation
def validate_query(query: str) -> bool:
    """Validate search query for safety and efficiency"""
    if not query or len(query.strip()) == 0:
        return False
    
    if len(query) > 500:
        return False
    
    # Check for malicious patterns
    malicious_patterns = [
        r'javascript:',
        r'<script',
        r'data:',
        r'file://',
        r'ftp://',
    ]
    
    for pattern in malicious_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return False
    
    # URL validation
    if query.startswith(('http://', 'https://')):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(query)
            allowed_domains = [
                'youtube.com', 'youtu.be', 'music.youtube.com',
                'open.spotify.com', 'spotify.com'
            ]
            domain = parsed.netloc.lower()
            if not any(allowed in domain for allowed in allowed_domains):
                return False
        except Exception:
            return False
    
    return True

async def search_song(query: str) -> Optional[Dict[str, Any]]:
    """Universal song search with validation and optimization"""
    try:
        # ✅ Input validation
        if not validate_query(query):
            print(f"❌ Invalid query: {query}")
            return None
        
        # ✅ Normalize YouTube URLs (shorts, etc.) before search
        if youtube_handler.is_url_supported(query):
            query = youtube_handler.clean_url(query)
        
        # ✅ Determine source and route accordingly
        if spotify_handler.is_url_supported(query):
            print("🎵 Routing to Spotify search")
            return await _search_spotify_song(query)
        elif youtube_handler.is_url_supported(query):
            print("🎵 Routing to YouTube search")
            return await youtube_handler.search(query)
        else:
            # Default to YouTube for text searches
            print("🎵 Default routing to YouTube search")
            return await youtube_handler.search(query)
            
    except Exception as e:
        print(f"❌ Universal search error: {e}")
        return None

async def search_playlist(playlist_url: str) -> Tuple[Optional[Dict], List[Dict]]:
    """Universal playlist search with source detection"""
    try:
        # ✅ Input validation
        if not validate_query(playlist_url):
            print(f"❌ Invalid playlist URL: {playlist_url}")
            return None, []
        
        # ✅ Route based on source
        if spotify_handler.is_url_supported(playlist_url):
            print("📋 Routing to Spotify playlist")
            return await spotify_handler.search_playlist(playlist_url)
        elif youtube_handler.is_url_supported(playlist_url):
            print("📋 Routing to YouTube playlist")
            return await youtube_handler.search_playlist(playlist_url)
        else:
            print(f"❌ Unsupported playlist URL: {playlist_url}")
            return None, []
            
    except Exception as e:
        print(f"❌ Universal playlist search error: {e}")
        return None, []

async def _search_spotify_song(spotify_url: str) -> Optional[Dict[str, Any]]:
    """⚡ Fast Spotify to YouTube conversion"""
    try:
        if not spotify_handler.spotify:
            print("❌ Spotify client not available")
            return None
        
        content_type, spotify_id = spotify_handler.extract_spotify_id(spotify_url)
        
        if content_type != 'track':
            print(f"❌ Expected track, got {content_type}")
            return None
        
        # Get Spotify track info with timeout
        track_info = await asyncio.wait_for(
            spotify_handler.get_track_info(spotify_id),
            timeout=5.0  # 5 second timeout
        )
        
        if not track_info:
            print("❌ Failed to get Spotify track info")
            return None
        
        # ⚡ Single optimized search strategy
        search_query = f"{track_info['name']} {track_info['artist_str']}"
        print(f"🔍 Quick search: {search_query}")
        
        song_data = await asyncio.wait_for(
            youtube_handler.search(search_query),
            timeout=8.0  # 8 second timeout
        )
        
        if song_data:
            # Enhance with Spotify metadata
            song_data.update({
                'title': f"{track_info['name']} - {track_info['artist_str']}",
                'uploader': track_info['artist_str'],
                'duration': track_info.get('duration', song_data.get('duration')),
                'spotify_track': True,
                'spotify_info': track_info,
                'source': 'spotify->youtube'
            })
            
            print(f"✅ Found match quickly")
            return song_data
        
        print("❌ No YouTube match found")
        return None
        
    except asyncio.TimeoutError:
        print("⏰ Spotify search timeout")
        return None
    except Exception as e:
        print(f"❌ Spotify song search error: {e}")
        return None

def is_playlist_url(url: str) -> bool:
    """Enhanced playlist URL detection"""
    try:
        if not url or not isinstance(url, str):
            return False
        
        # ✅ Check Spotify playlists/albums
        if spotify_handler.is_url_supported(url):
            return 'playlist' in url.lower() or 'album' in url.lower()
        
        # ✅ Check YouTube playlists
        if youtube_handler.is_url_supported(url):
            return youtube_handler.is_playlist_url(url)
        
        return False
        
    except Exception as e:
        print(f"❌ Playlist detection error: {e}")
        return False

def get_source_type(url: str) -> str:
    """Determine the source type of a URL"""
    try:
        if spotify_handler.is_url_supported(url):
            if is_playlist_url(url):
                return 'spotify_playlist'
            else:
                return 'spotify_track'
        elif youtube_handler.is_url_supported(url):
            if youtube_handler.is_playlist_url(url):
                return 'youtube_playlist'
            else:
                return 'youtube_video'
        else:
            return 'search_query'
    except Exception:
        return 'unknown'

# ✅ Performance monitoring
class SearchMetrics:
    """Track search performance metrics"""
    
    def __init__(self):
        self.search_count = 0
        self.success_count = 0
        self.spotify_count = 0
        self.youtube_count = 0
        self.avg_response_time = 0.0
        self._response_times = []
    
    def record_search(self, source: str, success: bool, response_time: float):
        """Record search metrics"""
        self.search_count += 1
        if success:
            self.success_count += 1
        
        if source == 'spotify':
            self.spotify_count += 1
        elif source == 'youtube':
            self.youtube_count += 1
        
        self._response_times.append(response_time)
        if len(self._response_times) > 100:  # Keep last 100 measurements
            self._response_times.pop(0)
        
        self.avg_response_time = sum(self._response_times) / len(self._response_times)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get search statistics"""
        success_rate = (self.success_count / self.search_count * 100) if self.search_count > 0 else 0
        
        return {
            'total_searches': self.search_count,
            'success_rate': f"{success_rate:.1f}%",
            'spotify_searches': self.spotify_count,
            'youtube_searches': self.youtube_count,
            'avg_response_time': f"{self.avg_response_time:.2f}s"
        }

# Global metrics instance
search_metrics = SearchMetrics()