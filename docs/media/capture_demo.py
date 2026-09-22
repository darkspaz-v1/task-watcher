"""Regenerates docs/media/demo.gif, docs/media/panel.png and docs/media/social-preview.png.

    python docs/media/capture_demo.py

Safety properties (this is how the published media was made):
  * The panel is launched from THIS checkout only, with tasks_io.TASKS_DIR redirected to a
    throwaway temp folder, so your real tasks/ folder is never read or written.
  * The single-instance lock is never taken, so it cannot collide with a running Task Watcher.
  * Every task below is invented (no real names, paths, hosts or accounts).
  * Only the panel window's rectangle is captured, never the desktop; toasts are stubbed out.

Why the done-toast isn't in the capture (evaluated, rejected):
  A real Windows toast renders outside the app window -- bottom-right of the screen, placed and
  animated by the OS notification platform, not by this process. Capturing it would mean grabbing
  a chunk of the real desktop instead of just this app's window rect, which breaks the "never
  capture the desktop" safety property above (whatever else is on screen -- other windows, other
  apps' notifications -- would end up in a published GIF). It's also not reliably reproducible:
  the toast is suppressed by Focus Assist, requires notifications to be enabled for the app, and
  winotify shells out to PowerShell to show it, so timing before a screen grab is not deterministic.
  For those reasons `app.notify` stays stubbed out here (see below) and the toast is not captured;
  `notify()` in app.py fires it with title "Task finished"/"Task failed" and the task's label as
  the message -- see the README caption for a one-line description of what it looks like.
Needs Pillow and the runtime requirements (pystray, winotify, psutil). Windows only.
"""
import ctypes
import shutil
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # physical pixels, so window rect == grab rect
except (AttributeError, OSError):
    ctypes.windll.user32.SetProcessDPIAware()

from PIL import Image, ImageDraw, ImageFont, ImageGrab  # noqa: E402

import app  # noqa: E402
import tasks_io  # noqa: E402

STEP_MS = 600
CAPTURE_LAG_MS = 560  # poll interval is 0.4 s below; wait for the panel to reflect the write
HOLD_FRAMES = 4       # repeat the final frame so the loop pauses on the finished state

# (id, label, [(step, status, progress), ...]) -- all invented
SCRIPT = [  # ids sort alphabetically, which is the order the panel lists them in
    ("a-render", "Render product demo video", [(0, "running", 8), (2, "running", 38), (4, "running", 71), (6, "done", 100)]),
    ("b-train", "Train classifier (epoch 4/10)", [(0, "running", 32), (3, "running", 47), (6, "running", 58), (9, "running", 71)]),
    ("c-export", "Nightly export to archive", [(0, "running", None)]),
]
STEPS = 11


def frame_rect(root):
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    rect = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))  # extended frame bounds
    return rect.left, rect.top, rect.right, rect.bottom


def main():
    tmp = Path(tempfile.mkdtemp(prefix="task-watcher-demo-"))
    tasks_io.TASKS_DIR = tmp / "tasks"
    tasks_io.TASKS_DIR.mkdir()
    toasts = []
    app.notify = lambda title, message: toasts.append((title, message))  # no real toasts

    watcher = app.TaskWatcherApp()
    watcher.config["poll_interval_seconds"] = 0.4
    root = watcher.root
    frames = []

    def write_step(i):
        for task_id, label, timeline in SCRIPT:
            current = [t for t in timeline if t[0] <= i]
            if not current:
                continue
            _, status, progress = current[-1]
            tasks_io.write_task(task_id, {"label": label, "status": status, "progress": progress})

    def capture():
        root.update_idletasks()
        frames.append(ImageGrab.grab(bbox=frame_rect(root), all_screens=True).convert("RGB"))

    for i in range(STEPS):
        root.after(500 + i * STEP_MS, write_step, i)
        root.after(500 + i * STEP_MS + CAPTURE_LAG_MS, capture)
    root.after(500 + STEPS * STEP_MS + CAPTURE_LAG_MS + 300, root.quit)
    root.mainloop()
    watcher._stop.set()
    root.destroy()
    shutil.rmtree(tmp, ignore_errors=True)

    frames = frames + [frames[-1]] * HOLD_FRAMES
    frames[-1].save(OUT / "panel.png", optimize=True)
    pal = frames[-1].quantize(colors=48, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    q[0].save(OUT / "demo.gif", save_all=True, append_images=q[1:], duration=STEP_MS, loop=0, optimize=True, disposal=1)
    build_social(frames[-1])
    print("frames:", len(frames), "size:", frames[0].size, "| toasts that would fire:", toasts)


def build_social(panel):
    W, H = 1280, 640
    BG, TEXT, MUTED, ACCENT = "#12131C", "#EDEEF7", "#8688A6", "#3DDC97"
    fonts = Path("C:/Windows/Fonts")

    def font(name, size):
        return ImageFont.truetype(str(fonts / name), size)

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 6), fill=ACCENT)
    d.text((80, 120), "Task Watcher", font=font("segoeuib.ttf", 72), fill=TEXT)
    lead = font("segoeui.ttf", 32)
    d.text((82, 224), 'One always-on-top panel that answers', font=lead, fill=TEXT)
    d.text((82, 268), '"is it done yet?" for anything long-running,', font=lead, fill=TEXT)
    d.text((82, 312), "including Claude Code sessions.", font=lead, fill=TEXT)
    d.text((82, 392), "Windows tray app in Python, with a toast when a task finishes", font=font("segoeui.ttf", 22), fill=MUTED)
    d.text((82, 560), "MIT licensed - tests and CI on Windows", font=font("consola.ttf", 20), fill=MUTED)
    scale = min(540 / panel.height, 1.0)
    shot = panel.resize((int(panel.width * scale), int(panel.height * scale)), Image.LANCZOS)
    x, y = 860, (H - shot.height) // 2 + 6
    d.rectangle((x - 2, y - 2, x + shot.width + 1, y + shot.height + 1), outline="#2E3044", width=2)
    img.paste(shot, (x, y))
    d.text((x, y + shot.height + 10), "Real screenshot, invented tasks", font=font("consola.ttf", 14), fill=MUTED)
    img.save(OUT / "social-preview.png", optimize=True)


if __name__ == "__main__":
    main()
