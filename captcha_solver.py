"""
captcha_solver.py
═══════════════════════════════════════════════════════════════════
Multi-Type CAPTCHA Solver — Free, No API, No Fees
═══════════════════════════════════════════════════════════════════
Solver priority chain (auto-detected):
  1. reCAPTCHA v2  → Audio challenge + SpeechRecognition (Google STT free endpoint)
  2. Image CAPTCHA → ddddocr (offline CNN OCR, no API key)
  3. Math CAPTCHA  → Regex expression parser
  4. Text CAPTCHA  → ddddocr OCR fallback

Falls back to manual entry via GUI dialog if all automated methods fail.
"""

import os
import re
import time
import random
import urllib.request
import tkinter as tk
from tkinter import simpledialog
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ── Auto-locate FFmpeg so pydub works without shell restart ───────────────
def _find_ffmpeg() -> str:
    """Search common install paths for ffmpeg.exe and return the full path."""
    import shutil
    import glob

    # 1. Already on PATH (works after shell restart)
    found = shutil.which("ffmpeg")
    if found:
        return found

    # 2. Common winget install path (Gyan build)
    winget_pattern = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\**\ffmpeg.exe"
    )
    matches = glob.glob(winget_pattern, recursive=True)
    if matches:
        return matches[0]

    # 3. Chocolatey
    choco = r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"
    if os.path.exists(choco):
        return choco

    # 4. Common manual install locations
    for candidate in [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    ]:
        if os.path.exists(candidate):
            return candidate

    return "ffmpeg"  # last resort: rely on PATH


# Apply ffmpeg path to pydub before it is imported
_FFMPEG_PATH = _find_ffmpeg()
os.environ["PATH"] = os.path.dirname(_FFMPEG_PATH) + os.pathsep + os.environ.get("PATH", "")

# ── Optional heavy dependencies (graceful import) ─────────────────────────
try:
    import ddddocr
    _ocr = ddddocr.DdddOcr(show_ad=False)
    _HAS_OCR = True
except ImportError:
    _HAS_OCR = False

# ── Trained CNN model (loaded once at startup if weights exist) ───────────
_nn_model = None
_HAS_NN   = False

def _load_nn_model():
    """Load the trained TileCNN if captcha_model.pth exists."""
    global _nn_model, _HAS_NN
    try:
        import torch
        import pathlib
        weights = pathlib.Path(__file__).parent / "captcha_model.pth"
        if not weights.exists():
            return
        from captcha_model import TileCNN
        model = TileCNN()
        model.load_state_dict(torch.load(str(weights), map_location="cpu"))
        model.eval()
        _nn_model = model
        _HAS_NN   = True
        print("[CaptchaSolver] ✅ Trained CNN loaded from captcha_model.pth")
    except Exception as e:
        print(f"[CaptchaSolver] ⚠️  Could not load CNN model: {e}")

_load_nn_model()

# ── Tile data collection directory ────────────────────────────────────────
import pathlib as _pathlib
import atexit as _atexit
import shutil as _shutil
_TILES_DIR = _pathlib.Path(__file__).parent / "captcha_tiles"
_TILES_DIR.mkdir(exist_ok=True)

def _cleanup_tiles_on_exit():
    """
    Auto-called when bot process closes.
    Deletes label folders with < 5 images (not useful for training).
    Keeps folders with >= 5 images as training data.
    """
    try:
        deleted, kept, total = 0, 0, 0
        for folder in sorted(_TILES_DIR.iterdir()):
            if not folder.is_dir():
                continue
            images = list(folder.glob("*.png"))
            if len(images) < 5:
                _shutil.rmtree(str(folder), ignore_errors=True)
                deleted += 1
            else:
                kept  += 1
                total += len(images)
        print(f"[CaptchaSolver] 🧹 Exit cleanup: deleted {deleted} small folder(s), "
              f"kept {kept} folder(s) with {total} training image(s)")
    except Exception as e:
        print(f"[CaptchaSolver] ⚠️ Cleanup error: {e}")

