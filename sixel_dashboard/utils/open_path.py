import os
import platform
import subprocess
from pathlib import Path

def open_path(path: str | Path):
    path = Path(path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"No existe: {path}")

    system = platform.system()

    if system == "Windows":
        os.startfile(path)  # ✅ Windows nativo
    elif system == "Darwin":  # macOS
        subprocess.run(["open", path])
    else:  # Linux
        subprocess.run(["xdg-open", path])
