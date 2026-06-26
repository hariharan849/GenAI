"""Core card generation logic: Excel loading, image compositing, OCR detection, output."""

import os
import re
import json
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont, ImageChops


WINDOWS_FONTS = Path("C:/Windows/Fonts")

# Common Tesseract install locations on Windows (tried in order)
_TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def _configure_tesseract() -> None:
    """Point pytesseract at the Tesseract binary when it is not on PATH."""
    try:
        import pytesseract, shutil
        # If tesseract is already on PATH, nothing to do
        if shutil.which("tesseract"):
            return
        for candidate in _TESSERACT_CANDIDATES:
            if Path(candidate).exists():
                pytesseract.pytesseract.tesseract_cmd = candidate
                return
    except ImportError:
        pass

# Keyword synonyms for each card role — used as last-resort column matching
# when excel_column is a role key but column_map doesn't bridge to the real header.
_ROLE_KEYWORDS: dict[str, list[str]] = {
    "name":    ["name", "student name", "student_name", "studentname"],
    "class":   ["class", "class & sec", "section", "class_sec", "classandsec"],
    "admn":    ["admn", "admission", "admn no", "admission no", "admn_no", "admissionno"],
    "photo":   ["photo", "photo path", "image", "photo_path"],
    "dob":     ["dob", "date of birth", "d.o.b", "birth", "dateofbirth"],
    "blood":   ["blood", "blood group", "bg", "bloodgroup"],
    "father":  ["father", "father name", "parent", "fathername"],
    "address": ["address", "addr"],
    "contact": ["contact", "phone", "mobile", "mob"],
}

# Marker colours used by the field config visual editor (one per field slot)
FIELD_COLORS = [
    "#F44336", "#E91E63", "#9C27B0", "#3F51B5", "#1976D2",
    "#0097A7", "#388E3C", "#F57F17", "#E65100", "#795548",
]


# ─────────────────────────────────────────────────── font loader ─────────────

def _get_font(name: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name_lower = name.lower().strip()
    variants = (
        [f"{name_lower}bd.ttf", f"{name_lower}b.ttf", f"{name_lower}-Bold.ttf",
         f"{name_lower}bold.ttf", f"{name_lower}.ttf"]
        if bold
        else [f"{name_lower}.ttf", f"{name_lower}-Regular.ttf"]
    )
    for v in variants:
        p = WINDOWS_FONTS / v
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ──────────────────────────────────────────────── photo compositing ──────────

def apply_photo_transform(
    photo: Image.Image,
    region: dict,
    transform: dict,
    bg_color: "tuple[int,int,int] | None" = None,
) -> Image.Image:
    """
    Fit photo into region with pan/zoom/rotation, masked to region shape.

    transform: {x, y, scale, rotation}  (x/y are pixel offsets from region centre)
    bg_color:  optional (R,G,B) fill painted behind the photo before masking;
               useful when scale < 1.0 so the photo doesn't fully cover the region.
    Returns RGBA image sized (region.width × region.height).
    """
    rw, rh = region["width"], region["height"]
    offset_x = float(transform.get("x", 0))
    offset_y = float(transform.get("y", 0))
    user_scale = float(transform.get("scale", 1.0))
    rotation = float(transform.get("rotation", 0))
    # bg_color may also be stored inside the transform dict by the editor
    if bg_color is None and transform.get("bg_color"):
        raw = transform["bg_color"]
        bg_color = tuple(raw[:3])

    photo_rgba = photo.convert("RGBA")

    if transform.get("flip_h"):
        photo_rgba = photo_rgba.transpose(Image.FLIP_LEFT_RIGHT)
    if transform.get("flip_v"):
        photo_rgba = photo_rgba.transpose(Image.FLIP_TOP_BOTTOM)

    brightness = float(transform.get("brightness", 1.0))
    contrast   = float(transform.get("contrast", 1.0))
    if brightness != 1.0 or contrast != 1.0:
        from PIL import ImageEnhance
        if brightness != 1.0:
            photo_rgba = ImageEnhance.Brightness(photo_rgba).enhance(brightness)
        if contrast != 1.0:
            photo_rgba = ImageEnhance.Contrast(photo_rgba).enhance(contrast)

    if rotation != 0:
        photo_rgba = photo_rgba.rotate(-rotation, expand=True, resample=Image.BICUBIC)

    # Cover-fit: photo fills the region at scale=1.0
    cover = max(rw / photo_rgba.width, rh / photo_rgba.height)
    total = cover * user_scale
    nw = max(1, int(photo_rgba.width * total))
    nh = max(1, int(photo_rgba.height * total))
    photo_rgba = photo_rgba.resize((nw, nh), Image.LANCZOS)

    canvas = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))

    shape = region.get("shape", "rect")

    # Fill background before pasting photo (visible when photo < region size)
    if bg_color is not None:
        bg_fill = Image.new("RGBA", (rw, rh), (*bg_color, 255))
        if shape == "circle":
            fill_mask = Image.new("L", (rw, rh), 0)
            ImageDraw.Draw(fill_mask).ellipse([0, 0, rw - 1, rh - 1], fill=255)
            canvas.paste(bg_fill, (0, 0), fill_mask)
        else:
            canvas.paste(bg_fill)

    px = (rw - nw) // 2 + int(offset_x)
    py = (rh - nh) // 2 + int(offset_y)
    canvas.paste(photo_rgba, (px, py), photo_rgba)

    if shape == "circle":
        mask = Image.new("L", (rw, rh), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, rw - 1, rh - 1], fill=255)
        r, g, b, a = canvas.split()
        canvas = Image.merge("RGBA", (r, g, b, ImageChops.multiply(a, mask)))
    # rect: canvas is already clipped to (rw × rh) — no mask required

    return canvas


