import json
import logging
import msvcrt
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import simpledialog

import pystray
from PIL import ImageTk
from winotify import Notification, audio

from applog import setup_logging
from icon import app_icon
from task_row import TaskRow, ensure_progressbar_styles
from tasks_io import delete_task, read_all_tasks, write_task
from watcher import check_process_alive

APP_DIR = Path(__file__).parent
CONFIG_PATH = APP_DIR / "config.json"
LOCK_PATH = APP_DIR / ".singleton.lock"
SHOW_SIGNAL_PATH = APP_DIR / ".show_signal"
_lock_file = None
log = logging.getLogger("task-watcher")


def _acquire_single_instance_lock():
    """Best-effort single-instance guard via an exclusive OS file lock (stdlib
    msvcrt, Windows-only, no extra dependency). Held for the process's lifetime;
    a second launch fails to acquire it and exits immediately instead of spawning
    a duplicate tray icon, panel, and poll loop. Before exiting, it drops a signal
    file so the already-running instance shows its panel - otherwise launching an
    already-running app (e.g. from the Launcher) silently does nothing, which is
    indistinguishable from being broken."""
    global _lock_file
    f = open(LOCK_PATH, "a+b")
    if f.tell() == 0:
        f.write(b"0")
        f.flush()
    f.seek(0)
    try:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()
        try:
            SHOW_SIGNAL_PATH.touch()
        except OSError:
            # Best effort: the second launch is exiting anyway; the only loss is
            # that the running instance doesn't raise its panel.
            log.debug("could not write show-signal file", exc_info=True)
        return False
    _lock_file = f
    return True


DEFAULT_CONFIG = {"poll_interval_seconds": 1.0, "stale_after_minutes": 30}

INK = "#12131C"
PANEL = "#1B1D2B"
HAIRLINE = "#2E3044"
TEXT = "#EDEEF7"
MUTED = "#8688A6"
ACCENT = "#3DDC97"


def load_config():
    config = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    except FileNotFoundError:
        pass
    return config


def _pick_mono_font():
    families = set(tkfont.families())
    for name in ("Cascadia Mono", "Cascadia Code", "Consolas"):
        if name in families:
            return name
    return "Consolas"


def notify(title, message):
    try:
        toast = Notification(app_id="Task Watcher", title=title, msg=message)
        toast.set_audio(audio.Default, loop=False)
        toast.show()
    except Exception:
        # Deliberately broad: toasts are best-effort, winotify shells out to PowerShell and its
        # failure modes aren't documented, and this runs on the Tk thread where an escaped
        # exception would stall the UI queue. Failure is logged (DEBUG) instead of shown.
        log.debug("toast notification failed", exc_info=True)


