import os
import time
from pathlib import Path
from config.settings import Config
import logging

class FileManager:
    """Placeholder FileManager — downloads disabled in this build."""

    def __init__(self):
        self.downloads_dir = None
        self.max_age_hours = 24
        self.max_files = 100
