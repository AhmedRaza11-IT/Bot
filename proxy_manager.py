"""
proxy_manager.py
═══════════════════════════════════════════════════════════════════
Hybrid Proxy Manager — Paid + Free Proxy Pool
═══════════════════════════════════════════════════════════════════
Tier 1 → User-provided proxies from testing.txt (paid/private)
Tier 2 → Free public proxy pool (auto-fetched & validated)

Format in testing.txt:
    Proxy List: IP:PORT:USER:PASS, IP:PORT, IP:PORT:USER:PASS

If no paid proxies are configured, falls back to Tier 2 automatically.
Proxies rotate on each bot cycle or on HTTP 429 / timeout errors.
"""

import itertools
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List

import requests

# ── Optional: free-proxy library ─────────────────────────────────────────
try:
    from fp.fp import FreeProxy
    _HAS_FREE_PROXY = True
except ImportError:
    _HAS_FREE_PROXY = False

# ── Constants ─────────────────────────────────────────────────────────────
_VALIDATE_URL    = "https://httpbin.org/ip"
_VALIDATE_TIMEOUT = 6
_MIN_POOL_SIZE   = 4
_POOL_REFRESH_SEC = 10 * 60   # refresh free proxies every 10 minutes
_EXT_DIR         = os.path.abspath("./proxy_auth_ext")