class TaskWatcherApp:
    def __init__(self):
        self.config = load_config()
        self.root = tk.Tk()
        self.root.title("Task Watcher")
        self.root.configure(bg=INK)
        self.root.attributes("-topmost", True)
        self._mono = _pick_mono_font()
        self._icon_photo = ImageTk.PhotoImage(app_icon())
        self.root.iconphoto(True, self._icon_photo)
        ensure_progressbar_styles(self.root)
        w, h = 300, 420
        x = self.root.winfo_screenwidth() - w - 20
        self.root.geometry(f"{w}x{h}+{x}+40")
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        self.rows = {}
        self._prev_status = {}
        self._stop = threading.Event()
        self.icon = None

        # poll_loop and the pystray tray icon each run on their own thread and must
        # never touch Tk directly; they post callables here and this drain (always
        # running on the Tk thread via after()) is what actually applies them.
        self._ui_queue = queue.Queue()
        self.root.after(50, self._drain_ui_queue)

        self._build_ui()
        threading.Thread(target=self.poll_loop, daemon=True).start()

    def _drain_ui_queue(self):
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                fn()
        except queue.Empty:
            pass
        if SHOW_SIGNAL_PATH.exists():
            try:
                SHOW_SIGNAL_PATH.unlink()
            except OSError:
                # Best effort: worst case the panel is raised again on the next tick.
                log.debug("could not remove show-signal file", exc_info=True)
            self.root.deiconify()
            self.root.lift()
        self.root.after(50, self._drain_ui_queue)

    def _post(self, fn):
        self._ui_queue.put(fn)

    def _build_ui(self):
        tk.Frame(self.root, bg=ACCENT, height=2).pack(fill="x")

        header = tk.Frame(self.root, bg=INK)
        header.pack(fill="x", padx=14, pady=(10, 8))
        tk.Label(header, text="TASK WATCHER", bg=INK, fg=ACCENT, font=(self._mono, 10, "bold")).pack(side="left")

        watch_btn = tk.Label(header, text="+ watch", bg=INK, fg=MUTED, font=(self._mono, 9), cursor="hand2")
        watch_btn.pack(side="right")
        watch_btn.bind("<Button-1>", lambda e: self.prompt_watch_process())
        watch_btn.bind("<Enter>", lambda e: watch_btn.config(fg=ACCENT))
        watch_btn.bind("<Leave>", lambda e: watch_btn.config(fg=MUTED))

        self.empty_label = tk.Label(
            self.root,
            text="No active tasks.\n\nDrop a status JSON file in\nthe 'tasks' folder, or\nclick '+ watch' above.",
            bg=INK,
            fg=MUTED,
            font=("Segoe UI", 9),
            justify="center",
        )
        self.empty_label.pack(pady=30)

        canvas_frame = tk.Frame(self.root, bg=INK)
        canvas_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg=INK, highlightthickness=0)
        scrollbar = tk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.rows_frame = tk.Frame(self.canvas, bg=INK)
        self.rows_frame.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.root.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    def prompt_watch_process(self):
        val = simpledialog.askstring(
            "Watch Process",
            "Enter a PID (number) or process name (e.g. ffmpeg.exe):",
            parent=self.root,
        )
        if not val:
            return
        val = val.strip()
        task_id = f"proc-{val.replace('.', '_').replace(' ', '_')}-{int(time.time())}"
        if val.isdigit():
            write_task(
                task_id,
                {"label": f"Watching PID {val}", "progress": None, "status": "running", "pid": int(val)},
            )
        else:
            write_task(
                task_id,
                {"label": f"Watching {val}", "progress": None, "status": "running", "process_name": val},
            )

    def poll_loop(self):
        while not self._stop.is_set():
            time.sleep(self.config["poll_interval_seconds"])
            tasks = read_all_tasks()
            now = time.time()
            stale_seconds = self.config.get("stale_after_minutes", 30) * 60

            for task_id, task in list(tasks.items()):
                status = task.get("status")
                if status not in ("running", "waiting"):
                    continue

                is_process_task = bool(task.get("pid") or task.get("process_name"))

                if is_process_task:
                    alive = check_process_alive(task)
                    if alive:
                        # Confirmed alive right now - refresh _seen_alive once and
                        # skip the staleness check below entirely; liveness is our
                        # freshness signal for these, not updated_at.
                        if not task.get("_seen_alive"):
                            task["_seen_alive"] = True
                            write_task(task_id, task)
                            tasks[task_id] = task
                        continue
                    elif alive is False and task.get("_seen_alive"):
                        task["status"] = "done"
                        task["progress"] = 100
                        write_task(task_id, task)
                        tasks[task_id] = task
                        continue
                    # else: alive is False and never seen alive - the watched PID/name
                    # may just not have started yet. Fall through to the staleness
                    # check below so a genuine typo eventually resolves instead of
                    # spinning forever.

                age = now - self._parse_updated_at(task.get("updated_at"), now)
                if age > stale_seconds:
                    minutes = self.config.get("stale_after_minutes", 30)
                    reason = "process never detected" if is_process_task else f"no update in {minutes}+ min"
                    task["status"] = "failed"
                    task["label"] = f"{task.get('label', task_id)} ({reason})"
                    write_task(task_id, task)
                    tasks[task_id] = task

            self._post(lambda t=tasks: self.update_ui(t))

    @staticmethod
    def _parse_updated_at(value, default_now):
        if not value:
            return default_now
        try:
            return time.mktime(time.strptime(value, "%Y-%m-%dT%H:%M:%S"))
        except (ValueError, TypeError):
            return default_now

    def update_ui(self, tasks):
        for task_id, task in tasks.items():
            status = task.get("status", "running")
            prev = self._prev_status.get(task_id)
            if prev not in ("done", "failed") and status in ("done", "failed"):
                notify(
                    "Task finished" if status == "done" else "Task failed",
                    task.get("label", task_id),
                )
            self._prev_status[task_id] = status

        for task_id in list(self.rows.keys()):
            if task_id not in tasks:
                self.rows[task_id].destroy()
                del self.rows[task_id]
                self._prev_status.pop(task_id, None)

        for task_id, task in tasks.items():
            if task_id not in self.rows:
                self.rows[task_id] = TaskRow(self.rows_frame, task_id, self.dismiss_task, mono_font=self._mono)
            self.rows[task_id].update(task)

        if tasks:
            self.empty_label.pack_forget()
        else:
            self.empty_label.pack(pady=30)

    def dismiss_task(self, task_id):
        delete_task(task_id)
        self._prev_status.pop(task_id, None)
        if task_id in self.rows:
            self.rows[task_id].destroy()
            del self.rows[task_id]
        if not self.rows:
            self.empty_label.pack(pady=30)

    def hide_window(self):
        self.root.withdraw()

    def show_window(self, icon=None, item=None):
        self._post(self.root.deiconify)

    def quit_app(self, icon=None, item=None):
        self._stop.set()
        if self.icon:
            self.icon.stop()
        self._post(self.root.destroy)

    def run(self):
        menu = pystray.Menu(
            pystray.MenuItem("Show Panel", self.show_window, default=True),
            pystray.MenuItem("Watch Process...", lambda icon, item: self._post(self.prompt_watch_process)),
            pystray.MenuItem("Quit", self.quit_app),
        )
        self.icon = pystray.Icon("task-watcher", app_icon(), "Task Watcher", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()
        self.root.mainloop()


def main():
    setup_logging("task-watcher")
    if not _acquire_single_instance_lock():
        return
    app = TaskWatcherApp()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        log.exception("fatal error")

        with open(APP_DIR / "app_error.log", "a", encoding="utf-8") as f:
            f.write(f"\n--- {time.ctime()} ---\n")
            f.write(traceback.format_exc())
        raise
