"""Copy the shared Python detector and KJV database into web/ before deploying.

    python3 build_web.py

The browser preview runs the same scripture_refs.py as the desktop app, so
always run this after changing scripture_refs.py or kjv.sqlite.

Local preview (VS Code's built-in preview server refuses .py/.sqlite files):
    python3 -m http.server 8000 -d web      then open http://localhost:8000
"""
import shutil
from pathlib import Path

HERE = Path(__file__).parent
WEB = HERE / "web"

for name in ("scripture_refs.py", "kjv.sqlite"):
    shutil.copy2(HERE / name, WEB / name)
    (WEB / name).chmod(0o644)  # readable by web servers / deploy tools
    print(f"copied {name} -> web/{name}")
