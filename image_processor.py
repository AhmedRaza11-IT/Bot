"""
image_processor.py
═══════════════════════════════════════════════════════════════════
Passport Photo Auto-Processor for BLS Italy Bot
═══════════════════════════════════════════════════════════════════
• Auto-detects input format (PNG, JPG, BMP, WEBP, TIFF)
• Corrects EXIF orientation
• Resizes to BLS Italy Schengen spec: 35×45mm @ 300 DPI = 413×531 px
• Composites on white background (handles transparent PNGs)
• Compresses to ≤ 200 KB JPEG (BLS upload limit)
• Saves processed file to ./pending_reservations/passport_processed.jpg
"""

import os
from pathlib import Path
from typing import Optional, Tuple

# Pillow import with friendly error
try:
    from PIL import Image, ImageOps
except ImportError:
    raise ImportError(
        "Pillow is required for image processing. "
        "Run: pip install Pillow"
    )

# ── BLS Italy Schengen visa photo specification ───────────────────────────
BLS_WIDTH_PX  = 413    # 35 mm @ 300 DPI
BLS_HEIGHT_PX = 531    # 45 mm @ 300 DPI
BLS_MAX_KB    = 200    # maximum upload file size
BLS_DPI       = (300, 300)
BLS_FORMAT    = "JPEG"
BLS_BG_COLOR  = (255, 255, 255)   # white background

OUTPUT_DIR  = "./pending_reservations"
OUTPUT_NAME = "passport_processed.jpg"


def process_passport_photo(
    input_path: str,
    output_path: Optional[str] = None,
    target_size: Tuple[int, int] = (BLS_WIDTH_PX, BLS_HEIGHT_PX),
    max_kb: int = BLS_MAX_KB,
    log_fn=None,
) -> str:
    """
    Process a raw passport photo for BLS Italy upload.

    Steps:
        1. Open & convert to RGB
        2. Correct EXIF rotation
        3. Scale to fit inside target_size (Lanczos)
        4. Composite centered on white canvas
        5. Iteratively lower JPEG quality until ≤ max_kb
        6. Save and return output path

    Args:
        input_path  : Path to the source image file
        output_path : Destination path. Defaults to pending_reservations/passport_processed.jpg
        target_size : (width, height) in pixels
        max_kb      : Maximum output file size in kilobytes
        log_fn      : Optional logging callback (e.g. bot's log function)

    Returns:
        Absolute path to the processed output file
    """
    _log = log_fn or print
    target_w, target_h = target_size

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Passport image not found: {input_path}")

    if output_path is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, OUTPUT_NAME)

    _log(f"🖼️ Processing passport photo: {input_path}")

    with Image.open(input_path) as img:

        # Step 1: Ensure RGB (handles RGBA, P/palette with transparency, L/grayscale, CMYK)
        if img.mode == "P" and "transparency" in img.info:
            img = img.convert("RGBA")

        if img.mode in ("RGBA", "LA", "PA"):
            # Composite transparent image onto white background first
            bg = Image.new("RGB", img.size, BLS_BG_COLOR)
            if img.mode == "RGBA":
                bg.paste(img, mask=img.split()[3])  # use alpha as mask
            else:
                bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[3])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Step 2: Auto-rotate based on EXIF data (phone photos are often sideways)
        img = ImageOps.exif_transpose(img)

        orig_w, orig_h = img.size
        _log(f"📐 Original: {orig_w}×{orig_h}px  →  Target: {target_w}×{target_h}px")

        # Step 3: Scale to fit inside target (letterbox, keep aspect ratio)
        scale   = min(target_w / orig_w, target_h / orig_h)
        new_w   = max(1, int(orig_w * scale))
        new_h   = max(1, int(orig_h * scale))
        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Step 4: Paste centered on a white canvas
        canvas = Image.new("RGB", (target_w, target_h), BLS_BG_COLOR)
        paste_x = (target_w - new_w) // 2
        paste_y = (target_h - new_h) // 2
        canvas.paste(resized, (paste_x, paste_y))

        # Step 5: Compress iteratively until under max_kb
        quality = 90
        while quality >= 30:
            canvas.save(
                output_path,
                format=BLS_FORMAT,
                quality=quality,
                optimize=True,
                dpi=BLS_DPI,
            )
            file_kb = os.path.getsize(output_path) / 1024
            if file_kb <= max_kb:
                break
            quality -= 5

        final_kb = os.path.getsize(output_path) / 1024
        _log(
            f"✅ Passport photo saved → {output_path}\n"
            f"   Dimensions : {target_w}×{target_h} px  |  "
            f"Size: {final_kb:.1f} KB  |  Quality: {quality}"
        )

    return os.path.abspath(output_path)


def get_processed_image_path(raw_path: str, log_fn=None) -> str:
    """
    Convenience wrapper: process the raw passport image and return
    the path to the upload-ready processed file.

    Call this before the Selenium file upload step.
    """
    return process_passport_photo(raw_path, log_fn=log_fn)
