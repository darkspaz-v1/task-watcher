import tkinter.font as tkfont
import tkinter as tk
from tkinter import ttk

INK = "#12131C"
PANEL = "#1B1D2B"
HAIRLINE = "#2E3044"
TEXT = "#EDEEF7"
MUTED = "#8688A6"
DANGER = "#F0576B"

STATUS_COLORS = {
    "running": "#5B8DEF",
    "waiting": "#F5A623",
    "done": "#3DDC97",
    "failed": "#F0576B",
}

_styles_ready = False


def pick_mono_font():
    families = set(tkfont.families())
    for name in ("Cascadia Mono", "Cascadia Code", "Consolas"):
        if name in families:
            return name
    return "Consolas"


def ensure_progressbar_styles(root):
    """One-time ttk.Style setup for dark, per-status colored progress bars.
    'clam' is the only bundled ttk theme that actually honors custom colors on Windows -
    the default 'vista' theme ignores background/troughcolor entirely."""
    global _styles_ready
    if _styles_ready:
        return
    style = ttk.Style(root)
    style.theme_use("clam")
    for status, color in STATUS_COLORS.items():
        style.configure(
            f"{status}.Horizontal.TProgressbar",
            troughcolor=PANEL,
            background=color,
            bordercolor=PANEL,
            lightcolor=color,
            darkcolor=color,
            thickness=6,
        )
    _styles_ready = True


class TaskRow:
    def __init__(self, parent, task_id, on_dismiss, mono_font=None):
        self.task_id = task_id
        self._mono = mono_font or pick_mono_font()

        self.frame = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=HAIRLINE)
        self.label_var = tk.StringVar()
        self.status_var = tk.StringVar()

        pad = tk.Frame(self.frame, bg=PANEL)
        pad.pack(fill="x", padx=10, pady=8)

        tk.Label(
            pad,
            textvariable=self.label_var,
            anchor="w",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 9, "bold"),
            wraplength=220,
            justify="left",
        ).pack(fill="x")

        row2 = tk.Frame(pad, bg=PANEL)
        row2.pack(fill="x", pady=(6, 0))

        self.pb = ttk.Progressbar(row2, length=190, mode="determinate", style="running.Horizontal.TProgressbar")
        self.pb.pack(side="left", fill="x", expand=True)

        self._dismissable = False
        self.dismiss_btn = tk.Label(row2, text="×", bg=PANEL, fg=MUTED, font=(self._mono, 12))
        self.dismiss_btn.pack(side="left", padx=(8, 0))
        self._on_dismiss = on_dismiss
        self.dismiss_btn.bind("<Button-1>", self._maybe_dismiss)
        self.dismiss_btn.bind("<Enter>", self._on_dismiss_hover)
        self.dismiss_btn.bind("<Leave>", lambda e: self.dismiss_btn.config(fg=MUTED))

        self.status_label = tk.Label(
            pad, textvariable=self.status_var, anchor="w", bg=PANEL, fg=MUTED, font=(self._mono, 8)
        )
        self.status_label.pack(fill="x", pady=(4, 0))

        self.frame.pack(fill="x", padx=8, pady=4)
        self._indeterminate = False

    def _on_dismiss_hover(self, event):
        if self._dismissable:
            self.dismiss_btn.config(fg=DANGER)

    def _maybe_dismiss(self, event):
        if self._dismissable:
            self._on_dismiss(self.task_id)

    def update(self, task):
        self.label_var.set(task.get("label") or self.task_id)
        status = task.get("status", "running")
        progress = task.get("progress")

        style_status = status if status in STATUS_COLORS else "running"
        self.pb.config(style=f"{style_status}.Horizontal.TProgressbar")

        if progress is None:
            if not self._indeterminate:
                self.pb.config(mode="indeterminate")
                self.pb.start(15)
                self._indeterminate = True
        else:
            if self._indeterminate:
                self.pb.stop()
                self.pb.config(mode="determinate")
                self._indeterminate = False
            try:
                self.pb.config(value=max(0, min(100, int(progress))))
            except (TypeError, ValueError):
                pass

        color = STATUS_COLORS.get(status, MUTED)
        self.status_label.config(fg=color)
        pct = f"  ·  {progress}%" if isinstance(progress, (int, float)) else ""
        self.status_var.set(f"{status.upper()}{pct}")

        self._dismissable = status in ("done", "failed")
        self.dismiss_btn.config(fg=MUTED, cursor="hand2" if self._dismissable else "arrow")

    def destroy(self):
        try:
            self.pb.stop()
        except Exception:
            pass
        self.frame.destroy()
