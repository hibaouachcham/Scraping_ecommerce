"""
Gestionnaire Playwright partagé — UN seul sync_playwright() pour tout le process.

Deux contextes séparés :
  - Contexte WB         : locale ru-RU, timezone Moscow
  - Contexte TD/Daraz   : locale en-US

Utilisation :
  from scrapers import playwright_manager as pm
  page = pm.get_page()       # Trendyol / Daraz
  page = pm.get_wb_page()    # Wildberries
"""
import time
import random

# ---------------------------------------------------------------------------
# Instance Playwright unique (évite le conflit asyncio loop)
# ---------------------------------------------------------------------------
_pw_instance = None
_pw_browser  = None

# Contexte Trendyol / Daraz
_td_context = None
_td_page    = None

# Contexte Wildberries
_wb_context      = None
_wb_page         = None
_wb_initialized  = False   # homepage WB déjà visitée ?


def _ensure_browser():
    """Lance le navigateur Chrome s'il n'est pas encore ouvert."""
    global _pw_instance, _pw_browser

    if _pw_browser is not None:
        try:
            # Vérification rapide : le browser est-il encore vivant ?
            _ = _pw_browser.is_connected()
            return
        except Exception:
            _pw_browser = None

    from playwright.sync_api import sync_playwright

    if _pw_instance is None:
        _pw_instance = sync_playwright().start()

    _pw_browser = _pw_instance.chromium.launch(
        headless=False,
        channel="chrome",
        args=["--disable-blink-features=AutomationControlled"],
    )


# ---------------------------------------------------------------------------
# Contexte Trendyol / Daraz  (en-US)
# ---------------------------------------------------------------------------
def get_page():
    """Retourne la page Playwright pour Trendyol/Daraz (en-US), la crée si besoin."""
    global _td_context, _td_page

    _ensure_browser()

    if _td_page is not None:
        try:
            _ = _td_page.url
            return _td_page
        except Exception:
            _td_page = None
            _td_context = None

    _td_context = _pw_browser.new_context(
        locale="en-US",
        viewport={"width": 1366, "height": 768},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    )
    _td_page = _td_context.new_page()
    _td_page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    return _td_page


def navigate(url: str, wait_selector: str = None, timeout: int = 30_000) -> str:
    """Navigue (contexte Trendyol/Daraz) et retourne le HTML rendu."""
    from playwright.sync_api import TimeoutError as PWTimeout

    page = get_page()

    for attempt in range(2):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            break
        except PWTimeout:
            if attempt == 0:
                time.sleep(5)
            else:
                raise RuntimeError(f"Timeout navigation vers {url}")
        except Exception as exc:
            if "closed" in str(exc).lower():
                close()
                page = get_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            else:
                raise

    if wait_selector:
        try:
            page.wait_for_selector(wait_selector, timeout=timeout)
        except PWTimeout:
            pass

    time.sleep(random.uniform(3, 5))
    return page.content()


def close():
    """Ferme le contexte Trendyol/Daraz (mais garde le browser ouvert pour WB)."""
    global _td_context, _td_page
    try:
        if _td_page:
            _td_page.close()
        if _td_context:
            _td_context.close()
    except Exception:
        pass
    _td_page = _td_context = None


# ---------------------------------------------------------------------------
# Contexte Wildberries  (ru-RU)
# ---------------------------------------------------------------------------
def get_wb_page():
    """Retourne la page Playwright pour Wildberries (ru-RU), la crée si besoin."""
    global _wb_context, _wb_page, _wb_initialized

    _ensure_browser()

    if _wb_page is not None:
        try:
            _ = _wb_page.url
            return _wb_page
        except Exception:
            _wb_page = None
            _wb_context = None
            _wb_initialized = False

    _wb_context = _pw_browser.new_context(
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        viewport={"width": 1366, "height": 768},
        extra_http_headers={"Accept-Language": "ru-RU,ru;q=0.9"},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    )
    _wb_page = _wb_context.new_page()
    _wb_page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )

    # Visite initiale homepage WB pour établir les cookies
    print("  [WB] Initialisation du navigateur (visite accueil WB)...")
    try:
        _wb_page.goto("https://www.wildberries.ru/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(random.uniform(15, 25))
    except Exception:
        pass
    _wb_initialized = True

    return _wb_page


def close_wb():
    """Ferme le contexte Wildberries (mais garde le browser ouvert pour TD/Daraz)."""
    global _wb_context, _wb_page, _wb_initialized
    try:
        if _wb_page:
            _wb_page.close()
        if _wb_context:
            _wb_context.close()
    except Exception:
        pass
    _wb_page = _wb_context = None
    _wb_initialized = False


# ---------------------------------------------------------------------------
# Fermeture complète
# ---------------------------------------------------------------------------
def close_all():
    """Ferme tout : les deux contextes + le browser + l'instance Playwright."""
    global _pw_instance, _pw_browser
    close()
    close_wb()
    try:
        if _pw_browser:
            _pw_browser.close()
        if _pw_instance:
            _pw_instance.stop()
    except Exception:
        pass
    _pw_browser = _pw_instance = None
