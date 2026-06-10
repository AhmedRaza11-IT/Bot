"""
stealth_engine.py
═══════════════════════════════════════════════════════════════════
8-Layer Anti-Bot Detection Bypass Engine for BLS Italy Bot
═══════════════════════════════════════════════════════════════════
L1 - Driver Patching       (undetected-chromedriver)
L2 - Chrome Flags          (disable automation indicators)
L3 - JS Fingerprint Spoof  (CDP injections at page load)
L4 - User Agent Rotation   (pool of real Windows Chrome UAs)
L5 - Viewport Noise        (random size variations)
L6 - Human Mouse Timing    (Bezier curves, variable speed)
L7 - Gaussian Delays       (natural timing distribution)
L8 - Cookie Warming        (session history pre-build)
"""

import random
import time
import undetected_chromedriver as uc

# ── Layer 4: Real User Agent Pool ─────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64)  AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.160 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; WOW64)      AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
]

# ── Layer 3: JS Fingerprint Patch (injected on every new document) ─────────
_JS_STEALTH_PATCH = """
    // L3a: Remove webdriver flag completely
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });

    // L3b: Spoof plugins array (empty = bot giveaway)
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            return [
                { name: 'Chrome PDF Plugin',     filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer',     filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client',          filename: 'internal-nacl-plugin' },
            ];
        },
        configurable: true
    });

    // L3c: Spoof languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en', 'ur'],
        configurable: true
    });

    // L3d: Patch permissions.query (notification permission check)
    const _origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : _origQuery(parameters)
    );

    // L3e: Stub chrome.runtime so it exists
    if (!window.chrome) window.chrome = {};
    if (!window.chrome.runtime) window.chrome.runtime = {
        connect: () => {},
        sendMessage: () => {}
    };

    // L3f: Spoof connection type
    Object.defineProperty(navigator, 'connection', {
        get: () => ({ rtt: 50, downlink: 10, effectiveType: '4g', saveData: false }),
        configurable: true
    });

    // L3g: Spoof hardwareConcurrency (real CPU cores count)
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => 8,
        configurable: true
    });

    // L3h: Spoof deviceMemory
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => 8,
        configurable: true
    });

    // L3i: Remove headless traces from navigator.userAgent
    const _origUA = navigator.userAgent;
    if (_origUA.includes('Headless')) {
        Object.defineProperty(navigator, 'userAgent', {
            get: () => _origUA.replace('HeadlessChrome', 'Chrome'),
            configurable: true
        });
    }
"""


def get_random_ua():
    """Return a random real Windows Chrome User-Agent string."""
    return random.choice(USER_AGENTS)


def get_chrome_options(proxy_str=None, user_agent=None, ext_folder=None):
    """
    Build a fully stealthed ChromeOptions object.

    Args:
        proxy_str  : optional 'IP:PORT' string (no auth prefix)
        user_agent : optional UA string override
        ext_folder : optional path to a Chrome extension folder to load

    Returns:
        uc.ChromeOptions
    """
    options = uc.ChromeOptions()

    # ── L2: Core anti-detection Chrome flags ─────────────────────────────
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-notifications")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--allow-running-insecure-content")
    options.add_argument("--lang=en-US")
    if user_agent:
        options.add_argument(f"--user-agent={user_agent}")

    # ── L5: Random viewport (noise to prevent canvas fingerprinting) ──────
    width  = random.choice([1280, 1366, 1440, 1536, 1920]) + random.randint(-15, 15)
    height = random.choice([720, 768, 800, 900, 1080])     + random.randint(-15, 15)
    options.add_argument(f"--window-size={width},{height}")

    # ── Proxy (unauthenticated — auth proxies use extension instead) ──────
    if proxy_str:
        clean = proxy_str.replace("http://", "").replace("https://", "")
        options.add_argument(f"--proxy-server={clean}")

    # ── Extension (for authenticated proxies with user:pass) ──────────────
    if ext_folder:
        options.add_argument(f"--load-extension={ext_folder}")

    return options


