"""
Spotify Configuration

To get your Spotify API credentials:
    pass
1. Go to https://developer.spotify.com/dashboard/
2. Create a new app
3. Copy your Client ID and Client Secret
4. Replace the values below
"""

SPOTIFY_CLIENT_ID = "your_spotify_client_id_here"
SPOTIFY_CLIENT_SECRET = "your_spotify_client_secret_here"

import os

SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID', SPOTIFY_CLIENT_ID)
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET', SPOTIFY_CLIENT_SECRET)
