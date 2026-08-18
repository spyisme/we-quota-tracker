import requests, time, json, os, sys, threading, math, ctypes
import tkinter as tk
from tkinter import messagebox
from capsolver import solveCaptcha

# Enable high-DPI awareness on Windows to prevent blurry text and coordinate scaling glitches
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# System Tray & Image Imports
from PIL import Image, ImageDraw, ImageTk
import pystray
from pystray import MenuItem as item

# ---------------------------------------------------------------------------
# Icon Helpers
# ---------------------------------------------------------------------------

def create_gear_image(size=16, color="#a4b0be"):
    """Creates a high-DPI PIL Image of a settings gear icon."""
    scale = 4
    img_size = size * scale
    img = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = img_size / 2, img_size / 2
    r_outer = img_size * 0.45
    r_inner = img_size * 0.30
    r_hole  = img_size * 0.14
    num_teeth = 6

    for i in range(num_teeth):
        angle = i * (2 * math.pi / num_teeth)
        w = math.pi / (num_teeth * 2.5)
        pts = [
            (cx + r_inner * math.cos(angle - w*1.5), cy + r_inner * math.sin(angle - w*1.5)),
            (cx + r_outer * math.cos(angle - w),     cy + r_outer * math.sin(angle - w)),
            (cx + r_outer * math.cos(angle + w),     cy + r_outer * math.sin(angle + w)),
            (cx + r_inner * math.cos(angle + w*1.5), cy + r_inner * math.sin(angle + w*1.5)),
        ]
        draw.polygon(pts, fill=color)

    draw.ellipse((cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner), fill=color)
    draw.ellipse((cx - r_hole, cy - r_hole, cx + r_hole, cy + r_hole), fill=(0, 0, 0, 0))
    return img.resize((size, size), Image.Resampling.LANCZOS)

# ---------------------------------------------------------------------------
# Config helpers  (config.json lives next to the exe / script, never bundled)
# ---------------------------------------------------------------------------