# ─────────────────────────────── CV2 circle-fit: resize + contour mask ───────

def fit_photo_to_circle(photo: Image.Image, region: dict) -> Image.Image:
    """
    Resize *photo* (already face-cropped) to fill the circle in *region*,
    then apply a precise circular mask using CV2.

    Steps
    -----
    1. Cover-scale so the photo fills the circle bounding box.
    2. Center-crop to (width × height).
    3. Draw a filled circle contour as an 8-bit alpha mask via cv2.circle.
    4. Gaussian-blur the mask edge for smooth anti-aliasing.
    5. Return RGBA image of size (region.width × region.height).

    Falls back to PIL ellipse masking when OpenCV is unavailable.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return apply_photo_transform(photo, region, {})

    rw, rh = region["width"], region["height"]

    # ── 1 + 2: cover-scale then center-crop ──────────────────────────────
    photo_rgb = photo.convert("RGB")
    pw, ph = photo_rgb.width, photo_rgb.height
    scale = max(rw / pw, rh / ph)
    nw = max(1, int(pw * scale))
    nh = max(1, int(ph * scale))
    resized = photo_rgb.resize((nw, nh), Image.LANCZOS)

    x0 = (nw - rw) // 2
    y0 = (nh - rh) // 2
    cropped = np.array(resized.crop((x0, y0, x0 + rw, y0 + rh)))

    # ── 3: draw circle contour as filled mask ────────────────────────────
    mask = np.zeros((rh, rw), dtype=np.uint8)
    cx, cy   = rw // 2, rh // 2
    radius   = min(rw, rh) // 2
    cv2.circle(mask, (cx, cy), radius, 255, thickness=-1)

    # ── 4: anti-alias the hard circle edge ───────────────────────────────
    mask = cv2.GaussianBlur(mask, (5, 5), 2)

    # ── 5: combine RGB + mask as alpha channel ───────────────────────────
    rgba = np.dstack([cropped, mask])
    return Image.fromarray(rgba.astype(np.uint8), "RGBA")


def fit_photo_to_rect(photo: Image.Image, region: dict) -> Image.Image:
    """
    Resize *photo* (already face-cropped) to fill the rectangle in *region*,
    cover-scale + center-crop to exact dimensions.
    Returns fully-opaque RGBA; no mask needed for rectangular placement.
    """
    rw, rh = region["width"], region["height"]
    img = photo.convert("RGB")
    scale = max(rw / img.width, rh / img.height)
    nw = max(1, int(img.width * scale))
    nh = max(1, int(img.height * scale))
    resized = img.resize((nw, nh), Image.LANCZOS)
    x0 = (nw - rw) // 2
    y0 = (nh - rh) // 2
    return resized.crop((x0, y0, x0 + rw, y0 + rh)).convert("RGBA")


def _find_cascade(filename: str) -> str:
    """
    Locate a Haar cascade XML file in both normal Python environments and
    PyInstaller bundles (where cv2 data lands under sys._MEIPASS/cv2/data/).
    """
    import sys

    # PyInstaller onedir: all bundled data is under sys._MEIPASS
    if hasattr(sys, "_MEIPASS"):
        candidate = os.path.join(sys._MEIPASS, "cv2", "data", filename)
        if os.path.exists(candidate):
            return candidate

    # Normal Python: cv2.data.haarcascades is the standard location
    try:
        import cv2 as _cv2
        candidate = _cv2.data.haarcascades + filename
        if os.path.exists(candidate):
            return candidate
    except Exception:
        pass

    return filename   # CascadeClassifier will fail gracefully if not found


# ──────────────────────────────────────────── Haar-cascade face crop ─────────

def _expand_to_aspect(
    x1: int, y1: int, x2: int, y2: int,
    target_ratio: float, img_w: int, img_h: int,
) -> tuple[int, int, int, int]:
    """
    Symmetrically expand the (x1,y1,x2,y2) box — clamped to image bounds —
    so its width/height matches target_ratio (width:height). The shorter
    dimension is grown; the box centre is preserved as closely as possible.
    """
    cw, ch = x2 - x1, y2 - y1
    desired_w = ch * target_ratio
    if desired_w > cw:
        extra = int(round(desired_w - cw))
        x1 = max(0, x1 - extra // 2)
        x2 = min(img_w, x1 + cw + extra)
        if x2 - x1 < cw + extra:
            x1 = max(0, x2 - (cw + extra))
    else:
        desired_h = cw / target_ratio
        extra = int(round(desired_h - ch))
        y1 = max(0, y1 - extra // 2)
        y2 = min(img_h, y1 + ch + extra)
        if y2 - y1 < ch + extra:
            y1 = max(0, y2 - (ch + extra))
    return x1, y1, x2, y2


def _apply_circle_mask(photo: Image.Image) -> Image.Image:
    """
    Return a square RGBA image with a soft circular mask (transparent outside).
    Works with OpenCV (anti-aliased Gaussian edge) or falls back to PIL ellipse.
    """
    w, h = photo.size
    side = min(w, h)
    x0 = (w - side) // 2
    y0 = (h - side) // 2
    sq = photo.convert("RGBA").crop((x0, y0, x0 + side, y0 + side))

    try:
        import cv2
        import numpy as np

        arr  = np.array(sq.convert("RGB"))
        mask = np.zeros((side, side), dtype=np.uint8)
        cv2.circle(mask, (side // 2, side // 2), side // 2, 255, thickness=-1)
        mask = cv2.GaussianBlur(mask, (5, 5), 2)
        rgba = np.dstack([arr, mask])
        return Image.fromarray(rgba.astype(np.uint8), "RGBA")

    except ImportError:
        mask = Image.new("L", (side, side), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, side - 1, side - 1), fill=255)
        sq.putalpha(mask)
        return sq


PASSPORT_ASPECT = 35 / 45   # standard passport photo ratio, width:height (35mm x 45mm)


def extract_face(photo: Image.Image, shape: str = "rect") -> Image.Image:
    """
    Detect the largest face in *photo* using OpenCV Haar cascade and return
    a crop that includes hair/forehead, chin, and side clearance — suitable
    for an ID card portrait region.

    shape: "rect"     — rectangular crop (original behaviour)
           "passport" — passport-size crop (35:45 aspect ratio) centered on the face
           "circle"   — square crop with circular RGBA mask (transparent background)

    Requires:  pip install opencv-python
    Falls back silently to the original image if OpenCV is absent or no
    face is detected.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        if shape == "circle":
            return _apply_circle_mask(photo)
        return photo

    img_arr = np.array(photo.convert("RGB"))
    gray = cv2.cvtColor(img_arr, cv2.COLOR_RGB2GRAY)

    cascade_xml = _find_cascade("haarcascade_frontalface_default.xml")
    face_cascade = cv2.CascadeClassifier(cascade_xml)

    faces = face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
    )
    if not len(faces):
        if shape == "circle":
            return _apply_circle_mask(photo)
        return photo

    # Use the largest detected face
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])

    # Padding: hair/forehead above, shoulders + tie/half-uniform below
    pad_x   = int(w * 0.75)   # wider shoulders — more zoomed out
    pad_top = int(h * 1.10)   # more forehead/hair room
    pad_bot = int(h * 3.50)   # more body below chin

    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_top)
    x2 = min(photo.width,  x + w + pad_x)
    y2 = min(photo.height, y + h + pad_bot)

    if shape == "circle":
        # Expand the shorter side symmetrically to produce a square crop
        x1, y1, x2, y2 = _expand_to_aspect(x1, y1, x2, y2, 1.0, photo.width, photo.height)
    elif shape == "passport":
        # Expand/trim to the standard 35:45 passport photo aspect ratio
        x1, y1, x2, y2 = _expand_to_aspect(
            x1, y1, x2, y2, PASSPORT_ASPECT, photo.width, photo.height
        )

    cropped = photo.crop((x1, y1, x2, y2))

    if shape == "circle":
        return _apply_circle_mask(cropped)

    return cropped


