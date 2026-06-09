"""
selenium_bot.py
═══════════════════════════════════════════════════════════════════
BLS Italy Appointment Bot — Full Automation Engine
═══════════════════════════════════════════════════════════════════
Features implemented:
  ✅ Feature 1  - Auto Login + Multi-type CAPTCHA Solving (free)
  ✅ Feature 2  - Unlimited Usage (no keys, no limits)
  ✅ Feature 4  - Auto IP Rotation (paid + free hybrid)
  ✅ Feature 5  - 8-Layer Anti-Bot Detection Bypass
  ✅ Feature 6  - Auto Email OTP Verification
  ✅ Feature 7  - Auto Passport Image Upload + Resize
  ✅ Bonus      - Auto-books slot + sounds alert + logs to GUI
"""

import os
import re
import time
import random
import threading
import winsound
import subprocess
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException
)

# ── Internal modules ──────────────────────────────────────────────────────
from stealth_engine   import (get_chrome_options, apply_stealth_patches,
                               warm_up_session, human_delay, human_move_to,
                               human_type, human_scroll, micro_delay)
from proxy_manager    import ProxyManager, build_proxy_extension
from captcha_solver   import CaptchaSolver
from email_reader     import EmailReader
from image_processor  import get_processed_image_path

# ── Target portal URLs ────────────────────────────────────────────────────
BASE_URL       = "https://appointment.theitalyvisa.com"
LOGIN_URL      = f"{BASE_URL}/Global/Account/LogIn"
APPT_URL       = f"{BASE_URL}/Global/appointment/newappointment"

# ── Timeouts ──────────────────────────────────────────────────────────────
PAGE_TIMEOUT   = 30
ELEMENT_WAIT   = 15

# ── Global mutable state (hot-reloadable without restart) ─────────────────
live_state = {
    "config":      {},
    "image_path":  "",
    "stop_flag":   False,
    "pause_flag":  False,
}


def update_live_session(new_config: dict):
    """Called by dashboard Resume: hot-reload config into running engine."""
    live_state["config"] = new_config
    print("✅ Live config reloaded into running engine.")


# ── Utilities ─────────────────────────────────────────────────────────────
def _wait(driver, secs=ELEMENT_WAIT) -> WebDriverWait:
    return WebDriverWait(driver, secs)


def _find(driver, *selectors, timeout=ELEMENT_WAIT, allow_hidden=False):
    """Try multiple selectors (CSS or XPath) in order, find elements, and return the first visible match."""
    end = time.time() + timeout
    while time.time() < end:
        for sel in selectors:
            try:
                if sel.startswith("/") or sel.startswith("./") or sel.startswith("xpath:"):
                    by_type = By.XPATH
                    query = sel.replace("xpath:", "")
                else:
                    by_type = By.CSS_SELECTOR
                    query = sel
                
                elements = driver.find_elements(by_type, query)
                for el in elements:
                    if allow_hidden or el.is_displayed():
                        return el
            except Exception:
                pass
        time.sleep(0.5)
    return None


def _click(driver, element, current_pos=(100, 100)):
    """Human-like move + click on an element."""
    new_pos = human_move_to(driver, element, current_pos)
    element.click()
    micro_delay()
    return new_pos


def _select_dropdown(driver, selector: str, value: str, by_text=True):
    """Select a <select> option by visible text or value."""
    try:
        el = _wait(driver).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
        sel = Select(el)
        if by_text:
            sel.select_by_visible_text(value)
        else:
            sel.select_by_value(value)
        return True
    except Exception:
        return False


def _sound_alert():
    """Play a system beep sequence to alert the user of a booking."""
    try:
        for _ in range(5):
            winsound.Beep(1000, 300)
            time.sleep(0.15)
            winsound.Beep(1500, 300)
            time.sleep(0.15)
    except Exception:
        pass


def _gui_alert(gui_handle, message: str):
    """Thread-safe GUI notification via the dashboard handle."""
    try:
        if gui_handle and hasattr(gui_handle, 'show_booking_alert'):
            gui_handle.root.after(0, gui_handle.show_booking_alert, message)
    except Exception:
        pass


