import time
import json
import os
import sys
import threading
import math
import ctypes
from ctypes import wintypes
import gzip
import http.cookiejar
import urllib.request
import urllib.parse
import urllib.error
import tkinter as tk
from tkinter import messagebox

try:
    from src.capsolver import solveCaptcha
except ImportError:
    from capsolver import solveCaptcha

# Enable high-DPI awareness on Windows to prevent blurry text and coordinate scaling glitches
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Win32 Native Types & Helpers for System Tray (Replacing pystray & PIL)
# ---------------------------------------------------------------------------

user32   = ctypes.windll.user32
shell32  = ctypes.windll.shell32
gdi32    = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype  = ctypes.c_ssize_t
user32.PostMessageW.argtypes   = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype    = wintypes.BOOL

NIM_ADD     = 0x00000000
NIM_MODIFY  = 0x00000001
NIM_DELETE  = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON    = 0x00000002
NIF_TIP     = 0x00000004

WM_NULL          = 0x0000
WM_DESTROY       = 0x0002
WM_CLOSE         = 0x0010
WM_LBUTTONUP     = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP     = 0x0205
WM_CONTEXTMENU   = 0x007B
WM_USER          = 0x0400
WM_TRAY_MSG      = WM_USER + 42


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HICON),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


def create_native_tray_icon():
    """Generates an in-memory purple circular HICON using Win32 GDI without external files."""
    width, height = 16, 16
    hdc = user32.GetDC(0)
    memdc = gdi32.CreateCompatibleDC(hdc)
    hbm_color = gdi32.CreateCompatibleBitmap(hdc, width, height)
    hbm_mask = gdi32.CreateBitmap(width, height, 1, 1, None)

    # 1. Color Bitmap
    old_bmp = gdi32.SelectObject(memdc, hbm_color)
    bg_brush = gdi32.CreateSolidBrush(0x000000)
    user32.FillRect(memdc, ctypes.byref(wintypes.RECT(0, 0, width, height)), bg_brush)
    gdi32.DeleteObject(bg_brush)

    # Purple circle (#8c7ae6 -> BGR: 0xe67a8c)
    purple_brush = gdi32.CreateSolidBrush(0x00e67a8c)
    old_brush = gdi32.SelectObject(memdc, purple_brush)
    null_pen = gdi32.GetStockObject(8)  # NULL_PEN
    old_pen = gdi32.SelectObject(memdc, null_pen)
    gdi32.Ellipse(memdc, 1, 1, width - 1, height - 1)
    gdi32.SelectObject(memdc, old_pen)
    gdi32.SelectObject(memdc, old_brush)
    gdi32.DeleteObject(purple_brush)
    gdi32.SelectObject(memdc, old_bmp)

    # 2. Mask Bitmap (0 = opaque circle, 1 = transparent background)
    maskdc = gdi32.CreateCompatibleDC(hdc)
    old_mask_bmp = gdi32.SelectObject(maskdc, hbm_mask)
    white_brush = gdi32.GetStockObject(0)  # WHITE_BRUSH (transparent)
    user32.FillRect(maskdc, ctypes.byref(wintypes.RECT(0, 0, width, height)), white_brush)
    black_brush = gdi32.GetStockObject(4)  # BLACK_BRUSH (opaque)
    gdi32.SelectObject(maskdc, black_brush)
    gdi32.SelectObject(maskdc, null_pen)
    gdi32.Ellipse(maskdc, 1, 1, width - 1, height - 1)
    gdi32.SelectObject(maskdc, old_mask_bmp)

    user32.ReleaseDC(0, hdc)
    gdi32.DeleteDC(memdc)
    gdi32.DeleteDC(maskdc)

    icon_info = ICONINFO()
    icon_info.fIcon = True
    icon_info.xHotspot = 0
    icon_info.yHotspot = 0
    icon_info.hbmMask = hbm_mask
    icon_info.hbmColor = hbm_color

    hicon = user32.CreateIconIndirect(ctypes.byref(icon_info))
    gdi32.DeleteObject(hbm_color)
    gdi32.DeleteObject(hbm_mask)
    return hicon


