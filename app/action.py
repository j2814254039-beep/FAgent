import queue
import threading
import tkinter
from itertools import cycle
from pathlib import Path

from app.config import getActionPath

FRAME_INTERVAL_MS = 100
TRANSPARENT = "#3c5a8c"


class AvatarWindow:
    """桌宠窗口。所有 Tk 操作都在它自己那个线程里。"""

    def __init__(self):
        self.rootDir = Path(getActionPath())
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # ---------- 对外接口（线程安全）----------
    def play(self, action: str) -> None:
        self._queue.put(action)

    # ---------- 窗口线程 ----------
    def _run(self) -> None:
        root = tkinter.Tk()                    # ★ 在【本线程】创建
        root.geometry("500x500")
        root.overrideredirect(True)
        root.wm_attributes("-transparentcolor", TRANSPARENT)
        root.configure(bg=TRANSPARENT)

        label = tkinter.Label(root, bg=TRANSPARENT, bd=0)
        label.pack()

        _photo = None
        current = {"cycle": None}

        # ---- 拖动 ----
        _drag = {}
        label.bind("<Button-1>", lambda e: _drag.update(
            x=e.x_root - root.winfo_x(), y=e.y_root - root.winfo_y()))
        label.bind("<B1-Motion>", lambda e: root.geometry(
            f"+{e.x_root - _drag['x']}+{e.y_root - _drag['y']}"))

        # ---- 右键菜单 ----
        _menu = None
        def showMenu(e):
            nonlocal _menu
            _menu = tkinter.Menu(root, tearoff=0)
            _menu.add_command(label="退出", command=root.destroy)
            root.focus_force()
            try:
                _menu.tk_popup(e.x_root, e.y_root)
            finally:
                _menu.grab_release()
        label.bind("<Button-3>", showMenu)

        # ---- 帧动画 + 队列轮询 ----
        def tick():
            nonlocal _photo

            # 1. 有新动作请求吗？
            try:
                action = self._queue.get_nowait()
            except queue.Empty:
                pass
            else:
                frames = sorted((self.rootDir / action).glob("*.png"))
                if frames:
                    current["cycle"] = cycle(frames)

            # 2. 播下一帧
            if current["cycle"] is not None:
                frame = next(current["cycle"])
                _photo = tkinter.PhotoImage(file=str(frame))
                label.configure(image=_photo)

            root.after(FRAME_INTERVAL_MS, tick)

        # 默认动作
        defaultFrames = sorted((self.rootDir / "站立").glob("*.png"))
        if defaultFrames:
            current["cycle"] = cycle(defaultFrames)

        root.after(0, tick)
        root.mainloop()                        # ★ 在【本线程】进入事件循环
