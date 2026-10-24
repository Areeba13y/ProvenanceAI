"""Creates synthetic sample images (no real evidence needed)."""
from pathlib import Path
from PIL import Image, ImageDraw

Path("sample_data").mkdir(exist_ok=True)


def chat(msgs, name, exif=None):
    im = Image.new("RGB", (480, 420), (236, 229, 221))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 480, 50), fill=(7, 94, 84))
    d.text((16, 18), "Ali (demo chat)", fill="white")
    y = 70
    for who, text, t in msgs:
        x = 20 if who == "them" else 200
        d.rounded_rectangle((x, y, x + 260, y + 50), 8, fill="white" if who == "them" else (220, 248, 198))
        d.text((x + 10, y + 8), text, fill="black")
        d.text((x + 200, y + 34), t, fill="gray")
        y += 66
    if exif:
        im.save(name, exif=exif)
    else:
        im.save(name)


orig = [("them", "Meeting at 5?", "4:10 PM"), ("me", "Yes, see you", "4:12 PM"), ("them", "Bring the files", "4:15 PM")]
edit = [("them", "Meeting at 5?", "4:10 PM"), ("me", "Yes, see you", "4:12 PM"), ("them", "Bring the money", "4:15 PM")]
chat(orig, "sample_data/original.png")

ex = Image.Exif()
ex[0x0131] = "Adobe Photoshop 25.0"
ex[0x0132] = "2026:10:20 10:00:00"
ex.get_ifd(0x8769)[0x9003] = "2026:10:18 09:00:00"
chat(edit, "sample_data/edited.png", exif=ex)
print("samples ready")


# ---- photo-like JPEG pair for the OpenCV checks ----------------------------
import numpy as np
import cv2

rng = np.random.default_rng(1)
H, W = 384, 512
yy, xx = np.mgrid[0:H, 0:W]
base = np.stack([100 + 60 * np.sin(xx / 70), 120 + 50 * np.cos(yy / 60),
                 90 + 40 * np.sin((xx + yy) / 90)], axis=2)
photo = np.clip(base + rng.normal(0, 5, base.shape), 0, 255).astype(np.uint8)
cv2.imwrite("sample_data/photo_original.jpg", photo, [cv2.IMWRITE_JPEG_QUALITY, 92])
donor = np.clip(base[::-1] + rng.normal(0, 1.5, base.shape), 0, 255).astype(np.uint8)
cv2.imwrite("sample_data/_donor.jpg", donor, [cv2.IMWRITE_JPEG_QUALITY, 45])
img = cv2.imread("sample_data/photo_original.jpg")
img[150:230, 220:340] = cv2.imread("sample_data/_donor.jpg")[150:230, 220:340]
cv2.imwrite("sample_data/photo_tampered.jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
Path("sample_data/_donor.jpg").unlink()
print("photo samples ready")