# ── Browser process cleanup ───────────────────────────────────────────────
def _kill_chrome_processes(log=None):
    """
    Force-kill all lingering chromedriver and chrome processes on Windows.
    Called before launching a new browser to prevent WinError 6 handle errors.
    """
    _log = log or (lambda m: None)
    for proc in ["chromedriver.exe", "undetected_chromedriver.exe"]:
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/IM", proc],
                capture_output=True, text=True
            )
            if "SUCCESS" in result.stdout:
                _log(f"🧹 Killed lingering {proc}")
        except Exception:
            pass
    time.sleep(0.5)  # brief pause so OS releases handles


def _safe_quit(driver):
    """Safely quit a Chrome driver, suppressing all cleanup errors."""
    if driver is None:
        return
    try:
        driver.service.stop()
    except Exception:
        pass
    try:
        driver.quit()
    except Exception:
        pass
    try:
        # Force-kill the specific chrome process if still alive
        pid = getattr(driver, 'browser_pid', None)
        if pid:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True)
    except Exception:
        pass

    # Suppress the garbage collector's __del__ deallocator traceback by stubbing quit
    try:
        driver.quit = lambda *args, **kwargs: None
    except Exception:
        pass



def _create_driver(proxy_manager: ProxyManager, log):
    """Create a fully stealthed Chrome driver with optional proxy."""
    # Kill any lingering chrome/chromedriver processes before launching fresh
    _kill_chrome_processes(log)
    proxy_entry = proxy_manager.get_next() if proxy_manager else None

    ext_folder  = None

    if proxy_entry:
        log(f"📡 Using proxy: {proxy_entry.as_server()}")
        if proxy_entry.needs_extension():
            ext_folder = build_proxy_extension(
                proxy_entry.ip, proxy_entry.port,
                proxy_entry.user, proxy_entry.password
            )
            options = get_chrome_options(ext_folder=ext_folder)
        else:
            options = get_chrome_options(proxy_str=proxy_entry.as_server())
    else:
        log("🌐 No proxy — using direct connection")
        options = get_chrome_options()

    log("🤖 Launching stealth Chrome browser...")
    driver = uc.Chrome(options=options, version_main=None, headless=False)
    driver.set_page_load_timeout(PAGE_TIMEOUT)
    driver.maximize_window()

    apply_stealth_patches(driver)
    return driver, proxy_entry


