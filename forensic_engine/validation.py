"""Step 1: check that an uploaded file is really a usable image."""
from pathlib import Path
from PIL import Image

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 20 * 1024 * 1024  # 20 MB


def validate_image(path):
    """Return (ok, reason, info). Never raises for bad files."""
    p = Path(path)
    if not p.is_file():
        return False, "File not found", {}
    if p.suffix.lower() not in ALLOWED_EXT:
        return False, f"Unsupported file type '{p.suffix}'. Allowed: {sorted(ALLOWED_EXT)}", {}
    size = p.stat().st_size
    if size == 0:
        return False, "File is empty", {}
    if size > MAX_BYTES:
        return False, "File is larger than 20 MB", {}
    try:
        # verify() checks the file really is an image, not just renamed
        with Image.open(p) as im:
            im.verify()
        with Image.open(p) as im:  # reopen: verify() leaves the image unusable
            info = {"format": im.format, "width": im.width, "height": im.height, "mode": im.mode}
    except Exception as exc:
        return False, f"File is not a valid image ({exc.__class__.__name__})", {}
    return True, "OK", info