# ── Chrome Extension Generator (for authenticated proxy tunnels) ──────────
def build_proxy_extension(ip: str, port: str, user: str = "", password: str = "") -> str:
    """
    Write a Manifest V3 Chrome extension to disk that handles
    authenticated proxy login natively. Returns the extension folder path.
    """
    os.makedirs(_EXT_DIR, exist_ok=True)

    manifest = """{
    "version": "1.0.0",
    "manifest_version": 3,
    "name": "BLS Proxy Auth Handler",
    "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "webRequest", "webRequestAuthProvider"],
    "host_permissions": ["<all_urls>"],
    "background": { "service_worker": "background.js" }
}"""

    if user and password:
        auth_block = f"""
    chrome.webRequest.onAuthRequired.addListener(
        function(details) {{
            return {{ authCredentials: {{ username: "{user}", password: "{password}" }} }};
        }},
        {{ urls: ["<all_urls>"] }},
        ["asyncBlocking"]
    );"""
    else:
        auth_block = ""

    background = f"""chrome.proxy.settings.set({{
    value: {{
        mode: "fixed_servers",
        rules: {{
            singleProxy: {{ scheme: "http", host: "{ip}", port: parseInt({port}) }},
            bypassList: ["localhost", "127.0.0.1"]
        }}
    }},
    scope: "regular"
}}, function() {{}});
{auth_block}"""

    with open(os.path.join(_EXT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        f.write(manifest)
    with open(os.path.join(_EXT_DIR, "background.js"), "w", encoding="utf-8") as f:
        f.write(background)

    return _EXT_DIR


class ProxyEntry:
    """Represents a single proxy with optional credentials."""

    def __init__(self, raw: str):
        """
        Parse raw string. Accepted formats:
            IP:PORT
            IP:PORT:USER:PASS
            http://IP:PORT
            http://USER:PASS@IP:PORT
        """
        self.ip = self.port = self.user = self.password = ""
        self._raw = raw.strip()
        self._parse()

    def _parse(self):
        raw = self._raw.replace("http://", "").replace("https://", "")

        # Format: USER:PASS@IP:PORT
        if "@" in raw:
            creds, addr = raw.split("@", 1)
            parts = creds.split(":", 1)
            self.user = parts[0] if len(parts) > 0 else ""
            self.password = parts[1] if len(parts) > 1 else ""
            addr_parts = addr.rsplit(":", 1)
            self.ip   = addr_parts[0]
            self.port = addr_parts[1] if len(addr_parts) > 1 else "80"
        else:
            parts = raw.split(":")
            if len(parts) == 2:
                self.ip, self.port = parts
            elif len(parts) == 4:
                self.ip, self.port, self.user, self.password = parts
            elif len(parts) >= 2:
                self.ip   = parts[0]
                self.port = parts[1]

    def as_url(self) -> str:
        """Returns proxy as http://user:pass@ip:port or http://ip:port"""
        if self.user and self.password:
            return f"http://{self.user}:{self.password}@{self.ip}:{self.port}"
        return f"http://{self.ip}:{self.port}"

    def as_server(self) -> str:
        """Returns IP:PORT for --proxy-server Chrome flag (no auth prefix)."""
        return f"{self.ip}:{self.port}"

    def needs_extension(self) -> bool:
        """True when proxy requires auth (must use Chrome extension)."""
        return bool(self.user and self.password)

    def __repr__(self):
        if self.user:
            return f"<Proxy {self.ip}:{self.port} [{self.user}]>"
        return f"<Proxy {self.ip}:{self.port}>"


def _validate_proxy(entry: ProxyEntry) -> Optional[ProxyEntry]:
    """Quick live-check of a proxy. Returns entry if working, else None."""
    try:
        proxies = {"http": entry.as_url(), "https": entry.as_url()}
        r = requests.get(_VALIDATE_URL, proxies=proxies, timeout=_VALIDATE_TIMEOUT)
        if r.status_code == 200:
            return entry
    except Exception:
        pass
    return None


# ── Fetch free proxies from public sources ────────────────────────────────
def _fetch_free_proxies(n=30) -> List["ProxyEntry"]:
    """
    Fetch free proxy strings from multiple public sources and return
    a list of ProxyEntry objects.
    """
    raw_list = []

    # Source 1: free-proxy library
    if _HAS_FREE_PROXY:
        try:
            for _ in range(n):
                p = FreeProxy(timeout=1.5, rand=True, anonym=True).get()
                if p:
                    raw_list.append(p.replace("http://", "").replace("https://", ""))
        except Exception:
            pass

    # Source 2: proxy-list.download API
    try:
        r = requests.get(
            "https://www.proxy-list.download/api/v1/get?type=https",
            timeout=8
        )
        if r.status_code == 200:
            raw_list.extend(r.text.strip().splitlines())
    except Exception:
        pass

    # Source 3: proxylist.geonode.com
    try:
        r = requests.get(
            "https://proxylist.geonode.com/api/proxy-list?limit=50&sort_by=lastChecked&sort_type=desc&protocols=http",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if r.status_code == 200:
            data = r.json().get("data", [])
            for p in data:
                raw_list.append(f"{p['ip']}:{p['port']}")
    except Exception:
        pass

    return [ProxyEntry(r) for r in set(raw_list) if r.strip()]


class ProxyManager:
    """
    Manages a rotating pool of proxies.

    Priority:
        1. User-provided proxies (from config) — Tier 1
        2. Free public proxies — Tier 2 (auto-fetched when Tier 1 empty)

    Usage:
        pm = ProxyManager(config_data)
        entry = pm.get_next()
        pm.mark_bad(entry)   # call on 429 / timeout
    """

    def __init__(self, config_data: dict, log_fn=None):
        self._log   = log_fn or print
        self._lock  = threading.Lock()
        self._pool: List[ProxyEntry] = []
        self._cycle = None
        self._last_refresh = 0.0
        self._enabled = config_data.get("IP Rotator", "false").strip().lower() == "true"
        self._user_proxies = self._parse_user_proxies(config_data)

        if self._enabled:
            # Build pool in background so bot starts instantly
            threading.Thread(target=self._build_pool, daemon=True,
                             name="ProxyPoolBuilder").start()

    def _parse_user_proxies(self, config: dict) -> List[ProxyEntry]:
        """Parse 'Proxy List' key from testing.txt config."""
        raw = config.get("Proxy List", "").strip()
        if not raw:
            # Fallback: legacy single 'Proxy' key
            raw = config.get("Proxy", "").strip()
        if not raw:
            return []
        return [ProxyEntry(p.strip()) for p in raw.split(",") if p.strip()]

    def _build_pool(self):
        """Build/refresh the full proxy pool."""
        self._log("🔄 Building proxy pool...")
        pool: List[ProxyEntry] = []

        # Tier 1: validate user proxies
        if self._user_proxies:
            self._log(f"📋 Validating {len(self._user_proxies)} user-provided proxies...")
            with ThreadPoolExecutor(max_workers=8) as ex:
                futures = {ex.submit(_validate_proxy, p): p for p in self._user_proxies}
                for fut in as_completed(futures):
                    result = fut.result()
                    if result:
                        pool.append(result)
            self._log(f"✅ {len(pool)}/{len(self._user_proxies)} user proxies OK")

        # Tier 2: free proxies if pool still thin
        if len(pool) < _MIN_POOL_SIZE:
            self._log("🌐 Fetching free public proxies...")
            free_raw = _fetch_free_proxies(n=40)
            self._log(f"🔍 Validating {len(free_raw)} free proxy candidates...")
            with ThreadPoolExecutor(max_workers=12) as ex:
                futures = {ex.submit(_validate_proxy, p): p for p in free_raw}
                for fut in as_completed(futures):
                    result = fut.result()
                    if result:
                        pool.append(result)

        # Deduplicate and rebuild cycle — lock is NOT held during fetch/validate above
        deduped = list({p.as_server(): p for p in pool}.values())
        with self._lock:
            self._pool  = deduped
            self._cycle = itertools.cycle(self._pool) if self._pool else None
            self._last_refresh = time.time()

        self._log(f"✅ Proxy pool ready: {len(deduped)} working proxies")

    def _maybe_refresh(self):
        """Refresh pool if it's been more than _POOL_REFRESH_SEC."""
        if time.time() - self._last_refresh > _POOL_REFRESH_SEC:
            t = threading.Thread(target=self._build_pool, daemon=True)
            t.start()

    def get_next(self) -> Optional[ProxyEntry]:
        """
        Return the next proxy in the round-robin cycle.
        Returns None if IP rotation is disabled or pool is empty.
        """
        if not self._enabled:
            return None

        self._maybe_refresh()

        with self._lock:
            if not self._pool or self._cycle is None:
                return None
            return next(self._cycle)

    def mark_bad(self, entry: ProxyEntry):
        """Remove a known-bad proxy from the pool."""
        with self._lock:
            if entry in self._pool:
                self._pool.remove(entry)
                self._log(f"🚫 Removed bad proxy: {entry.as_server()}")
            # Rebuild cycle iterator so it doesn't reference removed entry
            if self._pool:
                self._cycle = itertools.cycle(self._pool)
            else:
                self._cycle = None
        # Refresh pool in background if running low
        if self.pool_size < _MIN_POOL_SIZE:
            threading.Thread(target=self._build_pool, daemon=True).start()

    def get_random(self) -> Optional[ProxyEntry]:
        """Return a random proxy from the current pool."""
        if not self._enabled:
            return None
        with self._lock:
            return random.choice(self._pool) if self._pool else None

    @property
    def pool_size(self) -> int:
        with self._lock:
            return len(self._pool)

    @property
    def is_enabled(self) -> bool:
        return self._enabled