# ── Phase 2: Auto Login ───────────────────────────────────────────────────
def _do_login(driver, config: dict, log) -> bool:
    """
    BLS Italy portal uses a 2-step login:
      Step 1 → Enter Email  → click Verify
      Step 2 → Password field appears → Enter Password → Submit

    Also handles:
      - Stale session "Ready to Leave?" logout prompt
      - CAPTCHA on either step
      - OTP email verification after login
    """
    email_addr = config.get("Email", "")
    password   = config.get("Password", "")

    if not email_addr or not password:
        log("❌ Email/Password missing in testing.txt")
        return False

    log("🔐 Navigating to login page...")
    driver.get(LOGIN_URL)
    human_delay(2.0, 3.5)

    pos = (100, 100)

    # ── Handle stale session logout prompt ──────────────────────────────
    # The site shows "Ready to Leave? / Logout" if a session exists
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "Ready to Leave" in body_text or "Logout" in body_text:
            log("🔓 Stale session detected — clicking Logout to clear it...")
            logout_btn = _find(driver,
                "input[value='Logout']",
                "button[value='Logout']",
                "a[href*='logout' i]",
                "a[href*='signout' i]",
                "input[type='submit'][value*='Logout']",
            )
            if logout_btn:
                pos = _click(driver, logout_btn, pos)
                human_delay(2.0, 3.0)
                log("✅ Logged out old session — reloading login page...")
                driver.get(LOGIN_URL)
                human_delay(2.0, 3.0)
    except Exception:
        pass

    # ──────────────────────────────────────────────────────────────────────
    # STEP 1: Enter Email and click Verify
    # ──────────────────────────────────────────────────────────────────────
    log("📧 Step 1 — Entering email address...")
    email_el = _find(driver,
        "input[type='email']",
        "input[type='text']",
        "input[name='Email']",
        "input[id*='email' i]",
        "input[placeholder*='email' i]",
        "#UserName", "#Email",
    )
    if not email_el:
        log("❌ Email field not found on login page")
        return False

    pos = _click(driver, email_el, pos)
    human_type(email_el, email_addr)
    log(f"✏️ Email entered: {email_addr}")
    human_delay(0.5, 1.0)

    # Solve CAPTCHA if present at step 1
    solver = CaptchaSolver(driver, log_fn=log)
    if solver._has_recaptcha() or solver._find_captcha_image():
        log("🧩 CAPTCHA on step 1 — solving...")
        answer = solver.solve()
        captcha_el = _find(driver,
            "input[id*='captcha' i]", "input[name*='captcha' i]",
            ".captcha-input", "#CaptchaInputText",
        )
        if answer and captcha_el:
            pos = _click(driver, captcha_el, pos)
            human_type(captcha_el, answer)

    # Click Verify / Next button (step 1 submit)
    verify_btn = _find(driver,
        "input[value='Verify']",
        "button[value='Verify']",
        "input[id*='verify' i]",
        "button[id*='verify' i]",
        "input[type='submit']",
        "button[type='submit']",
        "#btnVerify", "#btnNext",
    )
    if not verify_btn:
        log("❌ Verify button not found")
        return False

    pos = _click(driver, verify_btn, pos)
    log("🔘 Email verified — waiting for password field...")
    human_delay(2.0, 3.5)

    # ──────────────────────────────────────────────────────────────────────
    # STEP 2: Password field appears — enter password and submit
    # ──────────────────────────────────────────────────────────────────────
    log("🔑 Step 2 — Entering password...")
    pass_el = _find(driver,
        "input[type='password']",
        "input[name='Password']",
        "input[id*='pass' i]",
        "#Password",
    )
    if not pass_el:
        log("❌ Password field did not appear after email verify")
        return False

    pos = _click(driver, pass_el, pos)
    human_type(pass_el, password)
    log("✏️ Password entered")
    human_delay(0.5, 1.0)

    # Solve CAPTCHA if present at step 2
    if solver._has_recaptcha() or solver._find_captcha_image():
        log("🧩 CAPTCHA on step 2 — solving...")
        answer = solver.solve()
        captcha_el = _find(driver,
            "input[id*='captcha' i]", "input[name*='captcha' i]",
            ".captcha-input", "#CaptchaInputText",
        )
        if not captcha_el and answer:
            # Fallback heuristic: find visible, enabled text input that isn't the email field (doesn't contain '@')
            try:
                inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
                for inp in inputs:
                    if inp.is_displayed() and inp.is_enabled():
                        val = inp.get_attribute("value") or ""
                        if "@" not in val:
                            captcha_el = inp
                            break
            except Exception:
                pass
        
        if answer and captcha_el:
            pos = _click(driver, captcha_el, pos)
            human_type(captcha_el, answer)

    # Click Login / Submit button
    submit_el = _find(driver,
        "input[value='Login']",
        "button[value='Login']",
        "input[type='submit']",
        "button[type='submit']",
        "button[id*='login' i]",
        ".btn-login", "#btnLogin", "#btnSubmit",
    )
    if not submit_el:
        log("❌ Login submit button not found")
        return False

    pos = _click(driver, submit_el, pos)
    log("🔘 Login submitted — waiting for response...")
    human_delay(3.0, 5.0)

    # ── Check for OTP verification step ─────────────────────────────────
    if _is_otp_page(driver):
        log("📧 OTP verification page detected — reading email...")
        success = _handle_otp(driver, config, log, pos)
        if not success:
            log("❌ OTP verification failed")
            return False

    # ── Verify we're logged in ────────────────────────────────────────────
    if _is_logged_in(driver):
        log("✅ Login successful!")
        return True

    log("⚠️ Login may have failed — checking page content...")
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        if any(word in body_text for word in ["invalid", "incorrect", "failed", "error", "wrong"]):
            log("❌ Login error detected on page")
            return False
    except Exception:
        pass

    human_delay(2.0, 3.0)
    return _is_logged_in(driver)


