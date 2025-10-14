import asyncio
import time
import hashlib
import aiohttp
import re
import json
import yt_dlp
import discord
import traceback
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from config.settings import Config

class YouTubeHandlerSingleton:
    """Singleton YouTube handler with connection pooling and search/download pools."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._download_pool = {}
            self._search_pool = {}
            # Use the configured downloads directory consistently
            self.downloads_dir = Config.DOWNLOADS_DIR
            try:
                self.downloads_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                # Fallback: ensure a local downloads directory exists
                fallback = Path(__file__).parent.parent.parent / "downloads"
                fallback.mkdir(parents=True, exist_ok=True)
                self.downloads_dir = fallback
            self._initialized = True

    def _cleanup_old_instances(self):
        self._search_pool.clear()
        self._download_pool.clear()

    def _get_search_instance(self, use_cookies: bool = True):
        """Get search instance optimized for Oracle Cloud"""
        cache_key = f"search_{use_cookies}_{int(time.time() // 300)}"
        if cache_key not in self._search_pool:
            opts = {
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'skip_download': True,
                'extract_flat': False,
                'playlist_items': f'1:{getattr(Config, "MAX_PLAYLIST_SIZE", 100)}',
                'socket_timeout': 15,
                'retries': 1,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['web', 'ios'],
                        'player_skip': ['configs'],
                    }
                },
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Origin': 'https://www.youtube.com',
                    'Referer': 'https://www.youtube.com/',
                },
                'sleep_interval': 2,
                'max_sleep_interval': 5,
                'geo_bypass': True,
                'geo_bypass_country': None,
                'age_limit': 99,
            }
            if use_cookies:
                cookies_file = getattr(Config, "get_cookies_path", lambda: None)()
                if cookies_file and Path(cookies_file).exists():
                    opts['cookiefile'] = str(cookies_file)
                    logging.info(f"🍪 Using cookies: {cookies_file}")
            self._search_pool[cache_key] = yt_dlp.YoutubeDL(opts)  # type: ignore[arg-type]
        return self._search_pool[cache_key]

    def _get_download_instance(self, use_cookies: bool = True):
        """Get cached download instance with robust format fallbacks"""
        cache_key = f"download_{use_cookies}_{int(time.time() // 600)}"
        if cache_key not in self._download_pool:
            opts = {
                'format': (
                    'bestaudio[ext=m4a][filesize<25M]/'
                    'bestaudio[ext=webm][filesize<25M]/'
                    'bestaudio[filesize<25M]/'
                    'best[filesize<25M]/'
                    'bestaudio/best'
                ),
                'outtmpl': str(self.downloads_dir / '%(title)s_%(id)s.%(ext)s'),
                'concurrent_fragment_downloads': 1,
                'http_chunk_size': 1048576,
                'retries': 3,
                'fragment_retries': 3,
                'socket_timeout': 30,
                'keepvideo': False,
                'restrictfilenames': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'logtostderr': False,
                'quiet': True,
                'no_playlist': True,
                'extractaudio': True,
                'audioformat': 'mp3',
                'audioquality': '96K',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '96',
                }],
                'prefer_ffmpeg': True,
                'buffersize': 1024,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                },
                'geo_bypass': True,
                'geo_bypass_country': None,
                'age_limit': 99,
            }
            if use_cookies:
                cookies_file = getattr(Config, "get_cookies_path", lambda: None)()
                if cookies_file and Path(cookies_file).exists():
                    opts['cookiefile'] = str(cookies_file)
            self._download_pool[cache_key] = yt_dlp.YoutubeDL(opts)  # type: ignore[arg-type]
        return self._download_pool[cache_key]

    def is_url_supported(self, url: str) -> bool:
        return bool(re.search(r'(youtube\.com|youtu\.be)', url, re.IGNORECASE))

    def is_playlist_url(self, url: str) -> bool:
        if not self.is_url_supported(url):
            return False
        playlist_patterns = [
            r'[&?]list=', r'playlist\?list=', r'/playlist/',
            r'music\.youtube\.com/playlist'
        ]
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in playlist_patterns)

    def clean_url(self, url: str) -> str:
        if not self.is_url_supported(url):
            return url
        try:
            shorts_match = re.search(r'youtube\.com/shorts/([a-zA-Z0-9_-]+)', url)
            if shorts_match:
                video_id = shorts_match.group(1)
                return f"https://www.youtube.com/watch?v={video_id}"
            if 'v=' in url:
                video_id = url.split('v=')[1].split('&')[0]
                return f"https://www.youtube.com/watch?v={video_id}"
            elif 'youtu.be/' in url:
                video_id = url.split('youtu.be/')[1].split('?')[0]
                return f"https://www.youtube.com/watch?v={video_id}"
            else:
                return url
        except Exception:
            return url

    def clean_filename(self, filename: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*]', '', filename)
        cleaned = re.sub(r'[^\w\s\-\.]', '', cleaned)
        cleaned = re.sub(r'\s+', '_', cleaned.strip())
        return cleaned[:100] if len(cleaned) > 100 else cleaned

    async def search(self, query: str) -> Optional[Dict[str, Any]]:
        try:
            loop = asyncio.get_event_loop()
            if query.startswith(('http://', 'https://')):
                search_query = self.clean_url(query)
            else:
                search_query = f"ytsearch:{query}"
            logging.info(f"🔍 YouTube search: {query}")
            try:
                result = await self._web_based_search(query)
                if result:
                    logging.info("✅ Web-based search successful")
                    return result
            except Exception as e:
                logging.warning(f"⚠️ Web-based search failed: {e}")
            extraction_strategies = [
                ('web_client', {'extractor_args': {'youtube': {'player_client': ['web']}}}),
                ('ios_client', {'extractor_args': {'youtube': {'player_client': ['ios']}}}),
                ('android_client', {'extractor_args': {'youtube': {'player_client': ['android']}}}),
                ('minimal', {'format': 'worst', 'quiet': True})
            ]
            for strategy_name, extra_opts in extraction_strategies:
                try:
                    logging.info(f"🔍 Trying extraction strategy: {strategy_name}")
                    ytdl = self._get_search_instance(use_cookies=True)
                    ytdl.params.update(extra_opts)
                    data = await asyncio.wait_for(
                        loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False)),
                        timeout=8.0
                    )
                    if data and 'entries' in data and data['entries']:
                        for entry in data['entries']:
                            if entry and entry.get('id'):
                                result = self._format_song_data(entry)
                                logging.info(f"✅ Found with strategy: {strategy_name}")
                                return result
                except asyncio.TimeoutError:
                    logging.warning(f"⏰ Timeout with strategy: {strategy_name}")
                    continue
                except Exception as e:
                    if 'bot' in str(e).lower():
                        logging.warning(f"🤖 Bot detection with strategy: {strategy_name}")
                        continue
                    else:
                        logging.warning(f"⚠️ Error with strategy: {strategy_name}: {e}")
                        continue
            return await self._create_searchable_fallback(query)
        except Exception as e:
            logging.error(f"❌ Search error: {e}")
            return None

    async def _web_based_search(self, query: str) -> Optional[Dict[str, Any]]:
        """Web scraping fallback for bot detection"""
        try:
            # Create session with browser-like headers
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                }
            ) as session:
                
                # Search YouTube via web interface
                search_url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
                
                async with session.get(search_url) as response:
                    if response.status == 200:
                        html = await response.text()
                        
                        # Extract video data from page
                        match = re.search(r'var ytInitialData = ({.*?});', html)
                        if match:
                            try:
                                data = json.loads(match.group(1))
                                
                                # Navigate through YouTube's data structure
                                contents = data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])
                                
                                for section in contents:
                                    items = section.get('itemSectionRenderer', {}).get('contents', [])
                                    for item in items:
                                        if 'videoRenderer' in item:
                                            video = item['videoRenderer']
                                            video_id = video.get('videoId', None)
                                            title = video.get('title', {}).get('runs', [{}])[0].get('text', 'Unknown')
                                            uploader = "Unknown Artist"
                                            try:
                                                channel_info = video.get('ownerText', {}).get('runs', [{}])
                                                if channel_info and len(channel_info) > 0:
                                                    uploader = channel_info[0].get('text', 'Unknown Artist')
                                                if uploader == "Unknown Artist":
                                                    long_byline = video.get('longBylineText', {}).get('runs', [{}])
                                                    if long_byline and len(long_byline) > 0:
                                                        uploader = long_byline[0].get('text', 'Unknown Artist')
                                                if uploader == "Unknown Artist":
                                                    uploader = self._extract_artist_from_query(title)
                                            except Exception as e:
                                                logging.warning(f"⚠️ Error extracting uploader: {e}")
                                                uploader = self._extract_artist_from_query(query)
                                            if video_id and title and uploader:
                                                return {
                                                    'id': video_id,
                                                    'title': title,
                                                    'webpage_url': f"https://www.youtube.com/watch?v={video_id}",
                                                    'duration': 180,  # Default duration
                                                    'uploader': uploader,
                                                    'source': 'web_scraping',
                                                    'availability': 'public'
                                                }
                            except json.JSONDecodeError:
                                pass
        
        except Exception as e:
            logging.error(f"❌ Web-based search error: {e}")
            return None

    async def _create_searchable_fallback(self, query: str) -> Optional[Dict[str, Any]]:
        """Create a searchable fallback result"""
        try:
            # Create a deterministic but unique ID
            query_hash = hashlib.md5(f"{query}{int(time.time() // 3600)}".encode()).hexdigest()[:11]
            
            # Try to extract artist from query
            artist_name = self._extract_artist_from_query(query)
            
            return {
                'id': query_hash,
                'title': f"Search: {query}",
                'webpage_url': f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}",
                'duration': 180,
                'uploader': artist_name,
                'source': 'fallback',
                'availability': 'public',
                'is_fallback': True
            }
            
        except Exception as e:
            logging.error(f"❌ Fallback creation failed: {e}")
            return None

    def _extract_artist_from_query(self, query: str) -> str:
        """Extract potential artist name from search query"""
        try:
            # Common patterns: "artist - song", "song by artist", etc.
            if ' - ' in query:
                parts = query.split(' - ')
                if len(parts) >= 2:
                    return parts[0].strip()
            
            if ' by ' in query.lower():
                parts = query.lower().split(' by ')
                if len(parts) >= 2:
                    return parts[1].strip().title()
            
            # If no pattern found, use the first word(s)
            words = query.split()
            if len(words) >= 2:
                return ' '.join(words[:2])  # First two words
            elif len(words) == 1:
                return words[0]
            
            return "Unknown Artist"
            
        except Exception:
            return "Unknown Artist"
    
    def _format_song_data(self, video_info: Dict) -> Dict[str, Any]:
        """Format video info with enhanced debugging and validation"""
        try:
            logging.info(f"🔍 [FORMAT DEBUG] Processing video: {video_info.get('id', 'no-id')}")
            
            availability = video_info.get('availability', 'public')
            title = video_info.get('title', 'Unknown Title')
            video_id = video_info.get('id', 'unknown')
            
            logging.info(f"🔍 [FORMAT DEBUG] - Title: {title}")
            logging.info(f"🔍 [FORMAT DEBUG] - ID: {video_id}")
            logging.info(f"🔍 [FORMAT DEBUG] - Availability: {availability}")
            
            # ✅ Additional validation
            if not video_id or video_id == 'unknown':
                raise ValueError(f"Invalid video ID: {video_id}")
            
            if 'Private video' in title or 'Deleted video' in title:
                raise ValueError(f"Video unavailable: {title}")
            
            formatted_data = {
                'id': video_id,
                'title': title,
                'webpage_url': video_info.get('webpage_url') or f"https://www.youtube.com/watch?v={video_id}",
                'duration': video_info.get('duration'),
                'uploader': video_info.get('uploader', 'Unknown'),
                'view_count': video_info.get('view_count'),
                'description': (video_info.get('description', '') or '')[:100],
                'availability': availability,
                'source': 'youtube'
            }
            
            logging.info(f"✅ [FORMAT DEBUG] Successfully formatted: {formatted_data['title']}")
            return formatted_data
            
        except Exception as e:
            logging.error(f"❌ [FORMAT DEBUG] Error formatting video {video_info.get('id', 'unknown')}: {e}")
            raise
    
    async def search_playlist(self, playlist_url: str) -> Tuple[Optional[Dict], List[Dict]]:
        """⚡ ULTRA-FAST playlist processing - NO SIZE LIMITS"""
        try:
            loop = asyncio.get_event_loop()
            
            logging.info(f"🚀 [PLAYLIST] Starting processing: {playlist_url}")
            
            # ⚡ Use minimal extraction options for speed
            fast_opts = {
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'skip_download': True,
                'extract_flat': True,
                'socket_timeout': 15,
                'extractor_retries': 2,
                'fragment_retries': 2,
                'geo_bypass': True,
                'geo_bypass_country': None,
                'age_limit': 99,
            }
            
            # Add cookies if available
            cookies_file = getattr(Config, "get_cookies_path", lambda: None)()
            if cookies_file:
                fast_opts['cookiefile'] = cookies_file
                logging.info(f"🍪 Using cookies for playlist: {cookies_file}")
            else:
                logging.warning("⚠️ No cookies for playlist extraction")
            
            ytdl = yt_dlp.YoutubeDL(fast_opts)  # type: ignore[arg-type]
            
            logging.info(f"🚀 [PLAYLIST] Using extraction options (no size limit)")
            
            start_time = time.time()

            # Extract playlist data with timeout
            try:
                data = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: ytdl.extract_info(playlist_url, download=False)),
                    timeout=30.0  # 30 second timeout
                )
            except asyncio.TimeoutError:
                logging.warning(f"⏰ [PLAYLIST] Timeout after 30s, trying fallback")
                return await self._fallback_playlist_extraction(playlist_url)
            
            if not data:
                logging.error(f"❌ [PLAYLIST] No data returned")
                return None, []
            
            # Extract playlist info
            playlist_info = {
                'title': data.get('title', 'Unknown Playlist'),
                'uploader': data.get('uploader', 'Unknown'),
                'total_songs': len(data.get('entries', [])),
                'source': 'youtube'
            }
            
            songs = []
            entries = data.get('entries', [])
            
            for entry in entries:
                if entry and entry.get('id'):
                    song_data = {
                        'id': entry['id'],
                        'title': entry.get('title', 'Unknown Title'),
                        'webpage_url': entry.get('webpage_url') or f"https://www.youtube.com/watch?v={entry['id']}",
                        'duration': entry.get('duration'),
                        'uploader': entry.get('uploader', 'Unknown'),
                        'source': 'youtube'
                    }
                    songs.append(song_data)
            
            playlist_info['valid_songs'] = len(songs)
            extraction_time = time.time() - start_time
            
            logging.info(f"🚀 [PLAYLIST] Completed in {extraction_time:.2f}s: {len(songs)} songs")
            
            return playlist_info, songs
            
        except Exception as e:
            logging.error(f"❌ [PLAYLIST] Error: {e}")
            traceback.print_exc()
            return None, []

    async def _fallback_playlist_extraction(self, playlist_url: str) -> Tuple[Optional[Dict], List[Dict]]:
        """Fallback method - extract just the first few songs"""
        try:
            logging.info(f"🔄 [PLAYLIST FALLBACK] Attempting limited extraction")
            
            # Create basic playlist info
            playlist_info = {
                'title': 'YouTube Playlist (Limited)',
                'uploader': 'Unknown',
                'total_songs': 0,
                'valid_songs': 0,
                'source': 'youtube_fallback'
            }
            
            return playlist_info, []
            
        except Exception as e:
            logging.error(f"❌ [PLAYLIST FALLBACK] Error: {e}")
            return None, []
    
    def cleanup(self):
        self._search_pool.clear()
        self._download_pool.clear()

try:
    import discord as _discord_mod
    _PCMVolumeTransformer = getattr(_discord_mod, "PCMVolumeTransformer", None)
    _FFmpegPCMAudio = getattr(_discord_mod, "FFmpegPCMAudio", None)
except Exception:
    _PCMVolumeTransformer = None
    _FFmpegPCMAudio = None

# Determine a safe base class for YTDLSource at import time
if _PCMVolumeTransformer is None:
    class _BaseVolume(object):
        pass
else:
    _BaseVolume = _PCMVolumeTransformer  # type: ignore[assignment]

class YTDLSource(_BaseVolume):
    """Optimized Discord audio source with caching"""
    def __init__(self, source, *, data, volume=0.5):
        # Only call into Discord's PCMVolumeTransformer if available; otherwise, act as a thin wrapper
        if _PCMVolumeTransformer is not None:
            try:
                super().__init__(source, volume)  # type: ignore[misc]
            except Exception:
                # Fallback: ignore volume transform if unexpected signature
                pass
        # Always store a reference to the underlying source
        self.source = source
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url')
        self.duration = data.get('duration')
        self.uploader = data.get('uploader')

    @classmethod
    async def from_url(cls, url: str, *, loop=None, volume_percent=100, start_time=0):
        try:
            loop = loop or asyncio.get_event_loop()
            handler = youtube_handler
            ytdl = handler._get_download_instance(use_cookies=True)
            data = await loop.run_in_executor(
                None,
                lambda: ytdl.extract_info(url, download=False)
            )
            if not data:
                raise Exception(f"Could not extract info from: {url}")
            if 'entries' in data and data['entries']:
                data = data['entries'][0]
            audio_url = None
            if 'url' in data:
                audio_url = data['url']
            elif 'formats' in data and data['formats']:
                audio_formats = [f for f in data['formats'] if f and f.get('acodec') != 'none']
                if audio_formats:
                    audio_url = audio_formats[0].get('url')
            if not audio_url or not _FFmpegPCMAudio:
                raise Exception("No audio URL found or FFmpegPCMAudio unavailable")
            before_options = f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {start_time}' if start_time > 0 else '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
            options = '-vn -bufsize 1024k'
            source = _FFmpegPCMAudio(audio_url, before_options=before_options, options=options)  # type: ignore[misc]
            volume = volume_percent / 100.0
            return cls(source, data=data, volume=volume)
        except Exception as e:
            logging.error(f"❌ Error creating YTDLSource: {e}")
            raise

youtube_handler = YouTubeHandlerSingleton()
YouTubeHandler = YouTubeHandlerSingleton