def get_config_path():
    """Return the absolute path to config.json next to the exe/script."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "config.json")

DEFAULT_CONFIG = {
    "LANDLINE": "",
    "MY_WE_PASSWORD": "",
    "GOOGLE_API_KEY": "",
}

def load_config() -> dict:
    path = get_config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Fill any missing keys with defaults
            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg: dict):
    path = get_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

# ---------------------------------------------------------------------------
# Runtime globals (reloaded after every settings save)
# ---------------------------------------------------------------------------

_cfg = load_config()

def _apply_config(cfg: dict):
    global landline, password, acctId, google_api_key
    landline       = cfg.get("LANDLINE", "")
    password       = cfg.get("MY_WE_PASSWORD", "")
    acctId         = "FBB" + landline[1:] if landline else ""
    google_api_key = cfg.get("GOOGLE_API_KEY", "")

_apply_config(_cfg)

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------

BASE_DIR     = os.path.dirname(get_config_path())
SESSION_FILE = os.path.join(BASE_DIR, "session_data.json")
LOG_FILE     = os.path.join(BASE_DIR, "quota_log.json")

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except Exception:
        pass

def get_base_session():
    session = requests.Session()
    session.headers.update({
        "Connection": "keep-alive",
        "sec-ch-ua-platform": "\"Windows\"",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "sec-ch-ua": "\"Not=A?Brand\";v=\"99\", \"Brave\";v=\"151\", \"Chromium\";v=\"151\"",
        "Content-Type": "application/json; charset=UTF-8",
        "sec-ch-ua-mobile": "?0",
        "Sec-GPC": "1",
        "Origin": "https://my.te.eg",
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://my.te.eg/",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9"
    })
    return session

def perform_login():
    session = get_base_session()
    captchaPayload = {"merchantName": "E-Care", "serviceName": "Login", "identifier": landline}
    response = session.post("https://captcha.te.eg/api/Captcha/GenerateCaptcha", json=captchaPayload)
    captcha = response.json()

    if captcha.get("status") != "Success":
        raise Exception("Captcha request failed")

    captchaToken = captcha["token"]
    answer = "" if captcha.get("requireInteraction") == False else solveCaptcha(captcha["captcha"], google_api_key)["letters"]

    loginPayload = {
        "acctId": acctId, "password": password, "imgCacheKey": captchaToken,
        "appLocale": "en-US", "isSelfcare": "Y", "isMobile": "N",
        "imgCode": answer, "isConvergent": "0"
    }

    session.headers.update({
        "channelid": "702", "csrftoken": "", "languagecode": "en-US",
        "isselfcare": "true", "delegatorsubsid": "", "iscoporate": "false",
        "ismobile": "false", "systemtype": "",
    })

    response = session.post(
        "https://my.te.eg/echannel/service/besapp/base/rest/busiservice/v1/auth/userAuthenticate",
        json=loginPayload
    )
    login = response.json()

    try:
        csrf = login["body"]["token"]
    except KeyError:
        raise Exception("Login failed: invalid credentials or blocked")

    session.headers.update({"csrftoken": csrf})
    subscriberId = login["body"]["subscriber"]["subscriberId"]

    offersPayload = {"msisdn": acctId, "numberServiceType": "FBB", "groupId": ""}
    response = session.post("https://my.te.eg/echannel/service/besapp/base/rest/busiservice/cz/v1/auth/getSubscribedOfferings", json=offersPayload)
    mainOfferId = response.json()["body"]["offeringList"][0]["mainOfferingId"]

    session_data = {
        "cookies": session.cookies.get_dict(),
        "headers": dict(session.headers),
        "subscriberId": subscriberId,
        "mainOfferId": mainOfferId
    }

    with open(SESSION_FILE, "w") as f:
        json.dump(session_data, f)

    return session_data

def fetch_quota(session_data):
    session = requests.Session()
    session.cookies.update(session_data["cookies"])
    session.headers.update(session_data["headers"])

    quotaPayload = {
        "subscriberId": session_data["subscriberId"],
        "needQueryPoint": "true",
        "mainOfferId": session_data["mainOfferId"],
    }

    try:
        response = session.post("https://my.te.eg/echannel/service/besapp/base/rest/busiservice/cz/cbs/bb/queryFreeUnit", json=quotaPayload)
        quota = response.json()

        if "body" not in quota or not quota["body"]:
            return None

        used   = sum(float(item.get('used', 0)) for item in quota['body'])
        remain = sum(float(item.get('actualRemain', 0)) for item in quota['body'])
        total  = sum(float(item.get('total', 0)) for item in quota['body'])

        if total == 0 and (used + remain) > 0:
            total = used + remain

        return {"used": used, "remain": remain, "total": total}
    except Exception:
        return None

def log_usage(used, remain, total):
    now = time.time()
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                logs = json.load(f)
        else:
            logs = []
    except Exception:
        logs = []

    logs.append({"timestamp": now, "used": used, "remain": remain, "total": total})
    logs = [log for log in logs if log["timestamp"] >= now - 86400]

    with open(LOG_FILE, "w") as f:
        json.dump(logs, f)

    return logs

def get_used_last_30_mins(logs):
    if not logs:
        return 0.0
    now = time.time()
    cutoff = now - 1800
    current_used = float(logs[-1].get("used", 0))

    old_used = None
    for log in reversed(logs):
        if log.get("timestamp", 0) <= cutoff:
            old_used = float(log.get("used", 0))
            break

    if old_used is None:
        old_used = float(logs[0].get("used", 0))

    diff = current_used - old_used
    if diff < 0:
        diff = max(0.0, current_used)

    return round(max(0.0, diff), 2)


# ---------------------------------------------------------------------------
# Clipboard and Entry Interaction Helpers (Robust Windows support)
# ---------------------------------------------------------------------------

def get_clipboard_text() -> str:
    """Reads unicode text directly from Windows clipboard with Tkinter fallback."""
    # 1. Try Windows user32 clipboard API (CF_UNICODETEXT)
    try:
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32

        u32.OpenClipboard.argtypes = [wintypes.HWND]
        u32.OpenClipboard.restype = wintypes.BOOL
        u32.CloseClipboard.argtypes = []
        u32.CloseClipboard.restype = wintypes.BOOL
        u32.GetClipboardData.argtypes = [wintypes.UINT]
        u32.GetClipboardData.restype = wintypes.HANDLE

        k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalLock.restype = wintypes.LPCWSTR
        k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalUnlock.restype = wintypes.BOOL

        CF_UNICODETEXT = 13
        if u32.OpenClipboard(None):
            try:
                h_clip = u32.GetClipboardData(CF_UNICODETEXT)
                if h_clip:
                    text_ptr = k32.GlobalLock(h_clip)
                    if text_ptr:
                        text = str(text_ptr)
                        k32.GlobalUnlock(h_clip)
                        return text
            finally:
                u32.CloseClipboard()
    except Exception:
        pass

    # 2. Fallback to Tkinter clipboard
    try:
        root_w = tk._default_root
        if root_w:
            return root_w.clipboard_get()
    except Exception:
        pass

    return ""

def set_clipboard_text(text: str):
    """Writes unicode text directly to Windows clipboard with Tkinter fallback."""
    try:
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32

        u32.OpenClipboard.argtypes = [wintypes.HWND]
        u32.OpenClipboard.restype = wintypes.BOOL
        u32.CloseClipboard.argtypes = []
        u32.CloseClipboard.restype = wintypes.BOOL
        u32.EmptyClipboard.argtypes = []
        u32.EmptyClipboard.restype = wintypes.BOOL
        u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        u32.SetClipboardData.restype = wintypes.HANDLE

        k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        k32.GlobalAlloc.restype = wintypes.HGLOBAL
        k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalUnlock.restype = wintypes.BOOL

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002
        if u32.OpenClipboard(None):
            try:
                u32.EmptyClipboard()
                encoded = (text + "\0").encode("utf-16le")
                h_mem = k32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
                if h_mem:
                    ptr = k32.GlobalLock(h_mem)
                    if ptr:
                        ctypes.memmove(ptr, encoded, len(encoded))
                        k32.GlobalUnlock(h_mem)
                        u32.SetClipboardData(CF_UNICODETEXT, h_mem)
            finally:
                u32.CloseClipboard()
            return
    except Exception:
        pass

    try:
        root_w = tk._default_root
        if root_w:
            root_w.clipboard_clear()
            root_w.clipboard_append(text)
            root_w.update()
    except Exception:
        pass

def record_entry_state(entry: tk.Entry):
    """Records current text state into the undo stack if it has changed."""
    if getattr(entry, "_is_undo_redo", False):
        return
    text = entry.get()
    pos = entry.index(tk.INSERT)
    if not hasattr(entry, "_undo_stack"):
        entry._undo_stack = [(text, pos)]
        entry._redo_stack = []
        entry._is_undo_redo = False
        return

    if not entry._undo_stack or entry._undo_stack[-1][0] != text:
        entry._undo_stack.append((text, pos))
        if len(entry._undo_stack) > 50:
            entry._undo_stack.pop(0)
        entry._redo_stack.clear()

def undo_entry(entry: tk.Entry):
    """Reverts the Entry widget to the previous state in the undo stack."""
    if not hasattr(entry, "_undo_stack"):
        return "break"
    if len(entry._undo_stack) > 1:
        entry._is_undo_redo = True
        try:
            cur = entry._undo_stack.pop()
            entry._redo_stack.append(cur)
            prev_text, prev_pos = entry._undo_stack[-1]
            entry.delete(0, tk.END)
            entry.insert(0, prev_text)
            entry.icursor(min(prev_pos, len(prev_text)))
        finally:
            entry._is_undo_redo = False
    return "break"

def redo_entry(entry: tk.Entry):
    """Restores the next state from the redo stack."""
    if not hasattr(entry, "_redo_stack"):
        return "break"
    if entry._redo_stack:
        entry._is_undo_redo = True
        try:
            next_text, next_pos = entry._redo_stack.pop()
            entry._undo_stack.append((next_text, next_pos))
            entry.delete(0, tk.END)
            entry.insert(0, next_text)
            entry.icursor(min(next_pos, len(next_text)))
        finally:
            entry._is_undo_redo = False
    return "break"

def paste_into_entry(entry: tk.Entry):
    """Pastes clipboard text into the Entry widget at insertion or replacing selection."""
    text = get_clipboard_text()
    if not text:
        return "break"
    clean_text = text.replace("\r\n", "").replace("\n", "").replace("\r", "")
    try:
        first = entry.index(tk.SEL_FIRST)
        last = entry.index(tk.SEL_LAST)
        entry.delete(first, last)
    except tk.TclError:
        pass
    entry.insert(tk.INSERT, clean_text)
    entry.focus_set()
    record_entry_state(entry)
    return "break"

def copy_from_entry(entry: tk.Entry):
    """Copies current selection from Entry widget to clipboard."""
    try:
        first = entry.index(tk.SEL_FIRST)
        last = entry.index(tk.SEL_LAST)
        selected_text = entry.get()[first:last]
        if selected_text:
            set_clipboard_text(selected_text)
    except tk.TclError:
        pass
    return "break"

def cut_from_entry(entry: tk.Entry):
    """Cuts current selection from Entry widget to clipboard."""
    try:
        first = entry.index(tk.SEL_FIRST)
        last = entry.index(tk.SEL_LAST)
        selected_text = entry.get()[first:last]
        if selected_text:
            set_clipboard_text(selected_text)
            entry.delete(first, last)
            record_entry_state(entry)
    except tk.TclError:
        pass
    return "break"

def select_all_in_entry(entry: tk.Entry):
    """Selects all text in the Entry widget."""
    entry.select_range(0, tk.END)
    entry.icursor(tk.END)
    entry.focus_set()
    return "break"

def clear_entry(entry: tk.Entry):
    """Clears all text from the Entry widget and records undo state."""
    entry.delete(0, tk.END)
    record_entry_state(entry)
    return "break"

def setup_entry_copy_paste(entry: tk.Entry):
    """Enables robust undo/redo, copy/paste across all keyboard layouts and context menu."""
    entry._undo_stack = [(entry.get(), entry.index(tk.INSERT))]
    entry._redo_stack = []
    entry._is_undo_redo = False

    entry.config(
        selectbackground="#8c7ae6",
        selectforeground="#ffffff",
        exportselection=False
    )

    def on_key_press(event):
        ctrl_pressed = bool(event.state & 0x0004)
        shift_pressed = bool(event.state & 0x0001)

        # Layout-agnostic virtual key codes and chars
        # VK_V = 86, VK_C = 67, VK_X = 88, VK_A = 65, VK_Z = 90, VK_Y = 89, VK_INSERT = 45
        if ctrl_pressed:
            if event.keycode == 90 or event.keysym in ("z", "Z") or event.char == "\x1a":
                if shift_pressed:
                    return redo_entry(entry)
                return undo_entry(entry)
            elif event.keycode == 89 or event.keysym in ("y", "Y") or event.char == "\x19":
                return redo_entry(entry)
            elif event.keycode == 86 or event.keysym in ("v", "V") or event.char == "\x16":
                return paste_into_entry(entry)
            elif event.keycode == 67 or event.keysym in ("c", "C") or event.char == "\x03":
                return copy_from_entry(entry)
            elif event.keycode == 88 or event.keysym in ("x", "X") or event.char == "\x18":
                return cut_from_entry(entry)
            elif event.keycode == 65 or event.keysym in ("a", "A") or event.char == "\x01":
                return select_all_in_entry(entry)

        if shift_pressed and event.keycode == 45:
            return paste_into_entry(entry)

        return None

    def on_key_release(event):
        if event.keysym not in ("Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Caps_Lock", "Left", "Right", "Up", "Down"):
            record_entry_state(entry)

    entry.bind("<KeyPress>", on_key_press, add="+")
    entry.bind("<KeyRelease>", on_key_release, add="+")

    # Dark-themed context menu
    menu = tk.Menu(entry, tearoff=0, bg="#1c1f2e", fg="#f5f6fa",
                   activebackground="#8c7ae6", activeforeground="#ffffff",
                   relief=tk.FLAT, bd=1, font=("Segoe UI", 9))
    menu.add_command(label="Undo", command=lambda: undo_entry(entry), accelerator="Ctrl+Z")
    menu.add_command(label="Redo", command=lambda: redo_entry(entry), accelerator="Ctrl+Y")
    menu.add_separator()
    menu.add_command(label="Cut", command=lambda: cut_from_entry(entry), accelerator="Ctrl+X")
    menu.add_command(label="Copy", command=lambda: copy_from_entry(entry), accelerator="Ctrl+C")
    menu.add_command(label="Paste", command=lambda: paste_into_entry(entry), accelerator="Ctrl+V")
    menu.add_separator()
    menu.add_command(label="Select All", command=lambda: select_all_in_entry(entry), accelerator="Ctrl+A")
    menu.add_command(label="Clear", command=lambda: clear_entry(entry))

    def show_context_menu(event):
        entry.focus_set()
        # Undo / Redo states
        has_undo = hasattr(entry, "_undo_stack") and len(entry._undo_stack) > 1
        has_redo = hasattr(entry, "_redo_stack") and bool(entry._redo_stack)
        menu.entryconfig("Undo", state="normal" if has_undo else "disabled")
        menu.entryconfig("Redo", state="normal" if has_redo else "disabled")

        try:
            has_sel = entry.selection_present()
        except Exception:
            has_sel = False

        state_sel = "normal" if has_sel else "disabled"
        menu.entryconfig("Cut", state=state_sel)
        menu.entryconfig("Copy", state=state_sel)

        has_clip = bool(get_clipboard_text().strip())
        menu.entryconfig("Paste", state="normal" if has_clip else "disabled")

        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    entry.bind("<Button-3>", show_context_menu)


# ---------------------------------------------------------------------------
# Settings Dialog
# ---------------------------------------------------------------------------

class SettingsDialog(tk.Toplevel):
    """Dark-themed modal dialog to edit config.json fields."""

    BG      = "#0f1117"
    SURFACE = "#1c1f2e"
    FG      = "#f5f6fa"
    SUB     = "#a4b0be"
    ACCENT  = "#8c7ae6"
    DANGER  = "#e84118"
    BORDER  = "#2f3640"

    def __init__(self, parent, on_save_callback=None, on_close_callback=None):
        super().__init__(parent)
        self.parent = parent
        self.on_save_callback = on_save_callback
        self.on_close_callback = on_close_callback

        self.overrideredirect(True)
        self.configure(bg=self.BG)
        self.resizable(False, False)
        self.transient(parent)            # Keep tied to main app window
        self.attributes("-topmost", True) # Always in front of app and desktop
        self.grab_set()                  # Modal
        self.lift()
        self.focus_force()

        self._build_ui()
        self._position_dialog(parent)

        # Allow dragging the dialog
        self._drag_x = self._drag_y = 0
        self._title_bar.bind("<ButtonPress-1>",   self._drag_start)
        self._title_bar.bind("<B1-Motion>",        self._drag_motion)
        self._title_lbl.bind("<ButtonPress-1>",   self._drag_start)
        self._title_lbl.bind("<B1-Motion>",        self._drag_motion)
        self.bind("<Escape>", lambda _: self.destroy())

    def destroy(self):
        try:
            self.grab_release()
        except Exception:
            pass
        if self.on_close_callback:
            try:
                self.on_close_callback()
            except Exception:
                pass
        super().destroy()

    # ------------------------------------------------------------------
    def _build_ui(self):
        W = 350

        # ── Title bar ──────────────────────────────────────────────────
        self._title_bar = tk.Frame(self, bg=self.SURFACE, height=36, width=W)
        self._title_bar.pack(fill=tk.X)
        self._title_bar.pack_propagate(False)

        self.gear_img_dialog = ImageTk.PhotoImage(create_gear_image(16, "#f5f6fa"))
        self._title_lbl = tk.Label(
            self._title_bar, text=" Settings", image=self.gear_img_dialog,
            compound=tk.LEFT, fg=self.FG, bg=self.SURFACE,
            font=("Segoe UI", 10, "bold"), anchor="w"
        )
        self._title_lbl.place(x=12, y=8)

        btn_close = tk.Label(
            self._title_bar, text="✕", fg=self.SUB, bg=self.SURFACE,
            font=("Segoe UI", 10), cursor="hand2"
        )
        btn_close.place(x=W - 28, y=8)
        btn_close.bind("<Button-1>", lambda _: self.destroy())
        btn_close.bind("<Enter>",    lambda _: btn_close.config(fg=self.DANGER))
        btn_close.bind("<Leave>",    lambda _: btn_close.config(fg=self.SUB))

        # ── Separator ─────────────────────────────────────────────────
        tk.Frame(self, bg=self.BORDER, height=1).pack(fill=tk.X)

        # ── Body ───────────────────────────────────────────────────────
        body = tk.Frame(self, bg=self.BG, padx=20, pady=16)
        body.pack(fill=tk.BOTH, expand=True)

        cfg = load_config()

        fields = [
            ("Landline Number",   "LANDLINE",       False),
            ("WE Password",       "MY_WE_PASSWORD",  True),
            ("Google API Key",    "GOOGLE_API_KEY",  True),
        ]

        self._vars = {}
        self._show_vars = {}

        for label_text, key, secret in fields:
            # Label
            tk.Label(body, text=label_text, fg=self.SUB, bg=self.BG,
                     font=("Segoe UI", 8), anchor="w").pack(fill=tk.X, pady=(8, 2))

            row = tk.Frame(body, bg=self.BG)
            row.pack(fill=tk.X)

            var = tk.StringVar(value=cfg.get(key, ""))
            self._vars[key] = var

            show = "" if not secret else "•"
            entry = tk.Entry(
                row, textvariable=var, show=show,
                bg=self.SURFACE, fg=self.FG, insertbackground=self.FG,
                relief=tk.FLAT, font=("Segoe UI", 10),
                highlightthickness=1, highlightbackground=self.BORDER,
                highlightcolor=self.ACCENT
            )
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 4))
            setup_entry_copy_paste(entry)

            if secret:
                sv = tk.BooleanVar(value=False)
                self._show_vars[key] = sv

                def _toggle(e=entry, sv=sv):
                    sv.set(not sv.get())
                    e.config(show="" if sv.get() else "•")

                eye = tk.Label(row, text="👁", fg=self.SUB, bg=self.BG,
                               cursor="hand2", font=("Segoe UI", 10), padx=3)
                eye.pack(side=tk.LEFT)
                eye.bind("<Button-1>", lambda _, t=_toggle: t())
                eye.bind("<Enter>",    lambda _, b=eye: b.config(fg=self.FG))
                eye.bind("<Leave>",    lambda _, b=eye: b.config(fg=self.SUB))

            paste_btn = tk.Label(row, text="📋", fg=self.SUB, bg=self.BG,
                                 cursor="hand2", font=("Segoe UI", 10), padx=3)
            paste_btn.pack(side=tk.LEFT)
            paste_btn.bind("<Button-1>", lambda _, e=entry: paste_into_entry(e))
            paste_btn.bind("<Enter>",    lambda _, b=paste_btn: b.config(fg=self.FG))
            paste_btn.bind("<Leave>",    lambda _, b=paste_btn: b.config(fg=self.SUB))

        # ── Info note ──────────────────────────────────────────────────
        tk.Label(
            body,
            text="Changes take effect on next login / refresh.",
            fg=self.SUB, bg=self.BG, font=("Segoe UI", 7, "italic")
        ).pack(pady=(14, 0))

        # ── Buttons ────────────────────────────────────────────────────
        btn_row = tk.Frame(body, bg=self.BG)
        btn_row.pack(fill=tk.X, pady=(14, 0))

        cancel_btn = tk.Button(
            btn_row, text="Cancel", command=self.destroy,
            bg=self.SURFACE, fg=self.SUB, relief=tk.FLAT,
            font=("Segoe UI", 9), padx=16, pady=6,
            cursor="hand2", activebackground=self.BORDER,
            activeforeground=self.FG, borderwidth=0
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(6, 0))

        save_btn = tk.Button(
            btn_row, text="Save", command=self._save,
            bg=self.ACCENT, fg="white", relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"), padx=20, pady=6,
            cursor="hand2", activebackground="#7b6bd4",
            activeforeground="white", borderwidth=0
        )
        save_btn.pack(side=tk.RIGHT)

    # ------------------------------------------------------------------
    def _save(self):
        cfg = load_config()
        for key, var in self._vars.items():
            cfg[key] = var.get().strip()

        if not cfg["LANDLINE"]:
            messagebox.showerror("Validation", "Landline cannot be empty.", parent=self)
            return
        if not cfg["MY_WE_PASSWORD"]:
            messagebox.showerror("Validation", "Password cannot be empty.", parent=self)
            return

        save_config(cfg)
        _apply_config(cfg)

        if self.on_save_callback:
            self.on_save_callback()

        self.destroy()

    # ------------------------------------------------------------------
    def _position_dialog(self, parent):
        self.update_idletasks()
        pw = parent.winfo_rootx()
        py = parent.winfo_rooty()
        ph = parent.winfo_height()
        pw_w = parent.winfo_width()
        dw = self.winfo_reqwidth()
        dh = self.winfo_reqheight()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        x = pw + (pw_w - dw) // 2
        y = py + (ph - dh) // 2

        margin = 16
        if x + dw > screen_w - margin:
            x = screen_w - dw - margin
        if x < margin:
            x = margin
        if y + dh > screen_h - margin:
            y = screen_h - dh - margin
        if y < margin:
            y = margin

        self.geometry(f"+{x}+{y}")

    def _drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_motion(self, event):
        dx = event.x - self._drag_x
        dy = event.y - self._drag_y
        x = self.winfo_x() + dx
        y = self.winfo_y() + dy
        self.geometry(f"+{x}+{y}")


# ---------------------------------------------------------------------------
# Main Widget
# ---------------------------------------------------------------------------

class QuotaWidget:
    def __init__(self, root):
        self.root = root
        self.root.title("WE Quota Tracker")
        self.root.overrideredirect(True)   # Borderless window
        self.root.geometry("260x340")

        self.is_dragging      = False
        self.is_refreshing    = False
        self.is_settings_open = False
        self.after_id         = None

        # Position at TOP RIGHT corner with slight padding
        screen_width  = self.root.winfo_screenwidth()
        self.start_x  = screen_width - 280
        self.start_y  = 20
        self.reset_position()

        # Modern Dark Theme Colors
        self.bg_color     = "#151821"
        self.fg_color     = "#f5f6fa"
        self.accent_color = "#8c7ae6"
        self.arc_bg       = "#2f3640"
        self.sub_text     = "#a4b0be"

        self.root.configure(bg=self.bg_color)

        # ── Top bar buttons ───────────────────────────────────────────
        self.gear_img_sub   = ImageTk.PhotoImage(create_gear_image(16, "#a4b0be"))
        self.gear_img_white = ImageTk.PhotoImage(create_gear_image(16, "#ffffff"))

        # Settings gear icon button (top right)
        self.btn_settings = tk.Button(
            root, image=self.gear_img_sub, command=self.open_settings,
            bg=self.bg_color, activebackground=self.accent_color,
            borderwidth=0, cursor="hand2", width=22, height=22
        )
        self.btn_settings.bind("<Enter>", lambda _: self.btn_settings.config(image=self.gear_img_white))
        self.btn_settings.bind("<Leave>", lambda _: self.btn_settings.config(image=self.gear_img_sub))
        self.btn_settings.place(x=205, y=6, width=22, height=22)

        # Close (hides to tray)
        self.btn_exit = tk.Button(
            root, text="✕", command=self.hide_window,
            bg=self.bg_color, fg=self.sub_text,
            activebackground="#e84118", activeforeground="white",
            borderwidth=0, font=("Segoe UI", 10), cursor="hand2"
        )
        self.btn_exit.place(x=232, y=6, width=22, height=22)

        self.lbl_title = tk.Label(root, text="WE Quota Tracker", fg=self.fg_color, bg=self.bg_color, font=("Segoe UI", 11, "bold"))
        self.lbl_title.pack(pady=(12, 0))

        self.canvas = tk.Canvas(self.root, width=260, height=170, bg=self.bg_color, highlightthickness=0)
        self.canvas.pack()

        self.cx, self.cy = 130, 85
        self.r = 65

        self.canvas.create_oval(self.cx-self.r, self.cy-self.r, self.cx+self.r, self.cy+self.r, outline=self.arc_bg, width=12)
        self.arc = self.canvas.create_arc(self.cx-self.r, self.cy-self.r, self.cx+self.r, self.cy+self.r, start=90, extent=0, outline=self.accent_color, width=12, style=tk.ARC)

        self.lbl_gb         = self.canvas.create_text(self.cx, self.cy-10, text="-- GB",       fill=self.fg_color, font=("Segoe UI", 20, "bold"))
        self.lbl_remain_of  = self.canvas.create_text(self.cx, self.cy+15, text="Remaining of", fill=self.sub_text, font=("Segoe UI", 9))
        self.lbl_total      = self.canvas.create_text(self.cx, self.cy+30, text="-- GB",       fill=self.fg_color, font=("Segoe UI", 9, "bold"))

        self.lbl_recent = tk.Label(self.root, text="", fg="#e1b12c", bg=self.bg_color, font=("Segoe UI", 9))
        self.lbl_recent.pack(pady=(2, 0))

        self.lbl_timestamp = tk.Label(self.root, text="Not updated yet", fg=self.sub_text, bg=self.bg_color, font=("Segoe UI", 8))
        self.lbl_timestamp.pack(pady=(2, 0))

        # Action button centered in the widget: "Refresh" when active, "Relogin" when session expired
        self.btn_refresh = tk.Button(
            self.root, text="Refresh", command=self.manual_refresh,
            bg="#8c7ae6", fg="white", borderwidth=0, padx=20, pady=5,
            cursor="hand2", font=("Segoe UI", 9, "bold"),
            activebackground="#7b6bd4", activeforeground="white"
        )
        self.btn_refresh.pack(pady=(8, 4))

        self.lbl_footer = tk.Label(self.root, text="Created by SPY", fg=self.sub_text, bg=self.bg_color, font=("Segoe UI", 8, "italic"))
        self.lbl_footer.pack(side=tk.BOTTOM, pady=(0, 6))

        for widget in (self.root, self.canvas, self.lbl_title, self.lbl_recent, self.lbl_timestamp, self.lbl_footer):
            widget.bind("<ButtonPress-1>",   self.start_move)
            widget.bind("<ButtonRelease-1>", self.stop_move)
            widget.bind("<B1-Motion>",       self.on_motion)

        self.x = 0
        self.y = 0

        # If config is incomplete, open settings first; otherwise start refreshing
        cfg = load_config()
        if not cfg.get("LANDLINE") or not cfg.get("MY_WE_PASSWORD"):
            self.root.after(300, self.open_settings)
        else:
            self.schedule_refresh(0)

        self.setup_tray_icon()

    # ── Position ──────────────────────────────────────────────────────
    def reset_position(self):
        self.root.geometry(f"+{self.start_x}+{self.start_y}")

    # ── Settings ──────────────────────────────────────────────────────
    def open_settings(self):
        self.is_settings_open = True
        SettingsDialog(self.root, on_save_callback=self._on_settings_saved, on_close_callback=self._on_settings_closed)

    def _on_settings_closed(self):
        self.is_settings_open = False

    def _on_settings_saved(self):
        """Called after the user saves settings — kick off a fresh refresh."""
        # Clear stale session so we re-login with new creds
        if os.path.exists(SESSION_FILE):
            try:
                os.remove(SESSION_FILE)
            except Exception:
                pass
        self.schedule_refresh(0)

    # ── Window Show/Hide ──────────────────────────────────────────────
    def show_window(self):
        self.root.after(0, self.root.deiconify)

    def hide_window(self):
        self.root.withdraw()

    def toggle_window(self):
        if self.root.winfo_viewable():
            self.hide_window()
        else:
            self.show_window()

    def exit_app(self):
        if os.path.exists(LOCK_FILE):
            try:
                os.remove(LOCK_FILE)
            except Exception:
                pass
        self.tray_icon.stop()
        self.root.after(0, self.root.destroy)

    # ── Tray Icon ─────────────────────────────────────────────────────
    def create_tray_image(self):
        width = height = 64
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.ellipse((4, 4, width-4, height-4), fill='#8c7ae6', outline='#151821', width=3)
        return image

    def setup_tray_icon(self):
        menu = (
            item('Show / Hide',    self.toggle_window, default=True),
            item('Settings',       lambda: self.root.after(0, self.open_settings)),
            item('Reset Position', lambda: self.root.after(0, self.reset_position)),
            item('Exit',           lambda: self.root.after(0, self.exit_app))
        )
        image = self.create_tray_image()
        self.tray_icon = pystray.Icon("WE Quota Tracker", image, "WE Quota Tracker", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    # ── Drag ──────────────────────────────────────────────────────────
    def start_move(self, event):
        self.is_dragging = True
        self.x = event.x
        self.y = event.y

    def stop_move(self, event):
        self.is_dragging = False
        self.x = self.y = None

    def on_motion(self, event):
        if self.x is not None and self.y is not None:
            x = self.root.winfo_x() + (event.x - self.x)
            y = self.root.winfo_y() + (event.y - self.y)
            self.root.geometry(f"+{x}+{y}")

    # ── Refresh logic ─────────────────────────────────────────────────
    def manual_refresh(self):
        if self.is_refreshing:
            return
        if self.btn_refresh.cget("text") in ("Relogin", "Re-login") or not os.path.exists(SESSION_FILE):
            self.do_relogin()
            return

        self.is_refreshing = True
        self.lbl_timestamp.config(text="Refreshing...")
        self.btn_refresh.config(state="disabled", text="Refreshing...")
        self.refresh_job()

    def do_relogin(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.is_refreshing = True
        self.btn_refresh.config(state="disabled", text="Logging in...")
        self.canvas.itemconfig(self.lbl_gb,        text="Login...")
        self.canvas.itemconfig(self.lbl_remain_of, text="Solving")
        self.canvas.itemconfig(self.lbl_total,     text="Captcha...")
        self.lbl_timestamp.config(text="Authenticating...")

        def login_thread():
            try:
                session_data = perform_login()
                self.root.after(0, self.on_login_success, session_data)
            except Exception as e:
                self.root.after(0, self.on_login_fail, str(e))

        threading.Thread(target=login_thread, daemon=True).start()

    def on_login_success(self, session_data):
        self.canvas.itemconfig(self.lbl_gb,        text="Success")
        self.canvas.itemconfig(self.lbl_remain_of, text="")
        self.canvas.itemconfig(self.lbl_total,     text="Fetching...")
        self.lbl_timestamp.config(text="Fetching quota...")
        self.refresh_job()

    def on_login_fail(self, error_msg):
        self.is_refreshing = False
        if os.path.exists(SESSION_FILE):
            try:
                os.remove(SESSION_FILE)
            except Exception:
                pass
        self.btn_refresh.config(state="normal", text="Relogin")
        self.canvas.itemconfig(self.lbl_gb,        text="Failed")
        self.canvas.itemconfig(self.lbl_remain_of, text="Click Relogin")
        self.canvas.itemconfig(self.lbl_total,     text="to retry.")
        self.lbl_timestamp.config(text="Login failed")
        safe_print(f"Login failed: {error_msg}")

    def schedule_refresh(self, delay_ms=120000):
        if self.after_id:
            self.root.after_cancel(self.after_id)
        self.after_id = self.root.after(delay_ms, self.refresh_job)

    def refresh_job(self):
        if not os.path.exists(SESSION_FILE):
            self.do_relogin()
            return

        try:
            with open(SESSION_FILE, "r") as f:
                session_data = json.load(f)
        except Exception:
            self.do_relogin()
            return

        def fetch_thread():
            data = fetch_quota(session_data)
            self.root.after(0, self.on_fetch_done, data)

        threading.Thread(target=fetch_thread, daemon=True).start()

    def on_fetch_done(self, data):
        self.is_refreshing = False
        now_str = time.strftime("%I:%M:%S %p")

        if data is None:
            if os.path.exists(SESSION_FILE):
                try:
                    os.remove(SESSION_FILE)
                except Exception:
                    pass
            self.btn_refresh.config(state="normal", text="Relogin")
            self.canvas.itemconfig(self.lbl_gb,        text="Expired")
            self.canvas.itemconfig(self.lbl_remain_of, text="")
            self.canvas.itemconfig(self.lbl_total,     text="Need login")
            self.lbl_recent.config(text="")
            self.lbl_timestamp.config(text=f"Expired at {now_str}")
            self.canvas.itemconfig(self.arc, extent=0)
            safe_print("Session expired, button changed to Relogin.")
        else:
            self.btn_refresh.config(state="normal", text="Refresh")
            used   = data['used']
            remain = data['remain']
            total  = data['total']

            logs    = log_usage(used, remain, total)
            used_30 = get_used_last_30_mins(logs)

            self.canvas.itemconfig(self.lbl_gb,        text=f"{remain:.2f} GB")
            self.canvas.itemconfig(self.lbl_remain_of, text="Remaining of")
            self.canvas.itemconfig(self.lbl_total,     text=f"{total:.0f} GB")

            self.lbl_recent.config(text=f"In the last 30 min used {used_30} GB")
            self.lbl_timestamp.config(text=f"Updated: {now_str}")

            if total > 0:
                fraction = max(0.0, min(1.0, remain / total))
                extent = -360.0 * fraction
                if abs(extent) < 0.001:
                    extent = 0.0001
                self.canvas.itemconfig(self.arc, extent=extent)

            self.schedule_refresh(120000)


# ---------------------------------------------------------------------------
# Single Instance Management
# ---------------------------------------------------------------------------

LOCK_FILE = os.path.join(BASE_DIR, "app.lock")
_MUTEX_HANDLE = None

def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_INFORMATION = 0x0400
        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False

def find_pid_by_process_name() -> int:
    current_pid = os.getpid()
    try:
        import subprocess
        out = subprocess.check_output('tasklist /FI "IMAGENAME eq WEQuota.exe" /FO CSV /NH', shell=True, text=True)
        for line in out.splitlines():
            parts = line.split('","')
            if len(parts) >= 2:
                pid_str = parts[1].replace('"', '').strip()
                if pid_str.isdigit():
                    pid = int(pid_str)
                    if pid != current_pid:
                        return pid
    except Exception:
        pass
    return None

def get_running_instance_pid():
    current_pid = os.getpid()
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            if pid != current_pid and is_pid_running(pid):
                return pid
        except Exception:
            pass

    global _MUTEX_HANDLE
    try:
        kernel32 = ctypes.windll.kernel32
        _MUTEX_HANDLE = kernel32.CreateMutexW(None, True, "WE_Quota_Tracker_Single_Instance_Mutex")
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            pid = find_pid_by_process_name()
            return pid if pid else -1
    except Exception:
        pass

    return None

def kill_instance(pid):
    if pid and pid > 0:
        try:
            import subprocess
            subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
            time.sleep(0.5)
        except Exception:
            pass

    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
        except Exception:
            pass

def create_app_lock():
    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

class SingleInstanceDialog(tk.Toplevel):
    """Dark-themed popup asking user to kill running instance or exit."""
    def __init__(self, parent, pid=None):
        super().__init__(parent)
        self.pid = pid
        self.action = "exit"

        self.overrideredirect(True)
        self.configure(bg="#0f1117")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.grab_set()
        self.focus_force()

        W, H = 360, 185

        tbar = tk.Frame(self, bg="#1c1f2e", height=36, width=W)
        tbar.pack(fill=tk.X)
        tbar.pack_propagate(False)

        lbl_title = tk.Label(tbar, text=" WE Quota Tracker — Already Running", fg="#f5f6fa", bg="#1c1f2e", font=("Segoe UI", 10, "bold"))
        lbl_title.pack(side=tk.LEFT, padx=12, pady=8)

        tk.Frame(self, bg="#2f3640", height=1).pack(fill=tk.X)

        body = tk.Frame(self, bg="#0f1117", padx=20, pady=16)
        body.pack(fill=tk.BOTH, expand=True)

        msg = "An instance of WE Quota Tracker is already running."
        if pid and pid > 0:
            msg += f" (PID {pid})"
        msg += "\n\nWould you like to kill the running instance and start this one, or exit?"

        lbl_msg = tk.Label(body, text=msg, fg="#a4b0be", bg="#0f1117", font=("Segoe UI", 9), justify=tk.LEFT, wraplength=310)
        lbl_msg.pack(fill=tk.X, pady=(0, 14))

        btn_row = tk.Frame(body, bg="#0f1117")
        btn_row.pack(fill=tk.X)

        exit_btn = tk.Button(
            btn_row, text="Exit", command=self._on_exit,
            bg="#1c1f2e", fg="#a4b0be", relief=tk.FLAT,
            font=("Segoe UI", 9), padx=16, pady=5,
            cursor="hand2", borderwidth=0, activebackground="#2f3640", activeforeground="#f5f6fa"
        )
        exit_btn.pack(side=tk.RIGHT, padx=(6, 0))

        kill_btn = tk.Button(
            btn_row, text="Kill Existing & Start", command=self._on_kill,
            bg="#e84118", fg="white", relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"), padx=14, pady=5,
            cursor="hand2", activebackground="#c23616", activeforeground="white"
        )
        kill_btn.pack(side=tk.RIGHT)

        self._center_on_screen(W, H)

    def _on_kill(self):
        self.action = "kill"
        self.destroy()

    def _on_exit(self):
        self.action = "exit"
        self.destroy()

    def _center_on_screen(self, w, h):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

def check_single_instance(root):
    existing_pid = get_running_instance_pid()
    if existing_pid is None:
        create_app_lock()
        return True

    dialog = SingleInstanceDialog(root, pid=existing_pid)
    root.wait_window(dialog)

    if dialog.action == "kill":
        kill_instance(existing_pid)
        create_app_lock()
        return True
    else:
        return False


# ---------------------------------------------------------------------------
# Desktop-pinning helper (stay below other windows unless dragged)
# ---------------------------------------------------------------------------

def keep_desktop_behavior(root, app):
    try:
        if getattr(app, "is_settings_open", False):
            # Pause toggling while settings modal dialog is active
            root.after(150, lambda: keep_desktop_behavior(root, app))
            return

        user32 = ctypes.windll.user32

        if getattr(app, "is_dragging", False):
            root.attributes("-topmost", True)
        else:
            fg_hwnd = user32.GetForegroundWindow()
            class_name_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(fg_hwnd, class_name_buf, 256)
            class_name = class_name_buf.value

            if class_name in ("Progman", "WorkerW"):
                root.attributes("-topmost", True)
            else:
                root.attributes("-topmost", False)
    except Exception:
        pass

    root.after(150, lambda: keep_desktop_behavior(root, app))


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()

    if not check_single_instance(root):
        root.destroy()
        sys.exit(0)

    app = QuotaWidget(root)
    root.deiconify()
    keep_desktop_behavior(root, app)
    root.mainloop()