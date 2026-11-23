from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any

from desktop_app.cdp import ChromeController, PageConnection
from native_host.scanner import response_for_request


class WalledAIApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.controller: ChromeController | None = None
        root.title("Walled AI")
        root.geometry("520x370")
        root.minsize(480, 340)
        root.protocol("WM_DELETE_WINDOW", self.close)

        frame = ttk.Frame(root, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Walled AI", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="Standalone desktop guard for ChatGPT and Perplexity.\n"
            "Matching prompts and uploads are held for your decision.",
            justify="left",
        ).pack(anchor="w", pady=(8, 20))

        self.start_button = ttk.Button(frame, text="Start protected Chrome", command=self.start_browser)
        self.start_button.pack(fill="x")
        self.site_buttons = ttk.Frame(frame)
        self.site_buttons.pack(fill="x", pady=(10, 0))
        self.chatgpt_button = ttk.Button(
            self.site_buttons,
            text="Open ChatGPT",
            command=lambda: self.open_site("https://chatgpt.com/"),
            state="disabled",
        )
        self.chatgpt_button.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.perplexity_button = ttk.Button(
            self.site_buttons,
            text="Open Perplexity",
            command=lambda: self.open_site("https://www.perplexity.ai/"),
            state="disabled",
        )
        self.perplexity_button.pack(side="left", fill="x", expand=True, padx=(5, 0))

        ttk.Separator(frame).pack(fill="x", pady=18)
        ttk.Label(frame, text="Marker: WALLED_SENSITIVE (case-insensitive)").pack(anchor="w")
        ttk.Label(
            frame,
            text="Sign in to sites in this dedicated Chrome profile. Only tabs opened\n"
            "inside the protected browser are monitored.",
            justify="left",
        ).pack(anchor="w", pady=(8, 0))
        self.status = tk.StringVar(value="Protected browser is not running.")
        ttk.Label(frame, textvariable=self.status, wraplength=460).pack(anchor="w", pady=(18, 0))

    def start_browser(self) -> None:
        if self.controller is not None:
            return
        self.start_button.configure(state="disabled")
        self.status.set("Starting a dedicated Chrome profile...")
        self.controller = ChromeController(
            on_ready=lambda: self.root.after(0, self.browser_ready),
            on_status=lambda text: self.root.after(0, self.show_status, text),
            on_scan=self.scan_request,
        )
        self.controller.start()

    def browser_ready(self) -> None:
        self.start_button.configure(text="Protected Chrome is running", state="disabled")
        self.chatgpt_button.configure(state="normal")
        self.perplexity_button.configure(state="normal")
        self.status.set("Ready. Use the buttons to open a protected site.")

    def show_status(self, text: str) -> None:
        self.status.set(text)
        self.start_button.configure(state="normal")
        self.controller = None

    def open_site(self, url: str) -> None:
        if self.controller is None:
            return
        try:
            self.controller.open_site(url)
            self.status.set("Site opened in the protected Chrome profile.")
        except (OSError, RuntimeError, ValueError) as error:
            self.status.set(f"Could not open the site: {error}")

    def scan_request(self, connection: PageConnection, request: dict[str, Any]) -> None:
        self.root.after(0, self._scan_on_ui_thread, connection, request)

    def _scan_on_ui_thread(self, connection: PageConnection, request: dict[str, Any]) -> None:
        request_id = request.get("request_id")
        if not isinstance(request_id, str):
            return
        try:
            result = response_for_request(request, self.confirm)
            connection.resolve(request_id, bool(result.get("approved")), result.get("error", ""))
        except Exception as error:
            connection.resolve(request_id, False, f"Inspection failed: {error}")

    def confirm(self, kind: str, summary: str, excerpt: str) -> bool:
        dialog = tk.Toplevel(self.root)
        dialog.title("Walled AI — sensitive content detected")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"{kind}: {summary}", wraplength=460, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(frame, text=excerpt or "(No text preview available)", wraplength=460).pack(anchor="w", pady=(10, 16))

        answer = {"approved": False}

        def finish(approved: bool) -> None:
            answer["approved"] = approved
            dialog.destroy()

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e")
        ttk.Button(buttons, text="Cancel", command=lambda: finish(False)).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Continue", command=lambda: finish(True)).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        dialog.bind("<Escape>", lambda _event: finish(False))
        dialog.bind("<Return>", lambda _event: finish(False))
        self.root.wait_window(dialog)
        return answer["approved"]

    def close(self) -> None:
        if self.controller is not None:
            self.controller.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    WalledAIApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
