"""
Verificador de atualizações via GitHub Releases.
Roda em thread separada para não travar a UI.
"""
import json
import threading
import urllib.request
import urllib.error

from version import APP_VERSION, APP_NAME, GITHUB_REPO, APP_URL


def _parse_ver(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except Exception:
        return (0,)

_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _fetch_latest() -> dict | None:
    try:
        req = urllib.request.Request(
            _API,
            headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}",
                     "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def check_for_update(on_update_found: callable, on_no_update: callable | None = None):
    """
    Chama on_update_found(tag, download_url, body) se houver versão nova.
    Executa em thread background — callbacks devem usar signal/slot para thread-safety.
    """
    def _run():
        data = _fetch_latest()
        if not data:
            return
        tag = data.get("tag_name", "").lstrip("v")
        try:
            is_newer = _parse_ver(tag) > _parse_ver(APP_VERSION)
        except Exception:
            return
        if is_newer:
            assets = data.get("assets", [])
            dl_url = next(
                (a["browser_download_url"] for a in assets
                 if a["name"].endswith(".exe")),
                data.get("html_url", APP_URL),
            )
            body = data.get("body", "")
            on_update_found(tag, dl_url, body)
        elif on_no_update:
            on_no_update()

    threading.Thread(target=_run, daemon=True).start()
