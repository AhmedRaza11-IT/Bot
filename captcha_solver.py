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
            1. Check for reCAPTCHA iframe → audio solver
            2. Check for img[src*=captcha] → ddddocr image solver
            3. Check for math text on page → math solver
            4. Manual dialog fallback

        Returns:
            Solved text/number string, or None.
        """
        for attempt in range(1, self.max_retries + 1):
            self._log(f"🧩 CAPTCHA solve attempt {attempt}/{self.max_retries}...")

            # ── Method A: reCAPTCHA v2 ──────────────────────────────────
            if self._has_recaptcha():
                self._log("🔍 reCAPTCHA v2 detected → trying audio solver...")
                result = solve_recaptcha_audio(self.driver, self._log)
                if result:
                    return result
                self._log("⚠️ Audio solver failed — trying next method")

            # ── Method B: Image CAPTCHA ─────────────────────────────────
            img_element = self._find_captcha_image()
            if img_element:
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

            # ── Method C: Math/Text CAPTCHA in visible text ─────────────
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