def _is_otp_page(driver) -> bool:
    """Check if the current page is asking for an OTP."""
    try:
        page = driver.page_source.lower()
        return any(word in page for word in [
            "one-time", "otp", "verification code", "verify your email",
            "enter code", "6-digit", "security code"
        ])
    except Exception:
        return False


def _handle_otp(driver, config: dict, log, pos=(100, 100)) -> bool:
    """Read OTP from Gmail and enter it on the verification page."""
    gmail_user = config.get("Email", "")
    gmail_pass = config.get("Gmail App Password", "")

    if not gmail_pass:
        log("⚠️ Gmail App Password not set — requesting manual OTP entry")
        otp = EmailReader._manual_fallback(None, "Enter the OTP sent to your email:")
    else:
        reader = EmailReader(gmail_user, gmail_pass, log_fn=log)
        otp = reader.wait_for_otp(timeout=120, poll_interval=5)

    if not otp:
        log("❌ No OTP obtained")
        return False

    # Handle verification link (click it directly)
    if otp.startswith("http"):
        log(f"🔗 Opening verification link...")
        driver.get(otp)
        human_delay(2.0, 4.0)
        return True

    # Find OTP input field
    otp_el = _find(driver,
        "input[type='text']",
        "input[id*='otp' i]",
        "input[name*='otp' i]",
        "input[placeholder*='code' i]",
        "input[placeholder*='otp' i]",
        ".otp-input",
    )
    if otp_el:
        pos = _click(driver, otp_el, pos)
        human_type(otp_el, otp)
        log(f"✅ OTP entered: {otp}")

        # Submit OTP form
        submit = _find(driver,
            "button[type='submit']",
            "input[type='submit']",
            "#btnVerify",
            "button[id*='verify' i]",
            "button[id*='submit' i]",
        )
        if submit:
            _click(driver, submit, pos)
            human_delay(2.0, 3.5)

        return True

    log("❌ OTP input field not found on page")
    return False


def _is_logged_in(driver) -> bool:
    """Heuristic check — are we past the login page?"""
    try:
        url = driver.current_url.lower()
        parsed = urlparse(url)
        path = parsed.path

        # Explicitly not logged in if on the login page
        if "login" in path:
            return False

        # Logged in if we're on dashboard, appointment, or profile pages (checking path only)
        logged_in_hints = ["dashboard", "appointment", "newappointment",
                           "profile", "myaccount", "menu"]
        if any(hint in path for hint in logged_in_hints):
            return True

        # Also check for visible logout text on the page
        body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "logout" in body_text or "sign out" in body_text or "sign-out" in body_text:
            return True
    except Exception:
        pass
    return False