# ──────────────────────────────────────── CV2 circle region detector ─────────

def detect_photo_region(template_image: Image.Image) -> "dict | None":
    """
    Find the photo-placeholder region (circle or rectangle) in a template.

    Strategy:
      1. Colour-mask: isolate light-green fills (common placeholder colour)
         → compute contour circularity:
           circularity > 0.70  → circle
           circularity < 0.70  → rectangle (if aspect ratio 0.5-2.0)
      2. Fallback: HoughCircles on the grayscale edge map (circles only).

    Returns a photo_region dict {"x","y","width","height","shape"} or None.
    Requires opencv-python.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    img = np.array(template_image.convert("RGB"))
    h_img, w_img = img.shape[:2]
    min_dim = min(w_img, h_img)
    # Photo placeholder must be < 25 % of template area (rejects background blobs)
    max_region_area = 0.25 * w_img * h_img

    # ── Method 1: colour-contour (light-green placeholder) ───────────────
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    # Narrow to genuine green: H 75-145° (excludes yellow walls H≈45-55°),
    # S ≥ 40 (excludes near-white/near-gray), V 140-255.
    mask = cv2.inRange(hsv, np.array([75, 40, 140]), np.array([145, 255, 255]))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(cnt)
        # Skip contours that are too small or unreasonably large
        if area < (min_dim * 0.05) ** 2:
            break
        if area > max_region_area:
            continue
        peri = cv2.arcLength(cnt, True)
        if peri < 10:
            continue
        circularity = 4 * 3.14159 * area / (peri * peri)

        if circularity > 0.70:
            # ── Circle ───────────────────────────────────────────────────
            (cx, cy), r = cv2.minEnclosingCircle(cnt)
            r = int(r)
            if min_dim * 0.04 < r < min_dim * 0.48:
                return {
                    "x": int(cx) - r, "y": int(cy) - r,
                    "width": 2 * r, "height": 2 * r,
                    "shape": "circle",
                }
        elif circularity < 0.70:
            # ── Rectangle / square ────────────────────────────────────────
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            aspect = rw / rh if rh > 0 else 0
            if (0.5 <= aspect <= 2.0
                    and rw > min_dim * 0.05 and rw < w_img * 0.65
                    and rh > min_dim * 0.05 and rh < h_img * 0.65):
                return {"x": rx, "y": ry, "width": rw, "height": rh, "shape": "rect"}

    # ── Method 2: HoughCircles on blurred grayscale ───────────────────────
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=int(min_dim * 0.15),
        param1=80, param2=35,
        minRadius=int(min_dim * 0.05),
        maxRadius=int(min_dim * 0.45),
    )
    if circles is not None:
        cx, cy, r = map(int, np.round(circles[0, 0]))
        return {"x": cx - r, "y": cy - r, "width": 2 * r, "height": 2 * r, "shape": "circle"}

    return None


# ──────────────────────────────── custom face extraction (with editor params) ─

def _post_process_face(
    img: Image.Image,
    brightness: float,
    contrast: float,
    flip_h: bool,
    flip_v: bool,
    shape: str,
) -> Image.Image:
    if flip_h:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if flip_v:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    if brightness != 1.0 or contrast != 1.0:
        from PIL import ImageEnhance
        if brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(brightness)
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)
    if shape == "circle":
        img = _apply_circle_mask(img)
    return img


def extract_face_custom(
    photo: Image.Image,
    zoom: float = 1.0,
    shift_x: float = 0.0,
    shift_y: float = 0.0,
    width_scale: float = 1.0,
    height_scale: float = 1.0,
    shape: str = "passport",
    brightness: float = 1.0,
    contrast: float = 1.0,
    flip_h: bool = False,
    flip_v: bool = False,
) -> "tuple[Image.Image, tuple | None, tuple | None]":
    """
    Detect the largest face in *photo* and return an adjusted crop.

    Returns (result, face_bbox, crop_bbox).
      result    : cropped + post-processed image (RGBA for circle, RGB for passport)
      face_bbox : (x1,y1,x2,y2) raw Haar detection in original px, or None
      crop_bbox : (x1,y1,x2,y2) final padded crop in original px, or None

    zoom         : padding multiplier — >1 shows more context, <1 tighter crop
    shift_x/y    : fraction of crop size to shift the crop centre (+right / +down)
    width_scale  : independent horizontal padding multiplier — lets the user
                   drag the crop box's left/right edge to widen/narrow it
                   without affecting height
    height_scale : independent vertical padding multiplier — drag the
                   top/bottom edge to grow/shrink height without affecting width
    shape        : "passport" | "circle"
    brightness, contrast : PIL ImageEnhance factors (1.0 = unchanged)
    flip_h, flip_v : mirror the cropped result
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return _post_process_face(photo, brightness, contrast, flip_h, flip_v, shape), None, None

    img_arr = np.array(photo.convert("RGB"))
    gray    = cv2.cvtColor(img_arr, cv2.COLOR_RGB2GRAY)

    cascade_xml  = _find_cascade("haarcascade_frontalface_default.xml")
    face_cascade = cv2.CascadeClassifier(cascade_xml)
    faces = face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
    )

    if not len(faces):
        result = _post_process_face(photo, brightness, contrast, flip_h, flip_v, shape)
        return result, None, None

    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    face_bbox = (x, y, x + w, y + h)

    # Base padding × zoom multiplier × per-axis drag-resize multiplier
    pad_x   = int(w * 0.75 * zoom * width_scale)
    pad_top = int(h * 1.10 * zoom * height_scale)
    pad_bot = int(h * 3.50 * zoom * height_scale)

    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_top)
    x2 = min(photo.width,  x + w + pad_x)
    y2 = min(photo.height, y + h + pad_bot)

    # Shift: fraction of crop dimensions (from drag in the editor)
    cw, ch = x2 - x1, y2 - y1
    dx = int(shift_x * cw)
    dy = int(shift_y * ch)
    x1 = max(0, min(photo.width  - cw, x1 + dx))
    y1 = max(0, min(photo.height - ch, y1 + dy))
    x2 = min(photo.width,  x1 + cw)
    y2 = min(photo.height, y1 + ch)

    # Reshape for circle (square 1:1) or passport (35:45) output
    if shape == "circle":
        x1, y1, x2, y2 = _expand_to_aspect(x1, y1, x2, y2, 1.0, photo.width, photo.height)
    elif shape == "passport":
        x1, y1, x2, y2 = _expand_to_aspect(
            x1, y1, x2, y2, PASSPORT_ASPECT, photo.width, photo.height
        )

    crop_bbox = (x1, y1, x2, y2)
    cropped   = photo.crop(crop_bbox)
    result    = _post_process_face(cropped, brightness, contrast, flip_h, flip_v, shape)
    return result, face_bbox, crop_bbox


