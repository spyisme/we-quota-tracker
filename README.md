# MyWE - Telecom Egypt Quota Monitor

A lightweight desktop application and system tray utility to monitor Telecom Egypt (WE) internet quota in real time, featuring automated AI-powered captcha solving.

---

## Features

- **Live Quota Tracking**: Real-time display of used, remaining, and total gigabytes.
- **AI Captcha Solving**: Automatically resolves login captchas using Google Gemini (`gemini-3.1-flash-lite`).
- **System Tray Integration**: Runs unobtrusively in the Windows system tray with quick status tooltips and controls.
- **Usage Statistics & History**: Keeps track of quota consumption over a 24-hour window.
- **Built-in Configuration UI**: Configure your WE credentials and Google API Key directly inside the app.
- **Standalone Executable**: Easily build a single `.exe` file using the included PyInstaller script.

---

## Prerequisites

- **Python**: Python 3.10 or newer
- **WE Account**: Your landline number (with area code, e.g., `02xxxxxxx`) and My WE password
- **Google AI Studio API Key**: A free API key from [Google AI Studio](https://aistudio.google.com/) for Gemini captcha solving

---

## Installation

1. **Clone or download this repository**:
   ```bash
   git clone https://github.com/your-username/mywe.git
   cd mywe
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## Configuration

You can enter your credentials directly in the GUI settings dialog upon launch, or create/edit `config.json` in the root folder:

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
python gui.py
```

### Run the CLI Quick Check
For a simple one-off terminal check without the GUI:
```bash
python main.py
```

### Build Single Executable (.exe)
To package the app into a standalone Windows executable (`dist/MyWE.exe`):
```bash
python build.py
```

---

## Project Structure

```
├── gui.py              # Main Tkinter desktop application with tray support
├── capsolver.py        # Gemini AI captcha solver module
├── main.py             # CLI script for fetching quota in terminal
├── build.py            # PyInstaller build automation script
├── requirements.txt    # Python dependencies
├── README.md           # Project documentation
└── .gitignore          # Git ignore rules for sessions and secrets
```

---

## License

This project is for personal educational use. Not affiliated with or endorsed by Telecom Egypt (WE).
