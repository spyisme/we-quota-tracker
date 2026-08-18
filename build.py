import subprocess
import sys
import shutil
import os

def build():
    print("========================================================")
    print("  Building MyWE Executable")
    print("========================================================")
    
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name", "MyWE",
        "--clean",
        "gui.py",
    ]
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        exe_path = os.path.join(os.path.abspath("dist"), "MyWE.exe")
        print("\n========================================================")
        print("  Build completed successfully!")
        print(f"  Executable: {exe_path}")
        print("========================================================")
    else:
        print("\n[ERROR] Build failed. Please inspect the PyInstaller errors above.")
        sys.exit(result.returncode)

if __name__ == "__main__":
    build()