# ────────────────────────────────────────────────── text wrapping ────────────

def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    first_max_w: int,
    cont_max_w: int | None = None,
) -> list[str]:
    """
    Word-wrap text.  First line respects first_max_w; subsequent lines use
    cont_max_w (falls back to first_max_w when not given).
    Never breaks in the middle of a word.
    """
    if cont_max_w is None:
        cont_max_w = first_max_w

    words = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        max_w = first_max_w if not lines else cont_max_w
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines or [text]


# ─────────────────────────────────────────────────── CardGenerator ───────────

class CardGenerator:
    def __init__(self):
        self.config: dict = {}
        self.template_image: Image.Image | None = None
        self.df: pd.DataFrame | None = None
        self.excel_dir: str = ""          # directory of the loaded Excel file
        # row_index → {x, y, scale, rotation}
        self.photo_transforms: dict[int, dict] = {}

    # ── config ───────────────────────────────────────────────────────────────

    def load_config(self, path: str) -> None:
        with open(path, encoding="utf-8") as fh:
            self.config = json.load(fh)
        tpl = self.config.get("template_image")
        if tpl and os.path.exists(tpl):
            self.load_template(tpl)

    def save_config(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.config, fh, indent=2, ensure_ascii=False)

    # ── data loading ─────────────────────────────────────────────────────────

    def load_template(self, path: str) -> None:
        self.template_image = Image.open(path).convert("RGBA")
        self.config["template_image"] = path

    def load_excel(self, path: str) -> pd.DataFrame:
        self.df = pd.read_excel(path, dtype=str).fillna("")
        self.df.columns = [c.strip() for c in self.df.columns]
        self.excel_dir = os.path.dirname(os.path.abspath(path))
        return self.df

    # ── OCR auto-detection ───────────────────────────────────────────────────

    def auto_detect_fields(self, excel_columns: "list[str] | None" = None) -> list[dict]:
        """
        Scan the loaded template with Tesseract OCR to find label bounding boxes,
        then compute where each value should be placed (just after the colon).

        Requires:  pip install pytesseract
                   + Tesseract binary on PATH
        """
        _configure_tesseract()
        try:
            import pytesseract
            from pytesseract import Output
        except ImportError:
            raise RuntimeError(
                "pytesseract is not installed.\n"
                "Run:  pip install pytesseract\n"
                "Also install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki"
            )

        if self.template_image is None:
            raise RuntimeError("Load a template image first.")

        def _nkw(s: str) -> str:
            """Normalise a label keyword: lowercase + strip every non-alphanumeric char."""
            return re.sub(r"[^a-z0-9]", "", s.lower())

        # Normalised keyword → (role, multiline)
        # Keys are already normalised so OCR noise like dots/spaces is tolerated:
        #   "D.O.B"  → _nkw → "dob"   ✓
        #   "ADMN."  → _nkw → "admn"  ✓
        #   "Class"  → _nkw → "class" ✓
        LABEL_MAP: dict[str, tuple[str, bool]] = {
            "class":     ("class",   False),
            "sec":       ("class",   False),          # "Class & Sec"
            "classandsec": ("class", False),          # merged token
            "dob":       ("dob",     False),          # "D.O.B" → "dob"
            "birth":     ("dob",     False),
            "dateofbirth": ("dob",   False),
            "admn":      ("admn",    False),          # "ADMN." → "admn"
            "adm":       ("admn",    False),          # partial read
            "admnno":    ("admn",    False),          # "ADMN.No" merged
            "admission": ("admn",    False),
            "admissionno": ("admn",  False),
            "name":      ("name",    False),
            "studentname": ("name",  False),
            "father":    ("father",  False),
            "fathername": ("father", False),
            "address":   ("address", True),
            "contact":   ("contact", False),
            "phone":     ("contact", False),
            "mobile":    ("contact", False),
            "blood":     ("blood",   False),
            "bloodgroup": ("blood",  False),
        }

        img_rgb = self.template_image.convert("RGB")
        img_w = img_rgb.width

        # 2× upscale before OCR; coordinates divided back after detection
        _scale = 2.0
        ocr_img = img_rgb.resize(
            (int(img_rgb.width * _scale), int(img_rgb.height * _scale)),
            Image.LANCZOS,
        )
        data = pytesseract.image_to_data(ocr_img, config="--psm 11",
                                         output_type=Output.DICT)
        n = len(data["text"])

        found: dict[str, dict] = {}

        for i in range(n):
            raw = data["text"][i].strip()
            if not raw:
                continue
            keyword = _nkw(raw)   # strips dots, spaces, colons — handles D.O.B, ADMN. etc.
            if keyword not in LABEL_MAP:
                continue
            conf = int(data["conf"][i]) if str(data["conf"][i]).lstrip("-").isdigit() else -1
            if conf < 0:
                continue

            col, multiline = LABEL_MAP[keyword]
            if col in found:
                continue

            lx = int(data["left"][i]   / _scale)
            ly = int(data["top"][i]    / _scale)
            lh = int(data["height"][i] / _scale)

            # Walk forward to find the colon; use its right edge as value start.
            # Window = 10 tokens to tolerate extra blank/punctuation tokens between
            # multi-word labels (e.g. "Father" "Name" ":") and their colon.
            right_edge = lx + int(data["width"][i] / _scale)
            for j in range(i, min(i + 10, n)):
                txt_j = data["text"][j].strip()
                if not txt_j:
                    continue
                if ":" in txt_j:
                    right_edge = int((data["left"][j] + data["width"][j]) / _scale)
                    break

            value_x = right_edge + 8
            value_y = ly
            font_size = max(9, int(lh * 0.78))
            avail = max(80, img_w - value_x - 20)

            found[col] = {
                "excel_column": col,
                "label": "",
                "x": value_x,
                "y": value_y,
                "font": "arial",
                "size": font_size,
                "bold": False,
                "color": "#000000",
                "align": "left",
                "transform": "",
                "max_width": avail if multiline else 0,
                "line_height": font_size + 4,
                "wrap_x": value_x,
            }

        # ── Direct Excel-column matching (overrides role key) ────────────────
        if excel_columns:
            def _norm(s: str) -> str:
                return re.sub(r"[\s\W_]+", "", s).lower()

            col_norm_map = {_norm(c): c for c in excel_columns}
            for field in found.values():
                role = field["excel_column"]
                if _norm(role) in col_norm_map:
                    field["excel_column"] = col_norm_map[_norm(role)]
                else:
                    for kw, (mapped_role, _) in LABEL_MAP.items():
                        if mapped_role == role and _norm(kw) in col_norm_map:
                            field["excel_column"] = col_norm_map[_norm(kw)]
                            break

        return list(found.values())

    # ── mapping-template auto-detect ──────────────────────────────────────────

    def auto_detect_from_mapping_template(
        self, mapping_path: str
    ) -> "tuple[list[dict], dict | None]":
        """
        Scan *mapping_path* — a template image containing placeholder text such as
        'name1', 'class1', 'dob1' — to extract:

          • text field positions (via Tesseract OCR)
          • photo circle region  (via CV2 colour contour / HoughCircles)

        Returns (fields_list, photo_region_or_None).
        Raises RuntimeError when pytesseract / Tesseract binary is unavailable.
        """
        _configure_tesseract()
        try:
            import pytesseract
            from pytesseract import Output
        except ImportError:
            raise RuntimeError(
                "pytesseract is not installed.\n"
                "pip install pytesseract\n"
                "Tesseract binary: https://github.com/UB-Mannheim/tesseract/wiki"
            )

        mapping_img = Image.open(mapping_path)
        img_rgb = mapping_img.convert("RGB")

        # Photo region detection does not need OCR
        photo_region = detect_photo_region(mapping_img)

        # Upscale 2× before OCR — dramatically improves accuracy on small/medium
        # resolution templates where placeholder text is rendered at 14–18 px.
        # Coordinates are divided back by this factor after detection.
        _scale = 2.0
        ocr_img = img_rgb.resize(
            (int(img_rgb.width * _scale), int(img_rgb.height * _scale)),
            Image.LANCZOS,
        )

        # Generic placeholder regex: pure-alphabetic prefix (2+ chars) followed
        # by a DIGIT-led suffix.  The digit requirement is the key discriminator:
        #   "class1"  → prefix="class",  suffix="1"   ✓  detected
        #   "admn1"   → prefix="admn",   suffix="1"   ✓  detected
        #   "ADMN."   → suffix starts with "."         ✗  excluded (label token)
        #   "Father"  → no digit suffix                ✗  excluded (label word)
        # This removes the hardcoded _PH list — any <word><digit> placeholder
        # in the template is detected automatically.
        _PH_RE = re.compile(r'^([a-zA-Z]{2,})(\d\S*)$')

        # Presentation hints for well-known role names.
        # Position is always read from the template — these only set style
        # defaults that users can override in FieldConfigDialog.
        _STYLE_HINTS: dict[str, dict] = {
            "name":    {"bold": True,  "align": "center", "transform": "",      "multiline": False},
            "blood":   {"bold": False, "align": "left",   "transform": "upper", "multiline": False},
            "address": {"bold": False, "align": "left",   "transform": "",      "multiline": True},
        }
        _DEFAULT_STYLE = {"bold": False, "align": "left", "transform": "", "multiline": False}

        col_map = self.config.get("column_map", {})

        def _norm(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", s.lower())

        # Normalised col_map keys → original key, for fuzzy role→column lookup
        col_map_norm = {_norm(k): k for k in col_map if not k.startswith("_")}

        # --psm 11: sparse text — finds text scattered across the image without
        # assuming a uniform block layout, ideal for ID-card templates.
        data = pytesseract.image_to_data(ocr_img, config="--psm 11",
                                         output_type=Output.DICT)
        img_w = img_rgb.width   # original width for max_width calculations
        found: dict[str, dict] = {}
        n = len(data["text"])

        for i in range(n):
            word = data["text"][i].strip()
            if not word:
                continue
            conf_raw = data["conf"][i]
            conf = int(conf_raw) if str(conf_raw).lstrip("-").isdigit() else -1
            if conf < 0:
                continue

            m = _PH_RE.fullmatch(word)
            if not m and re.match(r'^[a-zA-Z]{2,}$', word):
                # Tesseract sometimes splits "address1" → ["address", "1"].
                # Try merging with the next non-empty token to recover the match.
                for j in range(i + 1, min(i + 3, n)):
                    nxt = data["text"][j].strip()
                    if nxt:
                        m = _PH_RE.fullmatch(word + nxt)
                        break
            if not m:
                continue

            role = m.group(1).lower()   # alphabetic prefix, lowercased
            if role in found:
                continue

            # Map role to its Excel column via column_map:
            # 1. exact key match  ("admn"   → col_map["admn"])
            # 2. normalised match ("admnno" → col_map key that normalises the same)
            # 3. fallback         use role name as-is (user can fix in ColumnMapDialog)
            excel_col = col_map.get(role)
            if excel_col is None:
                ck = col_map_norm.get(_norm(role))
                excel_col = col_map.get(ck, role) if ck else role

            # Scale coordinates back to original image space
            lx = int(data["left"][i]   / _scale)
            ly = int(data["top"][i]    / _scale)
            lw = int(data["width"][i]  / _scale)
            lh = int(data["height"][i] / _scale)
            fs = max(9, int(lh * 0.82))

            style = _STYLE_HINTS.get(role, _DEFAULT_STYLE)

            field_x = lx + lw // 2 if style["align"] == "center" else lx

            if style["multiline"]:
                first_max_w = max(80, img_w - field_x - 20)
                cont_wrap_x = field_x   # continuation lines align with value start
            else:
                first_max_w = 0
                cont_wrap_x = field_x

            found[role] = {
                "excel_column": excel_col,
                "label":        "",
                "x":            field_x,
                "y":            ly,
                "font":         "arial",
                "size":         fs,
                "bold":         style["bold"],
                "color":        "#000000",
                "align":        style["align"],
                "transform":    style["transform"],
                "max_width":    first_max_w,
                "line_height":  fs + 4,
                "wrap_x":       cont_wrap_x,
            }

        # Normalize sizes: body fields (non-centred) are all the same font size
        # in any well-designed template; OCR bounding-box noise makes them drift
        # ±1-2 px.  Use the median to produce one consistent size for all of them.
        import statistics
        body = [f for f in found.values() if f["align"] != "center"]
        if len(body) >= 2:
            base = int(statistics.median(f["size"] for f in body))
            for f in body:
                f["size"] = base
                f["line_height"] = base + 4

        return list(found.values()), photo_region

    # ── card generation ───────────────────────────────────────────────────────

    def generate_card(
        self,
        row_data: dict,
        photo_transform: dict | None = None,
        template: Image.Image | None = None,
    ) -> Image.Image:
        tpl = template or self.template_image
        if tpl is None:
            raise ValueError("No template image loaded.")

        card = tpl.copy().convert("RGBA")
        draw = ImageDraw.Draw(card)

        col_map = self.config.get("column_map", {})

        # ── shared column-resolution helper (used for photo AND text fields) ──
        _row_ci: dict[str, str] = {str(k).lower(): k for k in row_data}
        # Case-insensitive col_map key lookup so configs saved with "Address"
        # as a key still resolve when the field asks for "address".
        _cmap_ci: dict[str, str] = {k.lower(): v for k, v in col_map.items()
                                     if not k.startswith("_")}

        def _resolve_value(excel_col: str) -> str:
            """
            Column resolution with full case-insensitivity at every step:
              1. Exact col_map key match
              2. Case-insensitive col_map key match
              3. Case-insensitive row data match of the resolved name
              4. Case-insensitive row data match of the raw excel_col
              5. Keyword-based role match via _ROLE_KEYWORDS
            """
            if not excel_col:
                return ""
            resolved = (col_map.get(excel_col)
                        or _cmap_ci.get(excel_col.lower())
                        or excel_col)
            for candidate in (resolved, excel_col):
                if candidate in row_data:
                    return str(row_data[candidate]).strip()
                key = _row_ci.get(candidate.lower())
                if key is not None:
                    return str(row_data[key]).strip()
            for kw in _ROLE_KEYWORDS.get(excel_col, []):
                key = _row_ci.get(kw.lower())
                if key is not None:
                    return str(row_data[key]).strip()
            return ""

        # ── photo ────────────────────────────────────────────────────────────
        photo_region = self.config.get("photo_region") or {}
        # photo_region must be explicitly configured (via FieldConfigDialog,
        # mapping-template load, or auto-detect on template open).
        # No runtime auto-detect here — wrong detection would corrupt every card.

        if photo_region:
            photo_col = self.config.get("photo_column") or "photo"
            photo_path = _resolve_value(photo_col)
            # Resolve relative paths against the Excel file's directory so that
            # "photos/student1.jpg" works regardless of the app's working directory.
            if photo_path and not os.path.isabs(photo_path) and self.excel_dir:
                photo_path = os.path.join(self.excel_dir, photo_path)
            if photo_path and os.path.exists(photo_path):
                try:
                    photo_img = Image.open(photo_path)
                    # Use cover-fit for both auto and manual paths.
                    # Manual transform carries user pan/zoom/rotation/bg_color;
                    # auto path defaults to cover-fit (scale=1.0, no pan/rotation).
                    tfm = photo_transform or {"x": 0, "y": 0, "scale": 1.0, "rotation": 0.0}
                    composed = apply_photo_transform(photo_img, photo_region, tfm)
                    card.paste(composed, (photo_region["x"], photo_region["y"]), composed)
                except Exception as exc:
                    print(f"[photo] {photo_path}: {exc}")

        # ── text fields ───────────────────────────────────────────────────────
        for field in self.config.get("fields", []):
            col = field.get("excel_column", "")
            raw = _resolve_value(col)

            txform = field.get("transform", "")
            if txform == "upper":
                raw = raw.upper()
            elif txform == "lower":
                raw = raw.lower()
            elif txform == "title":
                raw = raw.title()

            # label prefix is empty when it's already printed in the template
            text = field.get("label", "") + raw

            print(f"[{col}] '{text}'")
            if not text.strip():
                continue

            font = _get_font(
                field.get("font", "arial"),
                int(field.get("size", 12)),
                bool(field.get("bold", False)),
            )
            color = field.get("color", "#000000")
            x = int(field.get("x", 0))
            y = int(field.get("y", 0))
            align = field.get("align", "left")
            max_width = int(field.get("max_width", 0))

            if max_width > 0:
                # Multi-line field (e.g. address).
                # All lines — first and continuation — start at the same x so
                # wrapped text stays neatly aligned under the value start position.
                line_h = int(field.get("line_height", int(field.get("size", 12)) + 4))
                card_w = card.width
                avail_w = max(60, min(max_width, card_w - x - 10))

                # Optional: split on a separator before word-wrapping.
                # e.g. split_on="," turns "15 Main St, Chennai 600001"
                # into two logical lines before pixel-width wrapping is applied.
                split_on = field.get("split_on", "")
                if split_on:
                    raw_segs = re.split(re.escape(split_on), text)
                    segments = [s.strip() for s in raw_segs if s.strip()]
                    lines: list[str] = []
                    for seg in segments:
                        lines.extend(_wrap_text(draw, seg, font, avail_w, avail_w))
                else:
                    lines = _wrap_text(draw, text, font, avail_w, avail_w)

                # Optional fixed position for the last line (e.g. city/pin goes
                # to a different card row while earlier lines flow normally).
                raw_llx = field.get("last_line_x")
                raw_lly = field.get("last_line_y")
                last_pos = (int(raw_llx), int(raw_lly)) if (raw_llx is not None and raw_lly is not None) else None

                for li, line in enumerate(lines):
                    if last_pos and li == len(lines) - 1:
                        draw.text(last_pos, line, fill=color, font=font)
                    else:
                        draw.text((x, y + li * line_h), line, fill=color, font=font)
            else:
                if align == "center":
                    bbox = draw.textbbox((0, 0), text, font=font)
                    x = x - (bbox[2] - bbox[0]) // 2
                elif align == "right":
                    bbox = draw.textbbox((0, 0), text, font=font)
                    x = x - (bbox[2] - bbox[0])
                draw.text((x, y), text, fill=color, font=font)

        return card.convert("RGB")

    # ── batch generation ──────────────────────────────────────────────────────

    def generate_all(
        self,
        output_dir: str,
        progress_callback=None,
    ) -> list[str]:
        if self.df is None:
            raise ValueError("No Excel data loaded.")

        os.makedirs(output_dir, exist_ok=True)
        results: list[str] = []
        total = len(self.df)

        for i, (_, row) in enumerate(self.df.iterrows()):
            row_data = row.to_dict()
            try:
                card = self.generate_card(row_data, self.photo_transforms.get(i))
                col_map = self.config.get("column_map", {})
                _rci = {str(k).lower(): k for k in row_data}
                def _pick(role: str, fallback: str) -> str:
                    for cand in (col_map.get(role, role), role):
                        if cand in row_data:
                            return str(row_data[cand]).strip()
                        k = _rci.get(cand.lower())
                        if k:
                            return str(row_data[k]).strip()
                    for kw in _ROLE_KEYWORDS.get(role, []):
                        k = _rci.get(kw.lower())
                        if k:
                            return str(row_data[k]).strip()
                    return fallback
                name = _pick("name", f"student_{i}")
                admn = _pick("admn", str(i))
                safe = "".join(c for c in f"{admn}_{name}" if c not in r'\/:*?"<>|')
                path = os.path.join(output_dir, f"{safe}.jpg")
                card.save(path, "JPEG", quality=95)
                results.append(path)
            except Exception as exc:
                print(f"[row {i}] {exc}")


            if progress_callback:
                progress_callback(i + 1, total)

        return results

    # ── print sheet ───────────────────────────────────────────────────────────

    def create_print_sheet(
        self,
        card_paths: list[str],
        dpi: int = 300,
    ) -> list[Image.Image]:
        """
        Arrange cards on A4 landscape sheets: 5 columns × 2 rows = 10 per page.

        Cards are NOT resized — the template is assumed to already fit 1/5 of the
        landscape A4 width. Sheet width = 5 × card_w; sheet height = A4 landscape
        height (11.69 in wide-side, 8.27 in short-side at the given DPI).
        A 10-pixel gap between the two rows acts as a cutting guide.
        """
        if not card_paths:
            return []

        _COLS     = 5
        _ROWS     = 2
        _PER_PAGE = _COLS * _ROWS

        # A4 landscape: short side is the sheet height
        sheet_h = int(8.27 * dpi)

        sample = Image.open(card_paths[0])
        card_w, card_h = sample.size
        sample.close()

        # Sheet width fits 5 cards exactly (no column gap — easy vertical cuts)
        sheet_w = card_w * _COLS

        # Distribute leftover vertical space equally: above row 0, between rows, below row 1
        # total_content = 2 × card_h; remaining = sheet_h - total_content
        # gap = remaining // 3  → equal margin above, between, and below
        remaining = max(0, sheet_h - _ROWS * card_h)
        gap = remaining // 3          # equal spacing for top, middle, bottom
        top_y = gap
        row_gap = gap                 # same gap between rows as outside margins

        pages: list[Image.Image] = []

        for start in range(0, len(card_paths), _PER_PAGE):
            sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
            for idx, path in enumerate(card_paths[start : start + _PER_PAGE]):
                col = idx % _COLS
                row = idx // _COLS
                img = Image.open(path).convert("RGB")
                x = col * card_w
                y = top_y + row * (card_h + row_gap)
                sheet.paste(img, (x, y))
                img.close()
            pages.append(sheet)

        return pages
