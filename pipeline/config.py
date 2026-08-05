from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
HIGGSFIELD_DATA_DIR = ROOT_DIR / "data_higgsfield"
PODCAST_DATA_DIR = ROOT_DIR / "data_podcast"
ASSETS_DIR = ROOT_DIR / "assets"
VOICES_DIR = ASSETS_DIR / "voices"
FONTS_DIR = ASSETS_DIR / "fonts"
ICONS_DIR = ASSETS_DIR / "icons"
MUSIC_DIR = ASSETS_DIR / "music"
OUTPUT_DIR = ROOT_DIR / "output"

DEFAULT_VOICE = "fr_FR-siwis-medium"
FRAME_SIZE = (1280, 720)
SHORT_FRAME_SIZE = (1080, 1920)
FPS = 24