_atexit.register(_cleanup_tiles_on_exit)

try:
    import speech_recognition as sr
    _HAS_SR = True
except ImportError:
    _HAS_SR = False

try:
    from pydub import AudioSegment
    _HAS_PYDUB = True
except ImportError:
    _HAS_PYDUB = False


# ── Helpers ───────────────────────────────────────────────────────────────
def _wait(driver, seconds=15) -> WebDriverWait:
    return WebDriverWait(driver, seconds)


def _manual_entry(prompt: str = "Enter CAPTCHA text manually:") -> Optional[str]:
    """Show a popup dialog for manual CAPTCHA entry."""
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        val = simpledialog.askstring("Manual CAPTCHA", prompt, parent=root)
        root.destroy()
        return val.strip() if val else None
    except Exception:
        return input(f"\n[MANUAL CAPTCHA] {prompt} ").strip()


def _solve_math(expr: str) -> Optional[str]:
    """Solve simple arithmetic expressions like '3 + 5', '12 - 4', '6 * 2'."""
    cleaned = re.sub(r'[^0-9+\-*/\s]', '', expr).strip()
    if not cleaned:
        return None
    try:
        result = eval(cleaned, {"__builtins__": {}})   # safe: only digits/ops
        return str(int(result))
    except Exception:
        return None