class Win32Tray:
    """Pure Win32 ctypes system tray manager replacing pystray."""

    def __init__(self, tooltip="WE Quota Tracker", on_left_click=None, on_right_click=None):
        self.tooltip = tooltip
        self.on_left_click = on_left_click
        self.on_right_click = on_right_click
        self.hwnd = None
        self.hicon = None
        self._thread = None
        self._wndproc = None
        self._ready_event = threading.Event()
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready_event.wait(timeout=3)

    def _run(self):
        hinstance = kernel32.GetModuleHandleW(None)
        class_name = f"WE_Tray_WndClass_{id(self)}"

        self._wndproc = WNDPROC(self._wnd_proc)

        wcex = WNDCLASSEXW()
        wcex.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wcex.style = 0
        wcex.lpfnWndProc = self._wndproc
        wcex.cbClsExtra = 0
        wcex.cbWndExtra = 0
        wcex.hInstance = hinstance
        wcex.hIcon = None
        wcex.hCursor = None
        wcex.hbrBackground = None
        wcex.lpszMenuName = None
        wcex.lpszClassName = class_name
        wcex.hIconSm = None

        user32.RegisterClassExW(ctypes.byref(wcex))

        self.hwnd = user32.CreateWindowExW(
            0, class_name, "WE_Tray_Hidden",
            0, 0, 0, 0, 0, None, None, hinstance, None
        )

        self.hicon = create_native_tray_icon()
        if not self.hicon:
            self.hicon = user32.LoadIconW(0, 32512)  # IDI_APPLICATION fallback

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY_MSG
        nid.hIcon = self.hicon
        nid.szTip = self.tooltip

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        self._nid = nid
        self._ready_event.set()

        msg = wintypes.MSG()
        while self._running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Cleanup on exit
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        if self.hicon:
            user32.DestroyIcon(self.hicon)
            self.hicon = None

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY_MSG:
            if lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                if self.on_left_click:
                    self.on_left_click()
            elif lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
                if self.on_right_click:
                    pt = wintypes.POINT()
                    user32.GetCursorPos(ctypes.byref(pt))
                    self.on_right_click(pt.x, pt.y)
            return 0
        elif msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        elif msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def stop(self):
        self._running = False
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)


# ---------------------------------------------------------------------------
# Vector Gear Button (Zero-Dependency Canvas replacement for PIL/ImageTk)
# ---------------------------------------------------------------------------

class VectorGearButton(tk.Canvas):
    """Zero-dependency vector-drawn settings gear button using native Tkinter canvas."""

    def __init__(self, parent, size=22, icon_size=16, normal_color="#a4b0be", hover_color="#ffffff", bg="#151821", command=None, **kwargs):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0, cursor="hand2", **kwargs)
        self.size = size
        self.icon_size = icon_size
        self.normal_color = normal_color
        self.hover_color = hover_color
        self.bg_color = bg
        self.command = command
        self.current_color = normal_color

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

        self._draw_gear()

    def _draw_gear(self):
        self.delete("all")
        cx = self.size / 2
        cy = self.size / 2
        r_outer = self.icon_size * 0.46
        r_inner = self.icon_size * 0.32
        r_hole  = self.icon_size * 0.15
        num_teeth = 6

        # Draw 6 gear teeth
        for i in range(num_teeth):
            angle = i * (2 * math.pi / num_teeth)
            w = math.pi / (num_teeth * 2.4)
            pts = [
                cx + r_inner * math.cos(angle - w * 1.5), cy + r_inner * math.sin(angle - w * 1.5),
                cx + r_outer * math.cos(angle - w),       cy + r_outer * math.sin(angle - w),
                cx + r_outer * math.cos(angle + w),       cy + r_outer * math.sin(angle + w),
                cx + r_inner * math.cos(angle + w * 1.5), cy + r_inner * math.sin(angle + w * 1.5),
            ]
            self.create_polygon(pts, fill=self.current_color, outline="")

        # Draw central circle body
        self.create_oval(cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner, fill=self.current_color, outline="")
        # Center cutout matching background
        self.create_oval(cx - r_hole, cy - r_hole, cx + r_hole, cy + r_hole, fill=self.bg_color, outline="")

    def _on_enter(self, _event=None):
        self.current_color = self.hover_color
        self._draw_gear()

    def _on_leave(self, _event=None):
        self.current_color = self.normal_color
        self._draw_gear()

    def _on_click(self, _event=None):
        if self.command:
            self.command()


# ---------------------------------------------------------------------------
# Zero-Dependency Standard Session Manager (Replacing requests)
# ---------------------------------------------------------------------------