# ── Phase 3: Navigate and Fill Appointment Form ───────────────────────────
def _fill_appointment_form(driver, config: dict, image_path: str, log) -> bool:
    """
    Navigate to new appointment page and fill all fields:
    Center, Service Type, Service Subtype, Category, Date, Passport Image.
    """
    log("📋 Navigating to new appointment page...")
    driver.get(APPT_URL)
    human_delay(2.0, 4.0)

    pos = (100, 100)

    center       = config.get("Center", "")
    service_type = config.get("Service Type", "")
    service_sub  = config.get("Service Subtype", "")
    category     = config.get("Category", "")

    # ── Select Center ─────────────────────────────────────────────────────
    if center:
        log(f"🏢 Selecting center: {center}")
        if not _select_dropdown(driver,
            "select[id*='center' i], select[name*='center' i], #ddlCenter, #Center",
            center):
            log(f"⚠️ Could not auto-select center '{center}' — may need manual check")
        human_delay(1.0, 2.0)

    # ── Select Service Type ───────────────────────────────────────────────
    if service_type:
        log(f"📝 Selecting service type: {service_type}")
        _select_dropdown(driver,
            "select[id*='service' i], select[name*='service' i], #ddlServiceType",
            service_type)
        human_delay(1.0, 2.0)

    # ── Select Service Subtype ────────────────────────────────────────────
    if service_sub:
        log(f"📝 Selecting service subtype: {service_sub}")
        _select_dropdown(driver,
            "select[id*='subtype' i], select[id*='sub' i], #ddlSubType, #ddlVisaType",
            service_sub)
        human_delay(1.0, 2.0)

    # ── Select Category ───────────────────────────────────────────────────
    if category:
        log(f"📝 Selecting category: {category}")
        _select_dropdown(driver,
            "select[id*='category' i], #ddlCategory, #Category",
            category)
        human_delay(1.0, 2.0)

    # ── Upload Passport Photo ─────────────────────────────────────────────
    if image_path and os.path.exists(image_path):
        log("🖼️ Processing and uploading passport photo...")
        try:
            processed_path = get_processed_image_path(image_path, log_fn=log)
            upload_el = _find(driver,
                "input[type='file']",
                "input[accept*='image' i]",
                "input[id*='photo' i]",
                "input[id*='image' i]",
                "input[name*='photo' i]",
                "#fileUpload",
                allow_hidden=True
            )
            if upload_el:
                upload_el.send_keys(os.path.abspath(processed_path))
                log(f"✅ Passport photo uploaded: {processed_path}")
                human_delay(1.0, 2.0)
            else:
                log("⚠️ File upload input not found on form")
        except Exception as e:
            log(f"❌ Image upload error: {e}")

    return True


# ── Phase 4: Check Available Slots ────────────────────────────────────────
def _check_available_slots(driver, config: dict, log) -> Optional[str]:
    """
    Check for appointment slots matching the preferred date.
    Returns the slot element text if found, else None.
    """
    preferred_date = config.get("Preferred Date", "")
    log(f"🗓️ Checking slots for preferred date: {preferred_date}")

    # Look for date picker / calendar
    try:
        # Try clicking the date input
        date_el = _find(driver,
            "input[type='date']",
            "input[id*='date' i]",
            "input[name*='date' i]",
            ".datepicker-input",
            "#AppDate",
            "#PreferredDate",
        )
        if date_el:
            date_el.click()
            human_delay(0.5, 1.5)

        # Look for available (not disabled/greyed) date slots
        available = driver.find_elements(By.CSS_SELECTOR,
            ".day:not(.disabled):not(.old):not(.new), "
            ".calendar-day.available, "
            ".slot-available, "
            "td.day:not(.disabled), "
            ".fc-day:not(.fc-past):not(.fc-disabled)"
        )

        if available:
            log(f"🟢 Found {len(available)} available slot(s)!")
            for slot in available:
                slot_text = slot.text.strip()
                if slot_text and (preferred_date in slot_text or _date_matches(slot_text, preferred_date)):
                    log(f"🎯 Target date slot found: {slot_text}")
                    return slot_text
            # Return first available slot if exact date not found
            log(f"📅 No exact date match — {len(available)} other slots available")
            return available[0].text.strip()

        # Also check for slot buttons
        slot_buttons = driver.find_elements(By.CSS_SELECTOR,
            "button.slot, .time-slot:not(.taken), .appointment-slot.open"
        )
        if slot_buttons:
            log(f"🟢 Found {len(slot_buttons)} time slot(s)!")
            return slot_buttons[0].text.strip()

    except Exception as e:
        log(f"⚠️ Slot detection error: {e}")

    return None


def _date_matches(slot_text: str, preferred: str) -> bool:
    """Loose date match — checks if the preferred date numbers appear in slot text."""
    try:
        # Extract numbers from both
        slot_nums = re.findall(r'\d+', slot_text)
        pref_nums = re.findall(r'\d+', preferred)
        # Check if month and day numbers match
        return any(n in slot_nums for n in pref_nums)
    except Exception:
        return False


