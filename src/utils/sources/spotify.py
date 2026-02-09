import spotipy
import aiohttp
import asyncio
import re
import time
import traceback
import logging
from spotipy.oauth2 import SpotifyClientCredentials
from typing import Optional, Tuple, List, Dict, Any
from .base import AudioSource
try:
    from .youtube import youtube_handler
except ImportError:
    youtube_handler = None

from config.settings import Config

class SpotifyHandler(AudioSource):
    """Spotify handler."""

    def __init__(self):
        super().__init__()
        self.youtube = youtube_handler
        self.spotify = None
        self.session: Optional[aiohttp.ClientSession] = None

        self._connector = None

        self._initialize_spotify()

    def _initialize_spotify(self):
        """Initialize Spotify client."""
        if not Config.SPOTIFY_CLIENT_ID or not Config.SPOTIFY_CLIENT_SECRET:
            logging.warning("Spotify credentials not configured")
            return

        try:
            credentials = SpotifyClientCredentials(
                client_id=Config.SPOTIFY_CLIENT_ID,
                client_secret=Config.SPOTIFY_CLIENT_SECRET
            )
            self.spotify = spotipy.Spotify(client_credentials_manager=credentials)
            logging.info("Spotify client initialized")
        except Exception as e:
            logging.error("Spotify initialization failed: %s", e)
            self.spotify = None

    def is_url_supported(self, url: str) -> bool:
        """Check if URL is supported."""
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
            logging.error("Error extracting Spotify ID: %s", e)

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

            artists = []
            try:
                artists_raw = track.get('artists', [])
                for artist in artists_raw:
                    if artist and isinstance(artist, dict) and artist.get('name'):
                        artists.append(artist['name'])

                if not artists:
                    artists = ['Unknown Artist']

                artist_str = ', '.join(artists)

            except Exception as artist_error:
                logging.warning("Artist processing error: %s", artist_error)
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
            logging.error("Error getting Spotify track: %s", e)
            return None

    async def search(self, query: str):
        """Search for a single Spotify track - REQUIRED ABSTRACT METHOD"""
        try:
            if not self.spotify:
                logging.error("Spotify client not available")
                return None

            content_type, spotify_id = self.extract_spotify_id(query)

            if content_type != 'track' or not spotify_id:
                logging.error("Expected track, got %s", content_type)
                return None

            track_info = await asyncio.wait_for(
                self.get_track_info(spotify_id),
                timeout=5.0
            )

            if not track_info:
                logging.error("Failed to get Spotify track info")
                return None

            if self.youtube is not None:
                return await self.search_youtube_for_track(track_info)
            else:
                logging.error("YouTube handler not available")
                return None

        except asyncio.TimeoutError:
            logging.warning("Spotify search timeout")
            return None
        except Exception as e:
            logging.error("Spotify search error: %s", e)
            return None

    async def get_playlist_info(self, playlist_id: str):
        """Get playlist metadata and tracks from Spotify"""
        try:
            if not self.spotify or not playlist_id:
                return None, []

            loop = asyncio.get_event_loop()

            logging.info("[SPOTIFY PLAYLIST] Starting fast extraction: %s", playlist_id)

            try:
                playlist = await asyncio.wait_for(
                    loop.run_in_executor(None, self.spotify.playlist, playlist_id),
                    timeout=10.0
                )

                if not playlist:
                    logging.error("[SPOTIFY PLAYLIST] Playlist returned None: %s", playlist_id)
                    return None, []

            except Exception as api_error:
                logging.error("[SPOTIFY PLAYLIST] API Error: %s", api_error)
                return None, []

            total_tracks = playlist['tracks']['total']

            if total_tracks == 0:
                logging.error("[SPOTIFY PLAYLIST] Playlist is empty: %s", playlist_id)
                return None, []

            playlist_info = {
                'title': playlist['name'],
                'total_songs': total_tracks,
                'source': 'spotify',
                'owner': playlist.get('owner', {}).get('display_name', 'Unknown'),
                'public': playlist.get('public', False)
            }

            logging.info("[SPOTIFY PLAYLIST] Found %d tracks in '%s'", total_tracks, playlist['name'])

            tracks = []
            results = playlist['tracks']

            while results:
                for item in results['items']:
                    if not item or not item.get('track') or not item['track'].get('id'):
                        continue

                    track = item['track']

                    if track.get('is_local'):
                        continue

                    artists = []
                    try:
                        artists_raw = track.get('artists', [])
                        artists = [artist['name'] for artist in artists_raw if artist and artist.get('name')]
                        artist_str = ', '.join(artists) if artists else 'Unknown Artist'
                    except Exception as artist_error:
                        artist_str = 'Unknown Artist'
                        artists = ['Unknown Artist']

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

                if results['next']:
                    results = await loop.run_in_executor(None, self.spotify.next, results)
                else:
                    results = None

                if len(tracks) % 50 == 0 and len(tracks) > 0:
                    logging.info("[SPOTIFY PLAYLIST] Processed %d/%d tracks...", len(tracks), total_tracks)

            playlist_info['valid_songs'] = len(tracks)

            if len(tracks) == 0:
                logging.error("[SPOTIFY PLAYLIST] No playable tracks found in playlist")
                return None, []

            logging.info("[SPOTIFY PLAYLIST] Completed: %d playable tracks extracted", len(tracks))
            return playlist_info, tracks

        except Exception as e:
            logging.exception("[SPOTIFY PLAYLIST] Unexpected error: %s", e)
            return None, []

    async def search_youtube_for_track(self, spotify_track: dict):
        """Convert a Spotify track to YouTube using the YouTube handler"""
        try:
            query_parts = [spotify_track['name']]
            if spotify_track['artists']:
                query_parts.append(spotify_track['artists'][0])
            if spotify_track.get('popularity', 0) > 50:
                query_parts.append("official")
            query = ' '.join(query_parts)

            if self.youtube is not None:
                song_data = await asyncio.wait_for(
                    self.youtube.search(query),
                    timeout=90.0  # Increased timeout to allow for retries and slow proxies
                )
            else:
                song_data = None

            if song_data:
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
            logging.error(f"Error converting Spotify song '{spotify_track.get('name', 'Unknown')}': {repr(e)}")
            return None

    async def search_playlist(self, playlist_url: str):
        """🚀 FAST: Add tracks to queue first, convert later during playback"""
        try:
            content_type, spotify_id = self.extract_spotify_id(playlist_url)

            if content_type not in ['playlist', 'album'] or not spotify_id:
                logging.error("[SPOTIFY PLAYLIST] Invalid content type: %s", content_type)
                return None, []

            logging.info("[SPOTIFY PLAYLIST] Starting fast processing: %s", playlist_url)
            start_time = time.time()

            try:
                playlist_info, spotify_tracks = await asyncio.wait_for(
                    self.get_playlist_info(spotify_id),
                    timeout=15.0  # Reduced timeout for faster response
                )
            except asyncio.TimeoutError:
                logging.error("[SPOTIFY PLAYLIST] Timeout processing playlist")
                return None, []
            except Exception as extraction_error:
                logging.error("[SPOTIFY PLAYLIST] Extraction error: %s", extraction_error)
                return None, []

            if not spotify_tracks:
                logging.error("[SPOTIFY PLAYLIST] No valid tracks found")
                return None, []

            extraction_time = time.time() - start_time
            logging.info("[SPOTIFY PLAYLIST] Metadata extracted in %.2fs", extraction_time)

            songs = []

            for i, track in enumerate(spotify_tracks, 1):
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

            if playlist_info is not None:
                playlist_info.update({
                    'valid_songs': len(songs),
                    'processing_time': time.time() - start_time,
                    'on_demand_conversion': True  # Mark as needing conversion during playback
                })

            total_time = time.time() - start_time
            logging.info("[SPOTIFY PLAYLIST] Fast processing complete: %d songs queued in %.2fs", len(songs), total_time)
            logging.info("Songs will be converted to YouTube during playback")

            return playlist_info, songs

        except Exception as e:
            logging.exception("[SPOTIFY PLAYLIST] Error: %s", e)
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

spotify_handler = SpotifyHandler()