class StandardResponse:
    def __init__(self, raw_bytes: bytes, status_code: int, headers: dict):
        if headers.get("Content-Encoding") == "gzip" or raw_bytes.startswith(b"\x1f\x8b"):
            try:
                self.content = gzip.decompress(raw_bytes)
            except Exception:
                self.content = raw_bytes
        else:
            self.content = raw_bytes
        self.status_code = status_code
        self.headers = headers

    def json(self):
        return json.loads(self.content.decode("utf-8"))

    @property
    def text(self):
        return self.content.decode("utf-8")


class StandardSession:
    """Zero-dependency HTTP session manager using standard library urllib and http.cookiejar."""

    def __init__(self):
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.headers = {
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
        }

    def post(self, url: str, json_data: dict = None, headers: dict = None, timeout: int = 30) -> StandardResponse:
        data = None
        req_headers = dict(self.headers)
        if headers:
            req_headers.update(headers)

        if json_data is not None:
            data = json.dumps(json_data).encode("utf-8")
            req_headers["Content-Type"] = "application/json; charset=UTF-8"

        req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                resp_headers = dict(resp.info())
                raw_bytes = resp.read()
                return StandardResponse(raw_bytes, resp.status, resp_headers)
        except urllib.error.HTTPError as e:
            resp_headers = dict(e.headers) if hasattr(e, "headers") else {}
            raw_bytes = e.read() if hasattr(e, "read") else b""
            return StandardResponse(raw_bytes, e.code, resp_headers)

    def get_cookies_dict(self) -> dict:
        return {cookie.name: cookie.value for cookie in self.cookie_jar}

    def set_cookies_from_dict(self, cookies: dict, domain: str = ".te.eg"):
        for name, value in cookies.items():
            ck = http.cookiejar.Cookie(
                version=0,
                name=name,
                value=value,
                port=None,
                port_specified=False,
                domain=domain,
                domain_specified=True,
                domain_initial_dot=domain.startswith("."),
                path="/",
                path_specified=True,
                secure=False,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False
            )
            self.cookie_jar.set_cookie(ck)


# ---------------------------------------------------------------------------
# Config helpers (config.json lives next to exe / script, never bundled)
# ---------------------------------------------------------------------------