# ── Phase 5: Book Slot ────────────────────────────────────────────────────
def _book_slot(driver, config: dict, log, gui_handle) -> bool:
    """
    Click the available slot, confirm booking, handle any final CAPTCHA,
    then alert the user via sound + GUI popup.
    """
    preferred_date = config.get("Preferred Date", "")
    log("🎯 Attempting to book the slot...")

    pos = (100, 100)

    # Click the first available slot
    slot_el = None
    for sel in [
        ".day:not(.disabled)", ".slot-available", ".fc-day:not(.fc-past)",
        "button.slot", ".time-slot:not(.taken)", ".appointment-slot.open"
    ]:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if els:
                slot_el = els[0]
                break
        except Exception:
            continue

    if slot_el:
        pos = _click(driver, slot_el, pos)
        log(f"✅ Slot clicked: {slot_el.text.strip() or 'date slot'}")
        human_delay(1.5, 3.0)

    # Solve any CAPTCHA on booking confirmation page
    solver = CaptchaSolver(driver, log_fn=log)
    if solver._has_recaptcha() or solver._find_captcha_image():
        log("🧩 CAPTCHA on booking page — solving...")
        answer = solver.solve()
        captcha_input = _find(driver,
            "input[id*='captcha' i]",
            "input[name*='captcha' i]",
        )
        if not captcha_input and answer:
            try:
                inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
                for inp in inputs:
                    if inp.is_displayed() and inp.is_enabled():
                        val = inp.get_attribute("value") or ""
                        if "@" not in val:
                            captcha_input = inp
                            break
            except Exception:
                pass

        if answer and captcha_input:
            pos = _click(driver, captcha_input, pos)
            human_type(captcha_input, answer)

    # Click Book / Confirm / Proceed button
    confirm_el = _find(driver,
        "button[id*='book' i]",
        "button[id*='confirm' i]",
        "button[id*='proceed' i]",
        "input[type='submit']",
        ".btn-book",
        ".btn-confirm",
        "#btnBookAppointment",
        "#btnConfirm",
    )
    if confirm_el:
        pos = _click(driver, confirm_el, pos)
        log("✅ Booking confirmation submitted!")
        human_delay(3.0, 5.0)

    # Check for success confirmation
    success = False
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        success_words = ["booking confirmed", "appointment booked", "success",
                         "confirmation", "reference number", "appointment id"]
        success = any(w in page_text for w in success_words)
    except Exception:
        pass

    if success:
        ref_no = ""
        try:
            # Try to extract reference/booking number
            ref_match = re.search(r'(?:reference|booking|appointment)\s*(?:number|no|id)[:\s]+([A-Z0-9\-]+)',
                                  driver.find_element(By.TAG_NAME, "body").text,
                                  re.IGNORECASE)
            if ref_match:
                ref_no = ref_match.group(1)
        except Exception:
            pass

        msg = (
            f"🎉 APPOINTMENT BOOKED SUCCESSFULLY!\n"
            f"   Date : {preferred_date}\n"
            f"   Center: {config.get('Center', 'N/A')}\n"
            f"   Ref#  : {ref_no or 'See browser'}"
        )
        log("=" * 55)
        log(msg)
        log("=" * 55)

        _sound_alert()
        _gui_alert(gui_handle, msg)
        return True

    log("⚠️ Booking result unclear — check browser window")
    return False


