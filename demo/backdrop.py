"""A plain dark window that covers the second monitor during the take, so nothing
personal behind the demo windows ends up in the video."""

import ctypes
import tkinter as tk

ctypes.windll.shcore.SetProcessDpiAwareness(2)
user32 = ctypes.windll.user32


def second_monitor():
    from ctypes import wintypes
    found = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                               ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def cb(h, dc, r, lp):
        rc = r.contents
        found.append((rc.left, rc.top, rc.right, rc.bottom))
        return 1
    user32.EnumDisplayMonitors(0, 0, proto(cb), 0)
    return next(m for m in found if not (m[0] == 0 and m[1] == 0))


l, t, r, b = second_monitor()
root = tk.Tk()
root.title("hands-off demo backdrop")
root.overrideredirect(True)
root.configure(bg="#1b1e24")
# "+-1920": Tk reads "-1920" alone as "1920 from the right edge"; "+-1920" is x = -1920
root.geometry(f"{r - l}x{b - t}+{l}+{t}")
root.update_idletasks()
# never topmost, so the demo windows opened after it stay in front
hwnd = user32.GetAncestor(root.winfo_id(), 2)  # GA_ROOT
user32.SetWindowPos(hwnd, -2, l, t, r - l, b - t, 0x0010)  # HWND_NOTOPMOST, SWP_NOACTIVATE
root.mainloop()
