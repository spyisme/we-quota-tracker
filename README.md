# MyWE - My We Egypt Quota Monitor
![image](http://spysnet.com/mywe) <br>
A lightweight desktop application and system tray utility to monitor Telecom Egypt (WE) internet quota in real time, featuring automated AI-powered captcha solving.

Built with **zero external runtime dependencies** (standard Python library + native Win32 `ctypes` bindings) for an ultra-lightweight footprint and minimal executable size.

---

## Features

- **Live Quota Tracking**: Real-time circular progress gauge showing remaining, used, and total gigabytes.
- **AI Captcha Solving**: Automatically resolves login captchas via Google Gemini (`gemini-3.1-flash`) using standard `urllib.request`.
- **System Tray Integration**: Native Windows system tray integration via `ctypes` (`Shell_NotifyIconW`) with customizable popup menu (Show/Hide, Settings, Reset Position, Exit).
- **Vector UI**: Crisp vector-rendered settings gear button via native Tkinter canvas (no Pillow dependency).
- **Usage History & Deltas**: Rolling 24-hour log persistence (`quota_log.json`) tracking 30-minute consumption deltas.
- **Built-in Configuration UI**: Modal settings dialog to enter your credentials and API key directly in the app.
- **Single Instance & Desktop Pinning**: Native mutex-based single instance handling and desktop-pinning behavior.
- **Lightweight Executable**: Compiles into a compact standalone `.exe` (~11MB) using PyInstaller.

---

## Prerequisites

- **Python**: Python 3.10 or newer (Standard Library only)
- **WE Account**: Your landline number (with governorate code, e.g., `02xxxxxxx`) and My WE password
- **Google AI Studio API Key**: A free API key from [Google AI Studio](https://aistudio.google.com/) for Gemini captcha solving

---

## Installation

1. **Clone this repository**:
   ```bash
   git clone https://github.com/spyisme/we-quota-tracker.git
   ```

2. **(Optional) Install packaging dependencies**:
   No external packages are required to run the application from source. If you plan to build the standalone `.exe`, install `pyinstaller`:
   ```bash
   pip install -r requirements.txt
   ```

---

## Configuration

You can enter your credentials directly in the GUI settings dialog upon launch, or create/edit `config.json` in the project root:

```json
{
  "LANDLINE": "02xxxxxxx",
  "MY_WE_PASSWORD": "your_password_here",
  "GOOGLE_API_KEY": "AIzaSy..."
}
```

---

## Usage

### Run the GUI Application
```bash
python -m src.gui
```

### Run the CLI Quick Check
For a quick terminal check without launching the GUI:
```bash
python main.py
```

### Build Standalone Executable (.exe)
To package the app into a standalone Windows executable (`dist/MyWE.exe`):
```bash
python scripts/build.py
```

---

## Project Structure

```
├── src/
│   ├── __init__.py
│   ├── gui.py          # Main Tkinter desktop application & Win32 system tray
│   └── capsolver.py    # Gemini AI OCR captcha solver module (urllib)
├── scripts/
│   └── build.py        # PyInstaller build automation script
├── main.py             # Terminal quick-check CLI script
├── requirements.txt    # Build-only dependencies (PyInstaller)
├── README.md           # Project documentation
└── .gitignore          # Git ignore rules for session data and credentials
```

---

## License

This project is for personal educational use. Not affiliated with or endorsed by Telecom Egypt (WE).
Inspired by karimawi.
