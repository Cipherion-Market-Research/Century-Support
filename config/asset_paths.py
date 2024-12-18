from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent.parent
STATIC_DIR = BASE_DIR / "static"
IMAGES_DIR = STATIC_DIR / "images"

# Specific asset paths as strings
WELCOME_GIF = str(IMAGES_DIR / "media" / "ciphexStart.gif")
LOGO_PATH = str(IMAGES_DIR / "logo" / "ciphex_logo.png")

# Ensure directories exist
for path in [STATIC_DIR, IMAGES_DIR, IMAGES_DIR / "logo", IMAGES_DIR / "media"]:
    path.mkdir(parents=True, exist_ok=True)
