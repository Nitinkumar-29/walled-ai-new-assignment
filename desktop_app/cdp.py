from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

import websocket

GUARD_SCRIPT = Path(__file__).with_name("guard.js").read_text(encoding="utf-8")
SUPPORTED_HOSTS = {"chatgpt.com", "www.perplexity.ai", "perplexity.ai"}


def _chrome_path() -> str:
    candidates = [
        shutil.which("chrome"),
        os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError("Google Chrome was not found. Install Chrome, then restart Walled AI.")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class PageConnection:
    def __init__(
        self,
        target: dict[str, Any],
        on_scan: Callable[["PageConnection", dict[str, Any]], None],
        on_closed: Callable[["PageConnection"], None],
    ) -> None:
        self.target_id = target["id"]
        self.url = target.get("url", "")
        self.on_scan = on_scan
        self.on_closed = on_closed
        self._counter = 0
        self._send_lock = threading.Lock()
        self._closed = threading.Event()
        self.ready = threading.Event()
        self.socket = websocket.WebSocketApp(
            target["webSocketDebuggerUrl"],
            on_open=self._opened,
            on_message=self._message,
            on_error=self._error,
            on_close=self._close,
        )
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        try:
            self.socket.run_forever(suppress_origin=True, ping_interval=20, ping_timeout=10)
        finally:
            self._closed.set()

    def _opened(self, _socket: websocket.WebSocketApp) -> None:
        self.send("Runtime.enable")
        self.send("Runtime.addBinding", {"name": "__walledAiBridge"})
        self.send("Page.enable")
        self.send("Page.addScriptToEvaluateOnNewDocument", {"source": GUARD_SCRIPT})
        self.send("Runtime.evaluate", {"expression": GUARD_SCRIPT, "awaitPromise": False})
        self.ready.set()

    def _message(self, _socket: websocket.WebSocketApp, raw: str) -> None:
        try:
            message = json.loads(raw)
            if message.get("method") != "Runtime.bindingCalled":
                return
            params = message.get("params", {})
            if params.get("name") != "__walledAiBridge":
                return
            payload = json.loads(params.get("payload", ""))
            self.on_scan(self, payload)
        except (json.JSONDecodeError, TypeError, ValueError):
            return

    def _error(self, _socket: websocket.WebSocketApp, _error: Any) -> None:
        return

    def _close(self, _socket: websocket.WebSocketApp, _status: Any, _message: Any) -> None:
        self._closed.set()
        self.on_closed(self)

    def send(self, method: str, params: dict[str, Any] | None = None) -> None:
        with self._send_lock:
            self._counter += 1
            payload = {"id": self._counter, "method": method}
            if params is not None:
                payload["params"] = params
            self.socket.send(json.dumps(payload))

    def resolve(self, request_id: str, approved: bool, error: str = "") -> None:
        expression = (
            "window.__walledAiResolve("
            + json.dumps(request_id)
            + ","
            + json.dumps({"approved": approved, "error": error})
            + ")"
        )
        try:
            self.send("Runtime.evaluate", {"expression": expression, "awaitPromise": False})
        except websocket.WebSocketException:
            return

    @property
    def closed(self) -> bool:
        return self._closed.is_set()


class ChromeController:
    def __init__(
        self,
        on_ready: Callable[[], None],
        on_status: Callable[[str], None],
        on_scan: Callable[[PageConnection, dict[str, Any]], None],
    ) -> None:
        self.on_ready = on_ready
        self.on_status = on_status
        self.on_scan = on_scan
        self.stop_event = threading.Event()
        self.port: int | None = None
        local_app_data = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        self.profile_dir = Path(local_app_data) / "WalledAI" / "ChromeProfile"
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._connections: dict[str, PageConnection] = {}
        self._thread: threading.Thread | None = None
        self._browser_websocket_url: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            chrome = _chrome_path()
            self.port = _free_port()
            command = [
                chrome,
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "about:blank",
            ]
            subprocess.Popen(command, close_fds=True)
        except (OSError, FileNotFoundError) as error:
            self.on_status(str(error))
            return

        deadline = time.monotonic() + 30
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            try:
                version = self._get_json("/json/version")
                self._browser_websocket_url = version.get("webSocketDebuggerUrl")
                self.on_ready()
                break
            except (OSError, urllib.error.URLError, json.JSONDecodeError):
                time.sleep(0.25)
        else:
            if not self.stop_event.is_set():
                self.on_status("Chrome did not start its local debugging endpoint.")
            return

        while not self.stop_event.wait(0.5):
            try:
                targets = self._get_json("/json/list")
            except (OSError, urllib.error.URLError, json.JSONDecodeError):
                continue
            live_ids: set[str] = set()
            for target in targets:
                if target.get("type") != "page" or not self._supported_url(target.get("url", "")):
                    continue
                target_id = target.get("id")
                live_ids.add(target_id)
                existing = self._connections.get(target_id)
                if existing is None or existing.closed:
                    self._connections[target_id] = PageConnection(target, self.on_scan, self._discard)
            for target_id in tuple(self._connections):
                if target_id not in live_ids:
                    self._connections.pop(target_id, None)

    @staticmethod
    def _supported_url(url: str) -> bool:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.scheme == "https" and parsed.hostname in SUPPORTED_HOSTS
        except ValueError:
            return False

    def _get_json(self, path: str, method: str | None = None) -> Any:
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method)
        with urllib.request.urlopen(request, timeout=1) as response:
            return json.loads(response.read().decode("utf-8"))

    def open_site(self, url: str) -> None:
        if url not in {"https://chatgpt.com/", "https://www.perplexity.ai/"}:
            raise ValueError("Unsupported site.")
        if self.port is None:
            raise RuntimeError("Start the protected browser before opening a site.")
        target = self._get_json("/json/new?about:blank", method="PUT")
        connection = PageConnection(target, self.on_scan, self._discard)
        self._connections[connection.target_id] = connection
        if not connection.ready.wait(5) or connection.closed:
            connection.socket.close()
            raise RuntimeError("Could not install the guard in the new browser tab.")
        connection.send("Page.navigate", {"url": url})

    def _discard(self, connection: PageConnection) -> None:
        current = self._connections.get(connection.target_id)
        if current is connection:
            self._connections.pop(connection.target_id, None)

    def stop(self) -> None:
        self.stop_event.set()
        for connection in tuple(self._connections.values()):
            try:
                connection.socket.close()
            except websocket.WebSocketException:
                pass
        self._connections.clear()
        if self._browser_websocket_url:
            try:
                browser_socket = websocket.create_connection(
                    self._browser_websocket_url,
                    suppress_origin=True,
                    timeout=1,
                )
                browser_socket.send(json.dumps({"id": 1, "method": "Browser.close"}))
                browser_socket.close()
            except websocket.WebSocketException:
                pass

