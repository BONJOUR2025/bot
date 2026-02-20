"""
BONJOUR Bot Service Launcher
GUI utility to start/stop the bot and web server, with live log output.

Build into EXE on Windows:
    pip install pyinstaller
    pyinstaller --onefile --windowed --name "Launcher" launcher.py
"""
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import scrolledtext


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_project_root() -> Path:
    """Return the project root directory regardless of frozen/dev mode."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller EXE – the exe lives in the project root
        return Path(sys.executable).parent
    return Path(__file__).parent.resolve()


def _find_python(root: Path) -> str:
    """Return the Python executable: prefer venv, fall back to system."""
    candidates = [
        root / "venv" / "Scripts" / "python.exe",   # Windows venv
        root / ".venv" / "Scripts" / "python.exe",
        root / "venv" / "bin" / "python",            # Unix venv
        root / ".venv" / "bin" / "python",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    # Fallback: use the interpreter that runs this script (or "python")
    return sys.executable if not getattr(sys, "frozen", False) else "python"


# ── main window ───────────────────────────────────────────────────────────────

class LauncherApp:
    BG_DARK   = "#1e1e1e"
    BG_TOP    = "#252526"
    BG_BTN    = "#2d2d2d"
    FG_WHITE  = "#d4d4d4"
    GREEN     = "#4ec94e"
    RED       = "#f44747"
    ORANGE    = "#ff9800"
    BLUE      = "#4fc3f7"
    PURPLE    = "#ce93d8"
    LIME      = "#81c784"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("BONJOUR · Сервис")
        self.root.geometry("950x680")
        self.root.minsize(750, 520)
        self.root.configure(bg=self.BG_DARK)

        self._project_root = _get_project_root()
        self._python = _find_python(self._project_root)
        self._processes: list[subprocess.Popen] = []
        self._running = False

        self._build_ui()
        self._log(f"[СИСТЕМА] Проект: {self._project_root}\n", "sys")
        self._log(f"[СИСТЕМА] Python:  {self._python}\n", "sys")
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── top bar ──
        top = tk.Frame(self.root, bg=self.BG_TOP, pady=8)
        top.pack(fill=tk.X)

        tk.Label(
            top, text="BONJOUR Bot Service",
            fg=self.FG_WHITE, bg=self.BG_TOP,
            font=("Segoe UI", 13, "bold"),
        ).pack(side=tk.LEFT, padx=14)

        self._status_text = tk.Label(
            top, text="Остановлен",
            fg=self.RED, bg=self.BG_TOP,
            font=("Segoe UI", 11),
        )
        self._status_text.pack(side=tk.RIGHT, padx=6)

        self._status_dot = tk.Label(
            top, text="●",
            fg=self.RED, bg=self.BG_TOP,
            font=("Segoe UI", 14),
        )
        self._status_dot.pack(side=tk.RIGHT, padx=2)

        # ── button bar ──
        bar = tk.Frame(self.root, bg=self.BG_BTN, pady=6, padx=10)
        bar.pack(fill=tk.X)

        btn_cfg = dict(font=("Segoe UI", 10), padx=14, pady=6,
                       relief=tk.FLAT, cursor="hand2", bd=0)

        self._btn_start = tk.Button(
            bar, text="▶  Запустить сервис",
            bg="#27ae60", fg="white", activebackground="#219a52",
            command=self._start, **btn_cfg,
        )
        self._btn_start.pack(side=tk.LEFT, padx=4)

        self._btn_stop = tk.Button(
            bar, text="■  Остановить",
            bg="#c0392b", fg="white", activebackground="#a93226",
            command=self._stop, state=tk.DISABLED, **btn_cfg,
        )
        self._btn_stop.pack(side=tk.LEFT, padx=4)

        tk.Button(
            bar, text="🗑  Очистить",
            bg="#555", fg="white", activebackground="#444",
            command=self._clear, **btn_cfg,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            bar, text="🌐  Открыть в браузере",
            bg="#1565c0", fg="white", activebackground="#0d47a1",
            command=lambda: webbrowser.open("http://localhost:8000"),
            **btn_cfg,
        ).pack(side=tk.LEFT, padx=4)

        # ── log area ──
        log_frame = tk.Frame(self.root, bg=self.BG_DARK)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        self._log_box = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg=self.BG_DARK, fg=self.FG_WHITE,
            insertbackground="white",
            selectbackground="#264f78",
            relief=tk.FLAT,
        )
        self._log_box.pack(fill=tk.BOTH, expand=True)

        # colour tags
        self._log_box.tag_config("bot",  foreground=self.BLUE)
        self._log_box.tag_config("web",  foreground=self.LIME)
        self._log_box.tag_config("err",  foreground=self.RED)
        self._log_box.tag_config("warn", foreground=self.ORANGE)
        self._log_box.tag_config("sys",  foreground=self.PURPLE)

    # ── logging ───────────────────────────────────────────────────────────────

    def _log(self, text: str, tag: str = "") -> None:
        """Append text to the log box (must be called from the main thread)."""
        self._log_box.insert(tk.END, text, tag)
        self._log_box.see(tk.END)

    def _log_from_thread(self, text: str, tag: str = "") -> None:
        """Thread-safe wrapper: schedules _log on the Tk event loop."""
        self.root.after(0, self._log, text, tag)

    def _clear(self) -> None:
        self._log_box.delete("1.0", tk.END)

    # ── process management ────────────────────────────────────────────────────

    def _start(self) -> None:
        cwd = str(self._project_root)
        python = self._python

        extra = {}
        if sys.platform == "win32":
            extra["creationflags"] = subprocess.CREATE_NO_WINDOW

        self._log("[СИСТЕМА] Запуск бота и веб-сервера...\n", "sys")
        try:
            bot_proc = subprocess.Popen(
                [python, "-m", "app.main"],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **extra,
            )
            web_proc = subprocess.Popen(
                [python, "-m", "uvicorn",
                 "app.server:app",
                 "--host", "0.0.0.0",
                 "--port", "8000"],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **extra,
            )
        except Exception as exc:
            self._log(f"[СИСТЕМА] Ошибка запуска: {exc}\n", "err")
            return

        self._processes = [bot_proc, web_proc]
        self._running = True
        self._set_state_running()

        for proc, prefix, tag in [
            (bot_proc, "BOT", "bot"),
            (web_proc, "WEB", "web"),
        ]:
            threading.Thread(
                target=self._drain, args=(proc.stdout, prefix, tag), daemon=True,
            ).start()
            threading.Thread(
                target=self._drain, args=(proc.stderr, prefix, "err"), daemon=True,
            ).start()

        # Monitor for unexpected exit
        threading.Thread(target=self._watch_processes, daemon=True).start()

    def _stop(self) -> None:
        self._log("[СИСТЕМА] Остановка...\n", "sys")
        for proc in self._processes:
            try:
                proc.terminate()
            except Exception:
                pass
        self._processes.clear()
        self._running = False
        self._set_state_stopped()

    # ── background threads ────────────────────────────────────────────────────

    def _drain(self, stream, prefix: str, default_tag: str) -> None:
        """Read lines from a process stream and forward to the log."""
        for raw in iter(stream.readline, b""):
            try:
                line = raw.decode("utf-8", errors="replace")
            except Exception:
                line = repr(raw)
            lo = line.lower()
            if "error" in lo or "traceback" in lo or "exception" in lo:
                tag = "err"
            elif "warning" in lo or "warn" in lo:
                tag = "warn"
            else:
                tag = default_tag
            self._log_from_thread(f"[{prefix}] {line}", tag)

    def _watch_processes(self) -> None:
        """Detect if all processes have died and update UI accordingly."""
        import time
        while self._running:
            time.sleep(2)
            alive = [p for p in self._processes if p.poll() is None]
            if not alive and self._running:
                self._log_from_thread(
                    "[СИСТЕМА] Все процессы завершились.\n", "sys"
                )
                self._running = False
                self.root.after(0, self._set_state_stopped)
                break

    # ── state helpers ─────────────────────────────────────────────────────────

    def _set_state_running(self) -> None:
        self._btn_start.config(state=tk.DISABLED)
        self._btn_stop.config(state=tk.NORMAL)
        self._status_dot.config(fg=self.GREEN)
        self._status_text.config(text="Работает", fg=self.GREEN)

    def _set_state_stopped(self) -> None:
        self._btn_start.config(state=tk.NORMAL)
        self._btn_stop.config(state=tk.DISABLED)
        self._status_dot.config(fg=self.RED)
        self._status_text.config(text="Остановлен", fg=self.RED)

    def _on_close(self) -> None:
        self._stop()
        self.root.destroy()


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    root = tk.Tk()
    LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
