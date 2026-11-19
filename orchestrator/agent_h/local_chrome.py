"""Chrome dédié de l'ordinateur de démo (host user_device), lancé avec les bons réglages.

Sur un écran Retina, Chrome affiche la page en densité 2 : la capture vue par l'agent H est deux fois
plus grande que la page, et ses clics tombaient deux fois trop bas et trop à droite (mesuré le
2026-11-18 sur SNCF Connect : le clic sur « Trains » ouvrait la publicité en dessous). On force donc la
densité 1. Même profil que le SDK H (~/.hai/chrome-profile) : les connexions aux sites sont gardées.

    python -m orchestrator.agent_h.local_chrome            # ouvre le Chrome dédié
    python -m orchestrator.agent_h.local_chrome --restart  # le ferme proprement et le rouvre
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PORT = 9222
PROFILE_DIR = Path.home() / ".hai" / "chrome-profile"  # celui du SDK H (hai_agents_local.browser)
FLAGS = [
    f"--remote-debugging-port={PORT}",
    f"--user-data-dir={PROFILE_DIR}",
    "--force-device-scale-factor=1",  # clics justes sur écran Retina
    "--window-size=1280,860",
    "--no-first-run",
    "--no-default-browser-check",
]
_CANDIDATES = {
    "Darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
    "Linux": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
    "Windows": [r"C:\Program Files\Google\Chrome\Application\chrome.exe"],
}


def listening(port: int = PORT) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _binary() -> str | None:
    for candidate in _CANDIDATES.get(platform.system(), []):
        if Path(candidate).exists() or shutil.which(candidate):
            return shutil.which(candidate) or candidate
    return None


def open_pages() -> int:
    """Nombre d'onglets ouverts dans le Chrome dédié (0 si injoignable)."""
    try:
        targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=3))
    except Exception:
        return 0
    return sum(1 for target in targets if target.get("type") == "page")


def current_url() -> str | None:
    """Adresse de l'onglet ouvert dans le Chrome dédié (None si injoignable ou page vide)."""
    try:
        targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=3))
    except Exception:
        return None
    for target in targets:
        url = target.get("url") or ""
        if target.get("type") == "page" and url.startswith("http"):
            return url
    return None


def ensure_page(url: str = "about:blank") -> None:
    """H ferme l'onglet à la fin d'une session : sans onglet, la session suivante échoue
    (« no such window: target window already closed »). On en rouvre un."""
    if listening() and open_pages() == 0:
        request = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?{url}", method="PUT")
        urllib.request.urlopen(request, timeout=5).close()
        time.sleep(1)


def fresh_page(url: str) -> None:
    """Nouvel onglet sur `url`, puis fermeture des autres : chaque commande part d'une page propre.

    Sinon l'agent peut s'accrocher à l'onglet de la commande précédente, que H ferme avec un temps de
    retard (« no such window: target window already closed », résultats d'un autre trajet affichés).
    La connexion aux sites est dans le profil Chrome, pas dans l'onglet : elle est gardée.
    """
    if not listening():
        return
    request = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?{url}", method="PUT")
    new_tab = json.load(urllib.request.urlopen(request, timeout=5))
    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=3))
    for target in targets:
        if target.get("type") == "page" and target.get("id") != new_tab.get("id"):
            with contextlib.suppress(Exception):
                urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/json/close/{target['id']}", timeout=3
                ).close()
    with contextlib.suppress(Exception):  # met le nouvel onglet au premier plan
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/activate/{new_tab['id']}", timeout=3).close()
    time.sleep(1)


_TUNED = False


def tune_local_driver() -> None:
    """Le relais local de H pilote ce Chrome par Selenium, réglé pour attendre le chargement COMPLET de la
    page après chaque commande : ≈ 5 s par clic sur SNCF Connect (mesuré le 19/11 : « click_at dispatched
    in 5.2 s »).
    « eager » n'attend que la structure de la page (DOMContentLoaded). PILOTE_H_PAGE_LOAD=normal revient au
    réglage de H, none n'attend rien."""
    global _TUNED
    strategy = (os.getenv("PILOTE_H_PAGE_LOAD") or "eager").strip()
    if _TUNED or strategy == "normal":
        return
    try:
        from hai_drivers.web.selenium import driver as selenium_driver
    except ImportError:
        return
    original = selenium_driver.SeleniumWebDriver._get_chrome_options.__func__

    def with_strategy(cls, *args, **kwargs):  # type: ignore[no-untyped-def]
        options = original(cls, *args, **kwargs)
        options.page_load_strategy = strategy
        return options

    selenium_driver.SeleniumWebDriver._get_chrome_options = classmethod(with_strategy)
    _TUNED = True


def navigate(url: str) -> bool:
    """Envoie l'onglet de l'agent à `url`, sans ouvrir d'onglet : une session H en attente, branchée sur cet
    onglet, le reste. False si Chrome ou l'onglet manque (on ouvre alors un onglet neuf)."""
    if not listening():
        return False
    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=3))
    pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if not pages:
        return False
    from websockets.sync.client import connect

    with connect(pages[0]["webSocketDebuggerUrl"], max_size=None, open_timeout=3) as ws:
        ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
        ws.recv(timeout=5)
    return True


def ensure(url: str | None = None) -> bool:
    """Lance le Chrome dédié s'il n'est pas déjà ouvert, avec au moins un onglet.
    Renvoie False si Chrome est introuvable."""
    if listening():
        ensure_page(url or "about:blank")
        return True
    binary = _binary()
    if binary is None:
        return False
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [binary, *FLAGS, *([url] if url else [])],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if listening():
            return True
        time.sleep(0.25)
    return False


def close() -> None:
    """Ferme le Chrome dédié proprement (Browser.close), pour que les cookies soient enregistrés."""
    if not listening():
        return
    import asyncio

    import websockets

    info = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=3))

    async def _close() -> None:
        async with websockets.connect(info["webSocketDebuggerUrl"]) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Browser.close"}))
            try:
                await asyncio.wait_for(ws.recv(), 3)
            except Exception:
                pass

    asyncio.run(_close())
    deadline = time.monotonic() + 10
    while listening() and time.monotonic() < deadline:
        time.sleep(0.25)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--restart", action="store_true", help="fermer proprement puis rouvrir")
    parser.add_argument("--url", default="https://www.sncf-connect.com")
    args = parser.parse_args()
    if args.restart:
        close()
    ok = ensure(args.url)
    print("Chrome dédié prêt (port 9222, densité 1)" if ok else "Chrome introuvable", file=sys.stderr)
    sys.exit(0 if ok else 1)
