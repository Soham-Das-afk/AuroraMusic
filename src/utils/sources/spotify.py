import spotipy
import aiohttp
import asyncio
import re
import time
import traceback
from spotipy.oauth2 import SpotifyClientCredentials
from typing import Optional, Tuple, List, Dict, Any
from .base import AudioSource
try:
    from .youtube import youtube_handler
except ImportError:
    youtube_handler = None  # Fallback if not available

from config.settings import Config

class SpotifyHandler(AudioSource):
    """Enhanced Spotify handler with streaming processing like YouTube"""
    
    def __init__(self):
        super().__init__()
        self.youtube = youtube_handler
        self.spotify = None
        self.session: Optional[aiohttp.ClientSession] = None
        
        # ✅ Connection pooling
        self._connector = None
        
        # Initialize Spotify client
        self._initialize_spotify()
    
    def _initialize_spotify(self):
        """Initialize Spotify client with error handling"""
        if not Config.SPOTIFY_CLIENT_ID or not Config.SPOTIFY_CLIENT_SECRET:
            print("⚠️ Spotify credentials not configured")
            return
        
        try:
            credentials = SpotifyClientCredentials(
                client_id=Config.SPOTIFY_CLIENT_ID,
                client_secret=Config.SPOTIFY_CLIENT_SECRET
            )
            self.spotify = spotipy.Spotify(client_credentials_manager=credentials)
            print("✅ Spotify client initialized")
        except Exception as e:
            print(f"❌ Spotify initialization failed: {e}")
            self.spotify = None
    
    def is_url_supported(self, url: str) -> bool:
        """Check if URL is from Spotify"""
        return bool(re.search(r'(open\.spotify\.com|spotify\.com|spotify:)', url, re.IGNORECASE))
    
    def is_playlist_url(self, url: str) -> bool:
        """Check if Spotify URL is a playlist or album"""
        return self.is_url_supported(url) and ('playlist' in url or 'album' in url)
    
    def extract_spotify_id(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract Spotify ID and type from URL"""
        try:
            if 'open.spotify.com' in url:
                parts = url.split('/')
                if len(parts) >= 5:
                    content_type = parts[-2]
                    spotify_id = parts[-1].split('?')[0]
                    return content_type, spotify_id
            elif url.startswith('spotify:'):
                parts = url.split(':')
                if len(parts) >= 3:
                    content_type = parts[1]
                    spotify_id = parts[2]
                    return content_type, spotify_id
        except Exception as e:
            print(f"❌ Error extracting Spotify ID: {e}")
        
        return None, None
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create optimized aiohttp session"""
        if self.session is None or self.session.closed:
            if self._connector is None or self._connector.closed:
                self._connector = aiohttp.TCPConnector(
                    limit=100,
                    limit_per_host=10,
                    keepalive_timeout=60,
                    enable_cleanup_closed=True
                )

            self.session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self.session

    async def get_track_info(self, track_id: str):
        """Get track information from Spotify with caching"""
        try:
            if not self.spotify or not track_id:
                return None

            loop = asyncio.get_event_loop()
            track = await loop.run_in_executor(None, self.spotify.track, track_id)

            if not track:
                return None

            # ✅ FIXED: Handle None values in artists properly
            artists = []
            try:
                artists_raw = track.get('artists', [])
                for artist in artists_raw:
                    if artist and isinstance(artist, dict) and artist.get('name'):
                        artists.append(artist['name'])

                # If no valid artists, use fallback
                if not artists:
                    artists = ['Unknown Artist']

                artist_str = ', '.join(artists)

            except Exception as artist_error:
                print(f"⚠️ Artist processing error: {artist_error}")
                artists = ['Unknown Artist']
                artist_str = 'Unknown Artist'

            return {
                'id': track['id'],
                'name': track.get('name', 'Unknown Track'),
                'artists': artists,
                'artist_str': artist_str,
                'album': track.get('album', {}).get('name', 'Unknown Album') if track.get('album') else 'Unknown Album',
                'duration': track.get('duration_ms', 0) // 1000 if track.get('duration_ms') else 0,
                'popularity': track.get('popularity', 0),
                'explicit': track.get('explicit', False),
                'source': 'spotify'
            }
        except Exception as e:
            print(f"❌ Error getting Spotify track: {e}")
            return None

    async def search(self, query: str):
        """Search for a single Spotify track - REQUIRED ABSTRACT METHOD"""
        try:
            if not self.spotify:
                print("❌ Spotify client not available")
                return None

            content_type, spotify_id = self.extract_spotify_id(query)

            if content_type != 'track' or not spotify_id:
                print(f"❌ Expected track, got {content_type}")
                return None

            # Get Spotify track info
            track_info = await asyncio.wait_for(
                self.get_track_info(spotify_id),
                timeout=5.0
            )

            if not track_info:
                print("❌ Failed to get Spotify track info")
                return None

            # Convert to YouTube
            if self.youtube is not None:
                return await self.search_youtube_for_track(track_info)
            else:
                print("❌ YouTube handler not available")
                return None

        except asyncio.TimeoutError:
            print("⏰ Spotify search timeout")
            return None
        except Exception as e:
            print(f"❌ Spotify search error: {e}")
            return None

    async def get_playlist_info(self, playlist_id: str):
        """Get playlist metadata and tracks from Spotify"""
        try:
            if not self.spotify or not playlist_id:
                return None, []

            loop = asyncio.get_event_loop()

            print(f"🚀 [SPOTIFY PLAYLIST] Starting fast extraction: {playlist_id}")

            try:
                # Get playlist metadata quickly
                playlist = await asyncio.wait_for(
                    loop.run_in_executor(None, self.spotify.playlist, playlist_id),
                    timeout=10.0
                )

                if not playlist:
                    print(f"❌ [SPOTIFY PLAYLIST] Playlist returned None: {playlist_id}")
                    return None, []

            except Exception as api_error:
                print(f"❌ [SPOTIFY PLAYLIST] API Error: {api_error}")
                return None, []

            total_tracks = playlist['tracks']['total']

            if total_tracks == 0:
                print(f"❌ [SPOTIFY PLAYLIST] Playlist is empty: {playlist_id}")
                return None, []

            playlist_info = {
                'title': playlist['name'],
                'total_songs': total_tracks,
                'source': 'spotify',
                'owner': playlist.get('owner', {}).get('display_name', 'Unknown'),
                'public': playlist.get('public', False)
            }

            print(f"🚀 [SPOTIFY PLAYLIST] Found {total_tracks} tracks in '{playlist['name']}'")

            # ✅ EXTRACT ALL TRACKS QUICKLY
            tracks = []
            results = playlist['tracks']

            while results:
                for item in results['items']:
                    if not item or not item.get('track') or not item['track'].get('id'):
                        continue

                    track = item['track']

                    # ✅ Skip local files and unavailable tracks
                    if track.get('is_local'):
                        continue

                    # ✅ FIXED: Handle None values in artists properly
                    artists = []
                    try:
                        artists_raw = track.get('artists', [])
                        artists = [artist['name'] for artist in artists_raw if artist and artist.get('name')]
                        artist_str = ', '.join(artists) if artists else 'Unknown Artist'
                    except Exception as artist_error:
                        artist_str = 'Unknown Artist'
                        artists = ['Unknown Artist']

                    # ✅ Create minimal track data with better error handling
                    track_data = {
                        'id': track['id'],
                        'name': track.get('name', 'Unknown Track'),
                        'artist_str': artist_str,
                        'artists': artists,
                        'album': track.get('album', {}).get('name', 'Unknown Album') if track.get('album') else 'Unknown Album',
                        'duration': track.get('duration_ms', 0) // 1000 if track.get('duration_ms') else 0,
                        'source': 'spotify'
                    }

                    tracks.append(track_data)

                # Get next page if available
                if results['next']:
                    results = await loop.run_in_executor(None, self.spotify.next, results)
                else:
                    results = None

                # Progress update
                if len(tracks) % 50 == 0 and len(tracks) > 0:
                    print(f"🚀 [SPOTIFY PLAYLIST] Processed {len(tracks)}/{total_tracks} tracks...")

            playlist_info['valid_songs'] = len(tracks)

            if len(tracks) == 0:
                print(f"❌ [SPOTIFY PLAYLIST] No playable tracks found in playlist")
                return None, []

            print(f"🚀 [SPOTIFY PLAYLIST] Completed: {len(tracks)} playable tracks extracted")
            return playlist_info, tracks

        except Exception as e:
            print(f"❌ [SPOTIFY PLAYLIST] Unexpected error: {e}")
            traceback.print_exc()
            return None, []

    async def search_youtube_for_track(self, spotify_track: dict):
        """Convert a Spotify track to YouTube using the YouTube handler"""
        try:
            # Build search query
            query_parts = [spotify_track['name']]
            if spotify_track['artists']:
                query_parts.append(spotify_track['artists'][0])
            if spotify_track.get('popularity', 0) > 50:
                query_parts.append("official")
            query = ' '.join(query_parts)

            # ✅ Fast search with timeout
            if self.youtube is not None:
                song_data = await asyncio.wait_for(
                    self.youtube.search(query),
                    timeout=8.0  # Same as YouTube search timeout
                )
            else:
                song_data = None

            if song_data:
                # Enhance with Spotify metadata
                song_data.update({
                    'title': f"{spotify_track['name']} - {spotify_track['artist_str']}",
                    'uploader': spotify_track['artist_str'],
                    'description': f"From Spotify: {spotify_track['album']}",
                    'spotify_track': True,
                    'spotify_info': spotify_track,
                    'source': 'spotify->youtube'
                })
                if spotify_track.get('duration'):
                    song_data['duration'] = spotify_track['duration']
                return song_data
            else:
                return None
        except Exception as e:
            print(f"❌ Error converting Spotify song: {e}")
            return None

    async def search_playlist(self, playlist_url: str):
        """🚀 FAST: Add tracks to queue first, convert later during playback"""
        try:
            content_type, spotify_id = self.extract_spotify_id(playlist_url)

            if content_type not in ['playlist', 'album'] or not spotify_id:
                print(f"❌ [SPOTIFY PLAYLIST] Invalid content type: {content_type}")
                return None, []

            print(f"🚀 [SPOTIFY PLAYLIST] Starting fast processing: {playlist_url}")
            start_time = time.time()

            # ✅ STEP 1: Fast metadata extraction only
            try:
                playlist_info, spotify_tracks = await asyncio.wait_for(
                    self.get_playlist_info(spotify_id),
                    timeout=15.0  # Reduced timeout for faster response
                )
            except asyncio.TimeoutError:
                print(f"❌ [SPOTIFY PLAYLIST] Timeout processing playlist")
                return None, []
            except Exception as extraction_error:
                print(f"❌ [SPOTIFY PLAYLIST] Extraction error: {extraction_error}")
                return None, []

            if not spotify_tracks:
                print(f"❌ [SPOTIFY PLAYLIST] No valid tracks found")
                return None, []

            extraction_time = time.time() - start_time
            print(f"🚀 [SPOTIFY PLAYLIST] Metadata extracted in {extraction_time:.2f}s")

            # ✅ STEP 2: Create queue entries WITHOUT YouTube conversion
            songs = []
            
            for i, track in enumerate(spotify_tracks, 1):
                # ✅ Create song data that will be converted on-demand during playback
                song_data = {
                    'id': f"spotify_{track['id']}",
                    'title': f"{track['name']} - {track['artist_str']}",
                    'webpage_url': f"spotify:track:{track['id']}",  # Special marker for on-demand conversion
                    'duration': track.get('duration', 0),
                    'uploader': track['artist_str'],
                    'source': 'spotify',
                    'spotify_info': track,
                    'needs_conversion': True,  # Mark for on-demand conversion
                    'conversion_query': f"{track['name']} {track['artist_str']}"  # Pre-built search query
                }
                songs.append(song_data)

            # Update playlist info
            if playlist_info is not None:
                playlist_info.update({
                    'valid_songs': len(songs),
                    'processing_time': time.time() - start_time,
                    'on_demand_conversion': True  # Mark as needing conversion during playback
                })

            total_time = time.time() - start_time
            print(f"🚀 [SPOTIFY PLAYLIST] Fast processing complete: {len(songs)} songs queued in {total_time:.2f}s")
            print(f"🎵 Songs will be converted to YouTube during playback")

            return playlist_info, songs

        except Exception as e:
            print(f"❌ [SPOTIFY PLAYLIST] Error: {e}")
            traceback.print_exc()
            return None, []
    
    async def cleanup(self):
        """Enhanced cleanup with connection management"""
        if self.session and not self.session.closed:
            await self.session.close()
        if self._connector and not self._connector.closed:
            await self._connector.close()
    
    def validate_credentials(self) -> bool:
        """Validate Spotify credentials"""
        return bool(Config.SPOTIFY_CLIENT_ID and Config.SPOTIFY_CLIENT_SECRET)

    async def test_playlist_access(self, playlist_id: str):
        """Test if we can access a specific playlist"""
        try:
            if not self.spotify:
                return {"success": False, "error": "Spotify client not initialized"}

            loop = asyncio.get_event_loop()
            playlist = await loop.run_in_executor(None, self.spotify.playlist, playlist_id)

            if not playlist:
                return {"success": False, "error": "Playlist not found"}

            return {
                "success": True,
                "title": playlist.get('name', 'Unknown'),
                "tracks": playlist.get('tracks', {}).get('total', 0),
                "public": playlist.get('public', False),
                "owner": playlist.get('owner', {}).get('display_name', 'Unknown')
            }
        except Exception as e:
            error_msg = str(e)
            if "404" in error_msg:
                return {"success": False, "error": "Playlist not found or private"}
            elif "401" in error_msg:
                return {"success": False, "error": "Authentication failed"}
            elif "403" in error_msg:
                return {"success": False, "error": "Access forbidden"}
            else:
                return {"success": False, "error": f"API error: {error_msg[:100]}"}

# Create the global instance
spotify_handler = SpotifyHandler()