def get_config_path():
    """Return absolute path to config.json next to exe/script."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        # Check parent folder if running from src/
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.basename(curr_dir).lower() == "src":
            base = os.path.dirname(curr_dir)
        else:
            base = curr_dir
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
# Runtime globals (reloaded after settings save)
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
# Utilities & Backend API Flows
# ---------------------------------------------------------------------------

def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except Exception:
        pass


def get_base_session() -> StandardSession:
    return StandardSession()


def perform_login():
    session = get_base_session()
    captchaPayload = {"merchantName": "E-Care", "serviceName": "Login", "identifier": landline}
    response = session.post("https://captcha.te.eg/api/Captcha/GenerateCaptcha", json_data=captchaPayload)
    captcha = response.json()

    if captcha.get("status") != "Success":
        raise Exception("Captcha request failed")

    captchaToken = captcha["token"]
    answer = "" if captcha.get("requireInteraction") is False else solveCaptcha(captcha["captcha"], google_api_key)["letters"]

    loginPayload = {
        "acctId": acctId,
        "password": password,
        "imgCacheKey": captchaToken,
        "appLocale": "en-US",
        "isSelfcare": "Y",
        "isMobile": "N",
        "imgCode": answer,
        "isConvergent": "0"
    }

    session.headers.update({
        "channelid": "702",
        "csrftoken": "",
        "languagecode": "en-US",
        "isselfcare": "true",
        "delegatorsubsid": "",
        "iscoporate": "false",
        "ismobile": "false",
        "systemtype": "",
    })

    response = session.post(
        "https://my.te.eg/echannel/service/besapp/base/rest/busiservice/v1/auth/userAuthenticate",
        json_data=loginPayload
    )
    login = response.json()

    try:
        csrf = login["body"]["token"]
    except (KeyError, TypeError):
        raise Exception("Login failed: invalid credentials or blocked")

    session.headers.update({"csrftoken": csrf})
    subscriberId = login["body"]["subscriber"]["subscriberId"]

    offersPayload = {"msisdn": acctId, "numberServiceType": "FBB", "groupId": ""}
    response = session.post(
        "https://my.te.eg/echannel/service/besapp/base/rest/busiservice/cz/v1/auth/getSubscribedOfferings",
        json_data=offersPayload
    )
    mainOfferId = response.json()["body"]["offeringList"][0]["mainOfferingId"]

    session_data = {
        "cookies": session.get_cookies_dict(),
        "headers": dict(session.headers),
        "subscriberId": subscriberId,
        "mainOfferId": mainOfferId
    }

    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(session_data, f)

    return session_data


def fetch_quota(session_data):
    session = StandardSession()
    session.set_cookies_from_dict(session_data.get("cookies", {}))
    session.headers.update(session_data.get("headers", {}))

    quotaPayload = {
        "subscriberId": session_data["subscriberId"],
        "needQueryPoint": "true",
        "mainOfferId": session_data["mainOfferId"],
    }

    try:
        response = session.post(
            "https://my.te.eg/echannel/service/besapp/base/rest/busiservice/cz/cbs/bb/queryFreeUnit",
            json_data=quotaPayload
        )
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
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        else:
            logs = []
    except Exception:
        logs = []

    logs.append({"timestamp": now, "used": used, "remain": remain, "total": total})
    logs = [log for log in logs if log["timestamp"] >= now - 86400]

    with open(LOG_FILE, "w", encoding="utf-8") as f:
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
# Smooth & Native Entry Helpers (No typing glitch / cursor jumping)
# ---------------------------------------------------------------------------

def paste_clipboard_into_entry(entry: tk.Entry):
    """Pastes clipboard text directly into the Entry widget cleanly."""
    try:
        clip_text = entry.clipboard_get()
        if clip_text:
            clean = clip_text.replace("\r\n", "").replace("\n", "").replace("\r", "")
            try:
                first = entry.index(tk.SEL_FIRST)
                last = entry.index(tk.SEL_LAST)
                entry.delete(first, last)
            except tk.TclError:
                pass
            entry.insert(tk.INSERT, clean)
    except Exception:
        pass


def setup_entry_context_menu(entry: tk.Entry):
    """Provides a sleek right-click context menu and standard Ctrl+A/Copy/Paste support."""
    entry.config(
        selectbackground="#8c7ae6",
        selectforeground="#ffffff",
        exportselection=False
    )

    # Ctrl+A binding (Select All)
    def select_all(event=None):
        entry.select_range(0, tk.END)
        entry.icursor(tk.END)
        return "break"

    entry.bind("<Control-a>", select_all)
    entry.bind("<Control-A>", select_all)

    # Dark-themed context menu
    menu = tk.Menu(entry, tearoff=0, bg="#1c1f2e", fg="#f5f6fa",
                   activebackground="#8c7ae6", activeforeground="#ffffff",
                   relief=tk.FLAT, bd=1, font=("Segoe UI", 9))

    def cut_text():
        try:
            entry.event_generate("<<Cut>>")
        except Exception:
            pass

    def copy_text():
        try:
            entry.event_generate("<<Copy>>")
        except Exception:
            pass

    def paste_text():
        paste_clipboard_into_entry(entry)

    def clear_text():
        entry.delete(0, tk.END)

    menu.add_command(label="Cut", command=cut_text, accelerator="Ctrl+X")
    menu.add_command(label="Copy", command=copy_text, accelerator="Ctrl+C")
    menu.add_command(label="Paste", command=paste_text, accelerator="Ctrl+V")
    menu.add_separator()
    menu.add_command(label="Select All", command=select_all, accelerator="Ctrl+A")
    menu.add_command(label="Clear", command=clear_text)

    def show_context_menu(event):
        entry.focus_set()
        try:
            has_sel = entry.selection_present()
        except Exception:
            has_sel = False

        state_sel = "normal" if has_sel else "disabled"
        menu.entryconfig("Cut", state=state_sel)
        menu.entryconfig("Copy", state=state_sel)

        try:
            has_clip = bool(entry.clipboard_get().strip())
        except Exception:
            has_clip = False

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
        self.transient(parent)
        self.attributes("-topmost", True)
        self.grab_set()
        self.lift()
        self.focus_force()

        self._build_ui()
        self._position_dialog(parent)

        self._drag_x = self._drag_y = 0
        self._title_bar.bind("<ButtonPress-1>", self._drag_start)
        self._title_bar.bind("<B1-Motion>",     self._drag_motion)
        self._title_lbl.bind("<ButtonPress-1>", self._drag_start)
        self._title_lbl.bind("<B1-Motion>",     self._drag_motion)
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

    def _build_ui(self):
        W = 350

        # Title bar
        self._title_bar = tk.Frame(self, bg=self.SURFACE, height=36, width=W)
        self._title_bar.pack(fill=tk.X)
        self._title_bar.pack_propagate(False)

        gear_icon = VectorGearButton(self._title_bar, size=20, icon_size=14, normal_color=self.FG, hover_color=self.FG, bg=self.SURFACE)
        gear_icon.place(x=10, y=8)

        self._title_lbl = tk.Label(
            self._title_bar, text="Settings",
            fg=self.FG, bg=self.SURFACE,
            font=("Segoe UI", 10, "bold"), anchor="w"
        )
        self._title_lbl.place(x=34, y=7)

        btn_close = tk.Label(
            self._title_bar, text="✕", fg=self.SUB, bg=self.SURFACE,
            font=("Segoe UI", 10), cursor="hand2"
        )
        btn_close.place(x=W - 28, y=8)
        btn_close.bind("<Button-1>", lambda _: self.destroy())
        btn_close.bind("<Enter>",    lambda _: btn_close.config(fg=self.DANGER))
        btn_close.bind("<Leave>",    lambda _: btn_close.config(fg=self.SUB))

        # Separator
        tk.Frame(self, bg=self.BORDER, height=1).pack(fill=tk.X)

        # Body
        body = tk.Frame(self, bg=self.BG, padx=20, pady=16)
        body.pack(fill=tk.BOTH, expand=True)

        cfg = load_config()

        fields = [
            ("Landline Number",   "LANDLINE",       False),
            ("WE Password",       "MY_WE_PASSWORD",  True),
            ("Google API Key",    "GOOGLE_API_KEY",  True),
        ]

        self._vars = {}

        for label_text, key, secret in fields:
            tk.Label(body, text=label_text, fg=self.SUB, bg=self.BG,
                     font=("Segoe UI", 8), anchor="w").pack(fill=tk.X, pady=(8, 2))

            row = tk.Frame(body, bg=self.BG)
            row.pack(fill=tk.X)

            var = tk.StringVar(value=cfg.get(key, ""))
            self._vars[key] = var

            show_char = "*" if secret else ""
            entry = tk.Entry(
                row, textvariable=var, show=show_char,
                bg=self.SURFACE, fg=self.FG, insertbackground=self.FG,
                relief=tk.FLAT, font=("Segoe UI", 10),
                highlightthickness=1, highlightbackground=self.BORDER,
                highlightcolor=self.ACCENT
            )
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 4))
            setup_entry_context_menu(entry)

            if secret:
                sv = tk.BooleanVar(value=False)

                def _toggle(e=entry, sv=sv):
                    is_visible = not sv.get()
                    sv.set(is_visible)
                    e.config(show="" if is_visible else "*")

                eye = tk.Label(row, text="👁", fg=self.SUB, bg=self.BG,
                               cursor="hand2", font=("Segoe UI", 10), padx=3)
                eye.pack(side=tk.LEFT)
                eye.bind("<Button-1>", lambda _, t=_toggle: t())
                eye.bind("<Enter>",    lambda _, b=eye: b.config(fg=self.FG))
                eye.bind("<Leave>",    lambda _, b=eye: b.config(fg=self.SUB))

            paste_btn = tk.Label(row, text="📋", fg=self.SUB, bg=self.BG,
                                 cursor="hand2", font=("Segoe UI", 10), padx=3)
            paste_btn.pack(side=tk.LEFT)
            paste_btn.bind("<Button-1>", lambda _, e=entry: paste_clipboard_into_entry(e))
            paste_btn.bind("<Enter>",    lambda _, b=paste_btn: b.config(fg=self.FG))
            paste_btn.bind("<Leave>",    lambda _, b=paste_btn: b.config(fg=self.SUB))

        tk.Label(
            body,
            text="Changes take effect on next login / refresh.",
            fg=self.SUB, bg=self.BG, font=("Segoe UI", 7, "italic")
        ).pack(pady=(14, 0))

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
        self.root.overrideredirect(True)
        self.root.geometry("260x340")

        self.is_dragging      = False
        self.is_refreshing    = False
        self.is_settings_open = False
        self.after_id         = None

        # Position at top right corner
        screen_width = self.root.winfo_screenwidth()
        self.start_x = screen_width - 280
        self.start_y = 20
        self.reset_position()

        # Dark theme colors
        self.bg_color     = "#151821"
        self.fg_color     = "#f5f6fa"
        self.accent_color = "#8c7ae6"
        self.arc_bg       = "#2f3640"
        self.sub_text     = "#a4b0be"

        self.root.configure(bg=self.bg_color)

        # Settings gear icon button (top right)
        self.btn_settings = VectorGearButton(
            root, size=22, icon_size=16,
            normal_color=self.sub_text, hover_color="#ffffff",
            bg=self.bg_color, command=self.open_settings
        )
        self.btn_settings.place(x=205, y=6, width=22, height=22)

        # Close button (hides to tray)
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

        self.canvas.create_oval(self.cx - self.r, self.cy - self.r, self.cx + self.r, self.cy + self.r, outline=self.arc_bg, width=12)
        self.arc = self.canvas.create_arc(self.cx - self.r, self.cy - self.r, self.cx + self.r, self.cy + self.r, start=90, extent=0, outline=self.accent_color, width=12, style=tk.ARC)

        self.lbl_gb        = self.canvas.create_text(self.cx, self.cy - 10, text="-- GB",       fill=self.fg_color, font=("Segoe UI", 20, "bold"))
        self.lbl_remain_of = self.canvas.create_text(self.cx, self.cy + 15, text="Remaining of", fill=self.sub_text, font=("Segoe UI", 9))
        self.lbl_total     = self.canvas.create_text(self.cx, self.cy + 30, text="-- GB",       fill=self.fg_color, font=("Segoe UI", 9, "bold"))

        self.lbl_recent = tk.Label(self.root, text="", fg="#e1b12c", bg=self.bg_color, font=("Segoe UI", 9))
        self.lbl_recent.pack(pady=(2, 0))

        self.lbl_timestamp = tk.Label(self.root, text="Not updated yet", fg=self.sub_text, bg=self.bg_color, font=("Segoe UI", 8))
        self.lbl_timestamp.pack(pady=(2, 0))

        # Action button centered: "Refresh" when active, "Relogin" when expired
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

        cfg = load_config()
        if not cfg.get("LANDLINE") or not cfg.get("MY_WE_PASSWORD"):
            self.root.after(300, self.open_settings)
        else:
            self.schedule_refresh(0)

        self.setup_tray_icon()

    def reset_position(self):
        self.root.geometry(f"+{self.start_x}+{self.start_y}")

    def open_settings(self):
        self.is_settings_open = True
        SettingsDialog(self.root, on_save_callback=self._on_settings_saved, on_close_callback=self._on_settings_closed)

    def _on_settings_closed(self):
        self.is_settings_open = False

    def _on_settings_saved(self):
        if os.path.exists(SESSION_FILE):
            try:
                os.remove(SESSION_FILE)
            except Exception:
                pass
        self.schedule_refresh(0)

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
        if hasattr(self, "tray") and self.tray:
            self.tray.stop()
        self.root.after(0, self.root.destroy)

    def setup_tray_icon(self):
        self.tray_menu = tk.Menu(
            self.root, tearoff=0, bg="#1c1f2e", fg="#f5f6fa",
            activebackground="#8c7ae6", activeforeground="#ffffff",
            relief=tk.FLAT, bd=1, font=("Segoe UI", 9)
        )
        self.tray_menu.add_command(label="Show / Hide",    command=self.toggle_window)
        self.tray_menu.add_command(label="Settings",       command=lambda: self.root.after(0, self.open_settings))
        self.tray_menu.add_command(label="Reset Position", command=lambda: self.root.after(0, self.reset_position))
        self.tray_menu.add_separator()
        self.tray_menu.add_command(label="Exit",           command=self.exit_app)

        self.tray = Win32Tray(
            tooltip="WE Quota Tracker",
            on_left_click=lambda: self.root.after(0, self.toggle_window),
            on_right_click=lambda x, y: self.root.after(0, lambda: self._show_tray_menu(x, y))
        )
        self.tray.start()

    def _show_tray_menu(self, x, y):
        user32.SetForegroundWindow(self.root.winfo_id())
        self.tray_menu.tk_popup(x, y)
        user32.PostMessageW(self.root.winfo_id(), WM_NULL, 0, 0)

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
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
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
        out = subprocess.check_output('tasklist /FI "IMAGENAME eq MyWE.exe" /FO CSV /NH', shell=True, text=True)
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
            with open(LOCK_FILE, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if pid != current_pid and is_pid_running(pid):
                return pid
        except Exception:
            pass

    global _MUTEX_HANDLE
    try:
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
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
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
            root.after(150, lambda: keep_desktop_behavior(root, app))
            return

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


def main():
    root = tk.Tk()
    root.withdraw()

    if not check_single_instance(root):
        root.destroy()
        sys.exit(0)

    app = QuotaWidget(root)
    root.deiconify()
    keep_desktop_behavior(root, app)
    root.mainloop()


if __name__ == "__main__":
    main()