# ── Main Engine Loop ──────────────────────────────────────────────────────
def launch_bls_automation(gui_handle, config_data: dict, image_path: str):
    """
    Main entry point called by the dashboard START button (runs in its own thread).

    Flow per cycle:
        1. Create stealthed browser (with proxy)
        2. Warm up session
        3. Auto Login → CAPTCHA → OTP verification
        4. Fill appointment form + upload photo
        5. Check available slots
        6. If slot found → Book → Alert → Stop
        7. If no slot → wait loop delay → retry
        8. On HTTP 429 or error → rotate proxy → restart browser
    """
    log = gui_handle.log

    live_state["config"]     = config_data
    live_state["image_path"] = image_path
    live_state["stop_flag"]  = False

    proxy_manager = ProxyManager(config_data, log_fn=log)

    loop_count     = 0
    restart_needed = False
    driver         = None
    current_proxy  = None

    try:
        while not live_state["stop_flag"]:

            # ── Pause check ───────────────────────────────────────────
            if live_state["pause_flag"]:
                log("⏸️ Bot paused — waiting for Resume...")
                time.sleep(1.0)
                continue

            config = live_state["config"]
            img    = live_state["image_path"]

            # Update target portal URLs dynamically (supports hot-reload from config)
            global BASE_URL, LOGIN_URL, APPT_URL
            portal_url = config.get("Visa Portal URL", "https://appointment.theitalyvisa.com").rstrip("/")
            if BASE_URL != portal_url:
                BASE_URL = portal_url
                LOGIN_URL = f"{BASE_URL}/Global/Account/LogIn"
                APPT_URL = f"{BASE_URL}/Global/appointment/newappointment"
                log(f"🌐 Target portal URL updated to: {BASE_URL}")

            loop_count += 1
            log(f"\n{'─' * 50}")
            log(f"🔁 Loop #{loop_count}  |  {datetime.now().strftime('%H:%M:%S')}")
            log(f"   Center: {config.get('Center', '?')}  |  Date: {config.get('Preferred Date', '?')}")
            if gui_handle:
                gui_handle.update_stats(loop_count, current_proxy)

            # ── (Re)launch browser ────────────────────────────────────
            if driver is None or restart_needed:
                if driver:
                    _safe_quit(driver)
                    driver = None

                try:
                    driver, current_proxy = _create_driver(proxy_manager, log)
                    warm_up_session(driver, BASE_URL, log)
                    restart_needed = False
                except Exception as e:
                    log(f"❌ Browser launch failed: {e}")
                    _safe_quit(driver)
                    driver = None
                    time.sleep(10)
                    continue

            try:
                # ── Login ─────────────────────────────────────────────
                if not _is_logged_in(driver):
                    if not _do_login(driver, config, log):
                        log("❌ Login failed — retrying with new session...")
                        restart_needed = True
                        time.sleep(5)
                        continue
                else:
                    log("🔓 Already logged in — skipping login step")

                # ── Fill form ─────────────────────────────────────────
                _fill_appointment_form(driver, config, img, log)

                # ── Check slots ───────────────────────────────────────
                slot = _check_available_slots(driver, config, log)

                if slot:
                    log(f"🟢 SLOT AVAILABLE: {slot}")
                    booked = _book_slot(driver, config, log, gui_handle)
                    if booked:
                        log("🏆 Bot mission complete — stopping")
                        live_state["stop_flag"] = True
                        if gui_handle:
                            gui_handle.root.after(0, gui_handle.on_bot_completed)
                        break
                    else:
                        log("⚠️ Booking attempt failed — will retry")
                else:
                    log("🔴 No available slots found this cycle")

            except WebDriverException as e:
                err = str(e).lower()
                log(f"🔥 Browser error: {e}")
                if "429" in err or "rate limit" in err:
                    log("🚫 Rate limited — rotating proxy and restarting browser")
                    if current_proxy:
                        proxy_manager.mark_bad(current_proxy)
                restart_needed = True
                continue

            except Exception as e:
                log(f"❌ Unexpected error in loop: {e}")
                restart_needed = True
                continue

            # ── Wait between cycles ───────────────────────────────────
            if not live_state["stop_flag"]:
                low  = float(config.get("Loop Delay Min", 4))
                high = float(config.get("Loop Delay Max", 8))
                wait = random.uniform(low, high)
                log(f"⏱️ Waiting {wait:.1f}s before next cycle...")
                time.sleep(wait)

    except Exception as e:
        log(f"💥 Fatal engine error: {e}")
    finally:
        _safe_quit(driver)
        log("🛑 Bot engine stopped.")
        if gui_handle:
            gui_handle.root.after(0, gui_handle.on_bot_stopped)