def apply_stealth_patches(driver):
    """
    Inject L3 JS fingerprint patches via Chrome DevTools Protocol.
    Call ONCE after driver creation — runs before every page load.
    """
    # JS fingerprint patches on every new document
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": _JS_STEALTH_PATCH}
    )

    # Note: Global Network.setExtraHTTPHeaders is omitted here because overriding Accept and Sec-Fetch-* 
    # headers globally blocks subresources (CSS, JS, images, fonts) from loading correctly (raw UI issue).
    # Chrome's native headers are context-aware and correct.


    # Also apply selenium-stealth if installed (canvas/WebGL spoofing)
    try:
        from selenium_stealth import stealth
        stealth(
            driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
    except ImportError:
        pass


# ── L7: Gaussian-distributed human delays ─────────────────────────────────
def human_delay(low=1.0, high=3.5):
    """Sleep for a Gaussian-distributed duration between low and high."""
    mean = (low + high) / 2
    std  = (high - low) / 5
    duration = max(low, min(high, random.gauss(mean, std)))
    time.sleep(duration)


def micro_delay():
    """Very short delay for between keystrokes / micro-actions."""
    time.sleep(random.uniform(0.03, 0.18))


# ── L6: Bezier curve mouse movement ──────────────────────────────────────
def _bezier_points(start, end, n=55):
    """Generate n points along a cubic Bezier curve from start to end."""
    sx, sy = start
    ex, ey = end
    cp1 = (sx + random.randint(-120, 120), sy + random.randint(-90, 90))
    cp2 = (ex + random.randint(-120, 120), ey + random.randint(-90, 90))
    pts = []
    for i in range(n):
        t = i / (n - 1)
        x = ((1-t)**3*sx + 3*(1-t)**2*t*cp1[0] + 3*(1-t)*t**2*cp2[0] + t**3*ex)
        y = ((1-t)**3*sy + 3*(1-t)**2*t*cp1[1] + 3*(1-t)*t**2*cp2[1] + t**3*ey)
        pts.append((int(x), int(y)))
    return pts


def human_move_to(driver, element, current_pos=(100, 100)):
    """
    Move the mouse to an element along a natural Bezier curve.

    Returns:
        (x, y) tuple of the final cursor position (element center)
    """
    from selenium.webdriver.common.action_chains import ActionChains

    loc  = element.location
    size = element.size
    tx   = loc['x'] + size['width']  // 2
    ty   = loc['y'] + size['height'] // 2

    try:
        points = _bezier_points(current_pos, (tx, ty))
        actions = ActionChains(driver)
        px, py  = current_pos

        for (qx, qy) in points:
            dx, dy = qx - px, qy - py
            if dx == 0 and dy == 0:
                continue
            actions.move_by_offset(dx, dy)
            px, py = qx, qy

        actions.perform()

        # Slight final jitter before click
        jitter = ActionChains(driver)
        jitter.move_by_offset(random.randint(-2, 2), random.randint(-2, 2)).perform()
        time.sleep(random.uniform(0.08, 0.25))
    except Exception:
        # Fallback to standard move_to_element
        try:
            ActionChains(driver).move_to_element(element).perform()
        except Exception:
            pass
            
    return (tx, ty)


def human_type(element, text):
    """
    Type text into an element with human-like inter-key delays
    and occasional simulated typo + backspace corrections.
    """
    from selenium.webdriver.common.keys import Keys
    element.clear()
    time.sleep(random.uniform(0.1, 0.3))

    for char in text:
        # 2% chance of a typo + correction
        if random.random() < 0.02 and char.isalpha():
            typo = random.choice("qwertyuioplkjhgfdsazxcvbnm")
            element.send_keys(typo)
            time.sleep(random.uniform(0.1, 0.35))
            element.send_keys(Keys.BACKSPACE)
            time.sleep(random.uniform(0.05, 0.15))
        element.send_keys(char)
        time.sleep(random.uniform(0.04, 0.22))


def human_scroll(driver, direction="down"):
    """Scroll the page naturally by a random amount."""
    amount = random.randint(150, 500) * (1 if direction == "down" else -1)
    driver.execute_script(
        f"window.scrollBy({{top: {amount}, behavior: 'smooth'}});"
    )
    time.sleep(random.uniform(0.4, 1.2))


# ── L8: Cookie Warming ───────────────────────────────────────────────────────
BLS_BASE_DOMAIN = "https://appointment.theitalyvisa.com"


def warm_up_session(driver, base_url=None, log_fn=None):
    """
    Multi-step warm-up to build a real browsing session:
      1. Visit Google (establishes a clean browsing history)
      2. Visit the BLS root domain (sets cookies, passes bot checks)
      3. Only then navigate to the login page
    This prevents the 403 Forbidden that happens on cold direct access.
    """
    if callable(base_url):
        log_fn = base_url
        base_url = None

    _log = log_fn or print
    target_domain = base_url or BLS_BASE_DOMAIN

    # Step 1: Google warm-up
    try:
        _log("🌡️ Warming session on Google...")
        driver.get("https://www.google.com")
        human_delay(2.0, 3.5)
        human_scroll(driver)
        human_delay(1.0, 2.0)
    except Exception as e:
        _log(f"⚠️ Google warm-up skipped: {e}")

    # Step 2: Visit BLS root domain to get cookies before login page
    try:
        _log(f"🌐 Visiting BLS domain root ({target_domain}) for cookie handshake...")
        driver.get(target_domain)
        human_delay(2.5, 4.0)
        human_scroll(driver)
        human_delay(1.0, 2.0)
    except Exception as e:
        _log(f"⚠️ BLS domain warm-up skipped: {e}")

