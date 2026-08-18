import os
import subprocess
import sys
from pathlib import Path


def build():
    print("========================================================")
    print("  Building MyWE Executable")
    print("========================================================")

    # Resolve paths relative to the project root (one level above scripts/)
    root_dir = Path(__file__).resolve().parent.parent
    main_file = root_dir / "src" / "gui.py"
    dist_dir = root_dir / "dist"
    work_dir = root_dir / "build"
    spec_dir = root_dir / "build"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name",
        "MyWE",
        "--clean",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        "--exclude-module", "sqlite3",
        "--exclude-module", "unittest",
        "--exclude-module", "pydoc",
        "--exclude-module", "pdb",
        "--exclude-module", "xmlrpc",
        "--exclude-module", "multiprocessing",
        "--exclude-module", "asyncio",
        "--exclude-module", "test",
        str(main_file),
    ]

    # Run PyInstaller from the project root directory
    result = subprocess.run(cmd, cwd=root_dir)

    if result.returncode == 0:
        exe_path = dist_dir / "MyWE.exe"
        print("\n========================================================")
        print("  Build completed successfully!")
        print(f"  Executable: {exe_path}")
        print("========================================================")
    else:
        print(
            "\n[ERROR] Build failed. Please inspect the PyInstaller errors above."
        )
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()