# ── Solver 1: reCAPTCHA v2 Audio Challenge ────────────────────────────────
def solve_recaptcha_audio(driver, log_fn=None) -> Optional[str]:
    """
    Solve reCAPTCHA v2 by switching to the audio challenge.
    Requires: pydub (pip install pydub) + FFmpeg on PATH

    Flow:
        1. Detect reCAPTCHA iframe and click checkbox
        2. Switch to challenge iframe and click 🔊 audio button
        3. Download the MP3 audio URL
        4. Convert MP3 → WAV via pydub
        5. Transcribe with SpeechRecognition (Google free endpoint)
        6. Type result and verify

    Returns:
        The transcribed text on success, or None on failure.
    """
    _log = log_fn or print

    if not _HAS_SR or not _HAS_PYDUB:
        _log("⚠️ SpeechRecognition / pydub not installed — skipping audio solver")
        return None

    mp3_path = "captcha_audio.mp3"
    wav_path = "captcha_audio.wav"

    try:
        wait = _wait(driver, 20)

        # Step 1: Click the reCAPTCHA checkbox (first iframe)
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        checkbox_frame = None
        for f in iframes:
            src = f.get_attribute("src") or ""
            if "recaptcha/api2/anchor" in src or "recaptcha" in src:
                checkbox_frame = f
                break

        if not checkbox_frame:
            _log("⚠️ No reCAPTCHA checkbox iframe found")
            return None

        driver.switch_to.frame(checkbox_frame)
        wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, ".recaptcha-checkbox-border, #recaptcha-anchor")
        )).click()
        driver.switch_to.default_content()
        time.sleep(random.uniform(1.5, 2.5))

        # Step 2: Switch to challenge iframe (bframe)
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        challenge_frame = None
        for f in iframes:
            src = f.get_attribute("src") or ""
            if "bframe" in src:
                challenge_frame = f
                break

        if not challenge_frame:
            driver.switch_to.default_content()
            return None

        driver.switch_to.frame(challenge_frame)
        time.sleep(random.uniform(0.5, 1.0))

        # Step 3: Click audio challenge button
        try:
            audio_btn = wait.until(EC.element_to_be_clickable((By.ID, "recaptcha-audio-button")))
            audio_btn.click()
        except Exception:
            _log("⚠️ Audio button not found (may need image challenge fallback)")
            driver.switch_to.default_content()
            return None

        time.sleep(random.uniform(1.0, 2.0))

        # Step 4: Get MP3 URL
        try:
            audio_src = driver.find_element(By.ID, "audio-source").get_attribute("src")
        except Exception:
            _log("⚠️ Audio source element not found")
            driver.switch_to.default_content()
            return None

        # Step 5: Download MP3
        urllib.request.urlretrieve(audio_src, mp3_path)

        # Step 6: Convert MP3 → WAV
        AudioSegment.from_mp3(mp3_path).export(wav_path, format="wav")

        # Step 7: Transcribe (Google's free anonymous STT endpoint)
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        text = recognizer.recognize_google(audio_data)
        _log(f"🔊 Audio CAPTCHA transcribed: '{text}'")

        # Step 8: Type into audio response field and verify
        resp_input = driver.find_element(By.ID, "audio-response")
        resp_input.clear()
        for ch in text.lower():
            resp_input.send_keys(ch)
            time.sleep(random.uniform(0.05, 0.15))

        driver.find_element(By.ID, "recaptcha-verify-button").click()
        driver.switch_to.default_content()
        time.sleep(random.uniform(1.0, 2.0))

        return text

    except Exception as e:
        _log(f"❌ Audio CAPTCHA solver error: {e}")
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
        return None

    finally:
        for path in (mp3_path, wav_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass


# ── Solver 2: Image / Text CAPTCHA via ddddocr ───────────────────────────
def solve_image_captcha(img_bytes: bytes, log_fn=None) -> Optional[str]:
    """
    Solve a raw image CAPTCHA using ddddocr (offline CNN OCR).

    Args:
        img_bytes : Raw bytes of the CAPTCHA image (PNG/JPG)

    Returns:
        Recognized text string, or None if ddddocr is unavailable.
    """
    _log = log_fn or print

    if not _HAS_OCR:
        _log("⚠️ ddddocr not installed — cannot solve image CAPTCHA")
        return None

    try:
        result = _ocr.classification(img_bytes)
        cleaned = re.sub(r'[^a-zA-Z0-9+\-*/\s]', '', result).strip()
        _log(f"🖼️ Image CAPTCHA OCR result: '{cleaned}' (raw: '{result}')")
        return cleaned
    except Exception as e:
        _log(f"❌ ddddocr error: {e}")
        return None


def solve_tile_number(img_bytes: bytes, log_fn=None) -> Optional[str]:
    """
    Extract the 3-digit number from a tile CAPTCHA image.

    Approach: color-aware multi-pipeline OCR.
    We NEVER use background colour to decide which tile to click.
    We extract the number from EVERY tile and compare against target.

    Pipelines (tried in order, majority vote on 3-digit results):
      0. Trained CNN              -- most accurate, used when available
      1. Grayscale enlarge        -- baseline
      2. HSV saturation mask      -- isolates digits from any bg colour
      3. Background subtraction   -- corner-sampled bg removal
      4. Per-channel best         -- uses R, G, or B channel separately
      5. High-contrast threshold  -- binarise
      6. Inverted                 -- for dark-bg tiles
      7. Stripe-removed           -- fixes underline/strikethrough
    """
    _log = log_fn or print

    # ── 0. Trained CNN ────────────────────────────────────────────
    if _HAS_NN and _nn_model is not None:
        try:
            import torch, io
            from PIL import Image
            from torchvision import transforms
            from captcha_model import IMG_SIZE, NORM_MEAN, NORM_STD
            tfm = transforms.Compose([
                transforms.Resize((IMG_SIZE, IMG_SIZE)),
                transforms.ToTensor(),
                transforms.Normalize(mean=NORM_MEAN, std=NORM_STD),
            ])
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            tensor = tfm(img).unsqueeze(0)
            result = _nn_model.predict_number(tensor)[0]
            _log(f"\U0001f916 CNN prediction: '{result}'")
            return result
        except Exception as e:
            _log(f"\u26a0\ufe0f CNN failed: {e}")

    if not _HAS_OCR:
        return None

    try:
        from PIL import Image, ImageOps, ImageFilter, ImageEnhance
        import io, numpy as np

        def _ocr_digits(pil_img):
            """Run ddddocr and return only digit characters."""
            buf = io.BytesIO()
            pil_img.save(buf, format='PNG')
            raw = _ocr.classification(buf.getvalue())
            return re.sub(r'[^0-9]', '', raw), raw

        def _to_ocr_size(img, scale=4):
            w, h = img.size
            return img.resize((w * scale, h * scale), Image.LANCZOS)

        base = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        arr  = np.array(base, dtype=np.float32)   # (H, W, 3)
        H, W, _ = arr.shape
        candidates = []

        # ── Pipeline 1: Grayscale enlarge + sharpen ───────────────
        p1 = _to_ocr_size(base.convert('L'))
        p1 = p1.filter(ImageFilter.SHARPEN)
        d, r1 = _ocr_digits(p1)
        if d: candidates.append(d)

        # ── Pipeline 2: HSV saturation mask ───────────────────────
        # Digits are saturated (vivid colour); background is pastel/white.
        # Extract only the high-saturation pixels → black digits on white bg.
        try:
            hsv = base.convert('HSV')
            h_arr, s_arr, v_arr = (np.array(hsv, dtype=np.float32)[:,:,i] for i in range(3))
            # Threshold: pixels with saturation > 60/255 are digits
            sat_thresh = 55
            digit_mask = (s_arr > sat_thresh).astype(np.uint8) * 255
            # Invert so digits are BLACK on WHITE (better for OCR)
            digit_img = Image.fromarray(255 - digit_mask, 'L')
            p2 = _to_ocr_size(digit_img)
            p2 = p2.filter(ImageFilter.SHARPEN)
            d, r2 = _ocr_digits(p2)
            if d: candidates.append(d)
        except Exception:
            r2 = ''

        # ── Pipeline 3: Background subtraction (corner sampling) ──
        # Estimate background from the 4 corner regions, then subtract.
        try:
            border = max(5, H // 8)
            corners = np.concatenate([
                arr[:border, :border].reshape(-1, 3),
                arr[:border, -border:].reshape(-1, 3),
                arr[-border:, :border].reshape(-1, 3),
                arr[-border:, -border:].reshape(-1, 3),
            ])
            bg_colour = np.median(corners, axis=0)  # robust bg estimate
            dist = np.linalg.norm(arr - bg_colour, axis=2)  # (H, W)
            # Pixels far from background = digits → make them black
            fg = (dist > 25).astype(np.uint8) * 255
            fg_img = Image.fromarray(255 - fg, 'L')  # digits = black
            p3 = _to_ocr_size(fg_img)
            p3 = p3.filter(ImageFilter.SHARPEN)
            d, r3 = _ocr_digits(p3)
            if d: candidates.append(d)
        except Exception:
            r3 = ''

        # ── Pipeline 4: Best single channel ───────────────────────
        # For coloured digits the channel OPPOSITE to their hue gives
        # the most contrast (e.g., green digits → red channel is dark).
        try:
            r_ch = Image.fromarray(arr[:,:,0].astype(np.uint8), 'L')
            g_ch = Image.fromarray(arr[:,:,1].astype(np.uint8), 'L')
            b_ch = Image.fromarray(arr[:,:,2].astype(np.uint8), 'L')
            best_contrast, best_ch = 0, r_ch
            for ch in (r_ch, g_ch, b_ch):
                ch_arr = np.array(ch, dtype=np.float32)
                contrast = ch_arr.std()
                if contrast > best_contrast:
                    best_contrast = contrast
                    best_ch = ch
            p4 = _to_ocr_size(best_ch)
            p4 = ImageEnhance.Contrast(p4).enhance(3.0)
            p4 = p4.point(lambda px: 0 if px < 128 else 255)
            d, r4 = _ocr_digits(p4)
            if d: candidates.append(d)
        except Exception:
            r4 = ''

        # ── Pipeline 5: High-contrast grayscale threshold ─────────
        p5 = ImageEnhance.Contrast(base.convert('L')).enhance(3.0)
        p5 = _to_ocr_size(p5)
        p5 = p5.point(lambda px: 0 if px < 128 else 255)
        d, r5 = _ocr_digits(p5)
        if d: candidates.append(d)

        # ── Pipeline 6: Inverted ──────────────────────────────────
        p6 = ImageOps.invert(base.convert('L'))
        p6 = ImageEnhance.Contrast(p6).enhance(2.5)
        p6 = _to_ocr_size(p6)
        d, r6 = _ocr_digits(p6)
        if d: candidates.append(d)

        # ── Pipeline 7: Stripe/underline removal + grayscale ──────
        try:
            bg_colour_mode = bg_colour if 'bg_colour' in dir() else np.array([240,240,240], dtype=np.float32)
            dist2 = np.linalg.norm(arr - bg_colour_mode, axis=2)
            fg_mask = dist2 > 30
            row_fg  = fg_mask.sum(axis=1) / W
            border7 = max(3, H // 10)
            stripe_rows = []
            i = border7
            while i < H - border7:
                if row_fg[i] > 0.60:
                    run_s = i
                    while i < H - border7 and row_fg[i] > 0.60:
                        i += 1
                    if i - run_s <= 4:
                        stripe_rows.extend(range(run_s, i))
                else:
                    i += 1
            if stripe_rows:
                arr7 = arr.copy()
                bg7  = bg_colour_mode if 'bg_colour' in dir() else np.array([240,240,240])
                for y in stripe_rows:
                    arr7[y] = bg7
                clean = Image.fromarray(arr7.astype(np.uint8), 'RGB')
                p7 = _to_ocr_size(clean.convert('L'))
                p7 = p7.filter(ImageFilter.SHARPEN)
                d, r7 = _ocr_digits(p7)
                if d: candidates.append(d)
            else:
                r7 = ''
        except Exception:
            r7 = ''

        _log(f"\U0001f4f7 Candidates: {candidates} "
             f"(sat='{r2}' bgsub='{r3}' ch='{r4}' stripe='{r7}')")

        if not candidates:
            return ''

        # Prefer 3-digit results by majority vote
        three = [c for c in candidates if len(c) == 3]
        if three:
            from collections import Counter
            return Counter(three).most_common(1)[0][0]

        valid = [c for c in candidates if 2 <= len(c) <= 4]
        if valid:
            from collections import Counter
            return Counter(valid).most_common(1)[0][0]

        return candidates[0]

    except Exception as e:
        _log(f"\u274c solve_tile_number error: {e}")
        return None


def _save_tile(img_bytes: bytes, label: str, idx: int) -> None:
    """
    Save a tile screenshot to captcha_tiles/<label>/tile_<ts>_<idx>.png
    for training data collection. Silently ignores errors.
    """
    try:
        if not (label and label.isdigit() and len(label) == 3):
            return
        dest_dir = _TILES_DIR / label
        dest_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        fname = dest_dir / f"tile_{ts}_{idx}.png"
        with open(str(fname), "wb") as f:
            f.write(img_bytes)
    except Exception:
        pass


# ── Solver 3: Math / Arithmetic CAPTCHA ──────────────────────────────────
def solve_math_captcha(text: str, log_fn=None) -> Optional[str]:
    """
    Detect and solve arithmetic CAPTCHAs like '3 + 5 = ?', 'What is 12-4?'

    Returns:
        Answer string, or None if no math expression detected.
    """
    _log = log_fn or print
    patterns = [
        r'(\d+\s*[+\-*/x×÷]\s*\d+)',
        r'What\s+is\s+(\d+\s*[+\-*/]\s*\d+)',
        r'(\d+)\s*plus\s*(\d+)',
        r'(\d+)\s*minus\s*(\d+)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            expr = m.group(1) if m.lastindex == 1 else f"{m.group(1)}+{m.group(2)}"
            expr = expr.replace('x', '*').replace('×', '*').replace('÷', '/')
            answer = _solve_math(expr)
            if answer:
                _log(f"🔢 Math CAPTCHA solved: '{expr}' = {answer}")
                return answer
    return None


# ── Main Entry: Auto-detect and Solve ─────────────────────────────────────
class CaptchaSolver:
    """
    High-level CAPTCHA solver. Tries each method in order and returns
    the first successful answer.

    Usage:
        solver = CaptchaSolver(driver, log_fn=self.log)
        answer = solver.solve()
        if answer:
            captcha_input.clear()
            captcha_input.send_keys(answer)
    """

    def __init__(self, driver, log_fn=None, max_retries=3):
        self.driver      = driver
        self._log        = log_fn or print
        self.max_retries = max_retries

    def solve(self) -> Optional[str]:
        """
        Auto-detect and solve CAPTCHA on the current page.

        Detection order:
            1. Check for Tile CAPTCHA -> tile solver
            2. Check for reCAPTCHA iframe → audio solver
            3. Check for img[src*=captcha] → ddddocr image solver
            4. Check for math text on page → math solver
            5. Manual dialog fallback

        Returns:
            Solved text/number string, or None.
        """
        for attempt in range(1, self.max_retries + 1):
            self._log(f"🧩 CAPTCHA solve attempt {attempt}/{self.max_retries}...")

            # ── Method A: Tile CAPTCHA ──────────────────────────────────
            if self._is_tile_captcha():
                success = self.solve_tile_captcha()
                if success:
                    return "TILES_CLICKED"
                self._log("⚠️ Tile CAPTCHA solver failed — trying next method")

            # ── Method B: reCAPTCHA v2 ──────────────────────────────────
            if self._has_recaptcha():
                self._log("🔍 reCAPTCHA v2 detected → trying audio solver...")
                result = solve_recaptcha_audio(self.driver, self._log)
                if result:
                    return result
                self._log("⚠️ Audio solver failed — trying next method")

            # ── Method C: Image CAPTCHA ─────────────────────────────────
            img_element = self._find_captcha_image()
            if img_element and not self._is_tile_captcha():
                self._log("🔍 Image CAPTCHA detected → trying ddddocr...")
                try:
                    img_bytes = img_element.screenshot_as_png
                    result = solve_image_captcha(img_bytes, self._log)

                    # If result looks like math, evaluate it
                    if result:
                        math_ans = _solve_math(result)
                        return math_ans if math_ans else result

                except Exception as e:
                    self._log(f"⚠️ Image capture error: {e}")

            # ── Method D: Math/Text CAPTCHA in visible text ─────────────
            page_text = self._get_page_text()
            if page_text:
                result = solve_math_captcha(page_text, self._log)
                if result:
                    return result

            # Short pause before retry
            time.sleep(random.uniform(1.5, 3.0))

        # ── Fallback: Manual entry ──────────────────────────────────────
        self._log("🙋 All automated methods failed — requesting manual CAPTCHA entry")
        return _manual_entry("All CAPTCHA solvers failed. Please enter the CAPTCHA text:")

    def _has_recaptcha(self) -> bool:
        """Check if any reCAPTCHA iframe exists on the page."""
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for f in iframes:
                src = f.get_attribute("src") or ""
                if "recaptcha" in src or "captcha" in src.lower():
                    return True
        except Exception:
            pass
        return False

    def _find_captcha_image(self):
        """Find a CAPTCHA image element on the page."""
        selectors = [
            "img[src*='captcha']",
            "img[id*='captcha']",
            "img[class*='captcha']",
            "img[alt*='captcha']",
            ".captcha img",
            "#captchaImage",
            "#CaptchaImage",
        ]
        for sel in selectors:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    return els[0]
            except Exception:
                continue
        return None

    def _get_page_text(self) -> str:
        """Get visible text from the page body for math CAPTCHA detection."""
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            return body.text[:2000]
        except Exception:
            return ""

    def _is_tile_captcha(self) -> bool:
        """Check if we are on a Tile CAPTCHA page."""
        try:
            imgs = self.driver.find_elements(By.CSS_SELECTOR, "img.captcha-img, img[src*='captcha' i], img[class*='captcha' i]")
            visible_imgs = [img for img in imgs if img.is_displayed() and img.size['width'] > 20 and img.size['height'] > 20]
            if len(visible_imgs) >= 4:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                if "select all" in body_text:
                    return True
        except Exception:
            pass
        return False

    def solve_tile_captcha(self) -> bool:
        """Solve Tile CAPTCHA by identifying the target number and clicking matching visible tiles."""
        self._log("🧩 Tile CAPTCHA detected — starting solver...")
        try:
            # 1. Find the visible instruction and extract the target number
            target_number = None

            # Start with strictly .box-label class, fall back to broader list if missing
            instruction_elements = self.driver.find_elements(By.CSS_SELECTOR, ".box-label")
            if not instruction_elements:
                instruction_elements = self.driver.find_elements(By.CSS_SELECTOR, "p, div, label, span")

            # Group all valid instruction candidates by (x, y) coordinate.
            # On the live page ALL labels stack at the same absolute position; only
            # the one with the highest z-index is visually shown to the user.
            instruction_groups = {}  # pos -> list of (el, z_val, text)
            for el in instruction_elements:
                try:
                    if not el.is_displayed():
                        continue

                    # Guard: off-screen
                    loc = el.location
                    if loc and (loc['x'] < 0 or loc['y'] < 0):
                        continue

                    # Guard: visibility property
                    visibility = el.value_of_css_property("visibility")
                    if visibility and visibility.lower() in ("hidden", "collapse"):
                        continue

                    # Guard: near-zero opacity
                    opacity = el.value_of_css_property("opacity")
                    if opacity:
                        try:
                            if float(opacity) < 0.1:
                                continue
                        except ValueError:
                            pass

                    # Guard: zero font-size
                    font_size = el.value_of_css_property("font-size")
                    if font_size:
                        fs_lower = font_size.lower().strip()
                        if fs_lower in ("0px", "0") or fs_lower.startswith("0"):
                            continue

                    text = el.text.strip()
                    if not text or "\n" in text:
                        continue  # skip empty / multiline containers
                    if "select all" not in text.lower():
                        continue

                    # Get computed z-index so we can pick the topmost label
                    z_index = el.value_of_css_property("z-index")
                    try:
                        z_val = int(z_index) if z_index and z_index != "auto" else 0
                    except ValueError:
                        z_val = 0

                    pos = (loc['x'], loc['y'])
                    if pos not in instruction_groups:
                        instruction_groups[pos] = []
                    instruction_groups[pos].append((el, z_val, text))
                except Exception:
                    pass

            # For each unique position group, pick the element with the highest z-index
            # (that is the one rendered on top — i.e. visible to the user)
            best_text = None
            best_z = -1
            for pos, candidates in instruction_groups.items():
                candidates_sorted = sorted(candidates, key=lambda x: x[1], reverse=True)
                top_el, top_z, top_text = candidates_sorted[0]
                # Also try color filter as a secondary confirmation when possible
                try:
                    color = top_el.value_of_css_property("color")
                    is_white = False
                    if color:
                        c_lower = color.lower().replace(" ", "")
                        if c_lower in ("white", "#ffffff", "#fff", "#fffffa", "#fafafa", "transparent"):
                            is_white = True
                        else:
                            cm = re.search(r'rgba?\((\d+),(\d+),(\d+)(?:,([\d.]+))?\)', c_lower)
                            if cm:
                                r, g, b = int(cm.group(1)), int(cm.group(2)), int(cm.group(3))
                                a = float(cm.group(4)) if cm.group(4) else 1.0
                                if (r > 240 and g > 240 and b > 240) or a < 0.1:
                                    is_white = True
                    # Only reject if clearly white AND there's a non-white alternative
                    non_white = [(e, z, t) for e, z, t in candidates_sorted if z < top_z]
                    if is_white and non_white:
                        top_el, top_z, top_text = non_white[0]
                except Exception:
                    pass

                if top_z > best_z:
                    best_z = top_z
                    best_text = top_text

            if best_text:
                self._log(f"📋 Visible instruction: '{best_text}'")
                m = re.search(r'number\s+(\d+)', best_text, re.IGNORECASE)
                if m:
                    target_number = m.group(1)

            if not target_number:
                self._log("❌ Could not extract target number from visible instructions")
                return False

            self._log(f"🎯 Target number is: {target_number}")

            # 2. Find all visible tile images
            all_imgs = self.driver.find_elements(By.CSS_SELECTOR, "img.captcha-img, img[src*='captcha' i], img[class*='captcha' i]")
            
            # Group overlapping visible tiles by coordinate position (x, y)
            tile_groups = {}
            for img in all_imgs:
                try:
                    if img.is_displayed() and img.size['width'] > 20 and img.size['height'] > 20:
                        loc = img.location
                        pos = (loc['x'], loc['y'])
                        
                        # Get z-index of the parent element
                        parent = img.find_element(By.XPATH, "..")
                        z_index = parent.value_of_css_property("z-index")
                        try:
                            z_val = int(z_index) if z_index and z_index != "auto" else 0
                        except ValueError:
                            z_val = 0
                            
                        if pos not in tile_groups:
                            tile_groups[pos] = []
                        tile_groups[pos].append((img, z_val))
                except Exception:
                    pass

            # For each unique coordinate, select only the tile with the highest z-index
            visible_tiles = []
            for pos, group in sorted(tile_groups.items()):
                group_sorted = sorted(group, key=lambda x: x[1], reverse=True)
                visible_tiles.append(group_sorted[0][0])

            self._log(f"Found {len(visible_tiles)} visible tile images")

            if not visible_tiles:
                self._log("❌ No visible tiles found")
                return False

            # 3. OCR each visible tile and click if it matches
            # Strategy A: multi-pipeline OCR (digits only)
            # Strategy B: background-colour detection — the CAPTCHA highlights
            #             matching tiles with a pink/salmon background, so any tile
            #             whose average pixel colour is clearly non-white/non-gray
            #             is also a candidate.
            clicked_count = 0
            ocr_results = []  # [(idx, img, result)]

            for idx, img in enumerate(visible_tiles):
                try:
                    img_bytes = img.screenshot_as_png

                    # OCR the tile number and record result
                    result = solve_tile_number(img_bytes, self._log)
                    if result:
                        result = re.sub(r'[^0-9]', '', result).strip()
                    else:
                        result = ''

                    match = (result == target_number)
                    self._log(f"Tile [{idx}]: OCR='{result}' | {'\u2705 MATCH' if match else '\u274c no match'}")
                    ocr_results.append((idx, img, result))

                    # Save tile for training only if OCR produced a confident 3-digit number
                    # Label = OCR result (accurate label, not just the target)
                    if result and len(result) == 3 and result.isdigit():
                        _save_tile(img_bytes, result, idx)

                except Exception as e:
                    self._log(f"⚠️ Error processing tile [{idx}]: {e}")

            # Pure OCR matching: click every tile whose number matches target
            tiles_to_click = [(idx, img) for idx, img, r in ocr_results
                              if r == target_number]
            self._log(f"🎯 {len(tiles_to_click)} tile(s) matched target '{target_number}'")

            for idx, img in tiles_to_click:
                try:
                    self._log(f"   -> Clicking Tile [{idx}]")
                    try:
                        from stealth_engine import human_move_to
                        human_move_to(self.driver, img)
                        img.click()
                    except Exception:
                        try:
                            self.driver.execute_script("arguments[0].click();", img)
                        except Exception:
                            pass
                    clicked_count += 1
                    time.sleep(random.uniform(0.3, 0.7))
                except Exception as e:
                    self._log(f"⚠️ Error clicking tile [{idx}]: {e}")

            self._log(f"✅ Clicked {clicked_count} matching tiles")
            return clicked_count > 0

        except Exception as e:
            self._log(f"❌ Tile CAPTCHA solver error: {e}")
            return False
