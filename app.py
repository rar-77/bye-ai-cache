import os
import sys
import json
import socket
import importlib
import webbrowser
import subprocess
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from typing import Optional

import scanner.engine as engine_mod
from scanner.cleaner import execute_clean, reveal_in_explorer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

engine = engine_mod.ScannerEngine()


def pick_folder_dialog() -> Optional[str]:
    """Opens native Windows folder selection dialog via built-in tkinter."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="BYE-AI-CACHE // Seleccionar carpeta o disco a escanear")
        root.destroy()
        if folder:
            return os.path.normpath(folder)
    except Exception:
        pass
    return None


class ByeAiCacheHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, format, *args):
        # Keep console clean
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def _send_json(self, payload: dict, status: int = 200):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/rules":
            self._send_json(engine.rules)
            return
        if parsed.path == "/api/scan/smart":
            try:
                importlib.reload(engine_mod)
                fresh_engine = engine_mod.ScannerEngine()
                data = fresh_engine.run_smart_scan()
                self._send_json(data)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return
        if parsed.path == "/api/pick-folder":
            chosen = pick_folder_dialog()
            self._send_json({"path": chosen})
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            body = self._read_json_body()
        except Exception as exc:
            self._send_json({"error": f"JSON inválido: {exc}"}, status=400)
            return

        if parsed.path == "/api/scan/custom":
            target_path = (body.get("path") or "").strip()
            if not target_path:
                self._send_json({"error": "Falta el parámetro 'path'"}, status=400)
                return
            try:
                data = engine.scan_custom_path(target_path)
                self._send_json(data)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=404)
            return

        if parsed.path == "/api/clean":
            items = body.get("items") or []
            mode = body.get("mode", "recycle")
            dry_run = bool(body.get("dry_run", False))
            res = execute_clean(items, mode=mode, dry_run=dry_run)
            self._send_json(res)
            return

        if parsed.path == "/api/reveal":
            target_path = (body.get("path") or "").strip()
            ok = reveal_in_explorer(target_path)
            self._send_json({"ok": ok})
            return

        self._send_json({"error": "Endpoint no encontrado"}, status=404)


def find_free_port(preferred: int = 7865) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", preferred)) != 0:
            return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def launch_desktop_window(url: str):
    """Tries pywebview first, then Edge/Chrome --app desktop window mode, then standard browser."""
    try:
        import webview  # type: ignore
        webview.create_window("BYE-AI-CACHE v1.0 // WinDirStat + Winamp AI Cleaner", url, width=1060, height=860)
        webview.start()
        return True
    except ImportError:
        pass

    # Try Edge or Chrome in --app mode for a native desktop window look on Windows
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for browser_exe in candidates:
        if os.path.isfile(browser_exe):
            try:
                subprocess.Popen([browser_exe, f"--app={url}", "--window-size=1080,880"])
                return False
            except Exception:
                continue

    webbrowser.open(url)
    return False


def main():
    no_browser = "--no-browser" in sys.argv
    port = find_free_port(7865)
    url = f"http://127.0.0.1:{port}"

    server = ThreadingHTTPServer(("127.0.0.1", port), ByeAiCacheHandler)
    print("=" * 64)
    print("  ⚡ BYE-AI-CACHE v1.0 // Y2K Win2000 & Winamp AI Cleaner ⚡")
    print(f"  Servidor activo en: {url}")
    print("  Presioná Ctrl+C en esta consola para cerrar.")
    print("=" * 64)

    if not no_browser:
        launch_desktop_window(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando BYE-AI-CACHE...")
        server.server_close()


if __name__ == "__main__":
    main()
