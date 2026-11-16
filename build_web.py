"""Copy the shared Python detector and KJV database into the web app.

    python3 build_web.py

The web app (web/, Next.js) runs the same scripture_refs.py in the browser
through Pyodide, so run this after changing scripture_refs.py or kjv.sqlite.
Then:
    cd web && npm run dev        # local development, http://localhost:3000
    cd web && npm run build      # static site in web/out/
"""
import shutil
from pathlib import Path

HERE = Path(__file__).parent
PUBLIC = HERE / "web" / "public"

for name in ("scripture_refs.py", "kjv.sqlite"):
    shutil.copy2(HERE / name, PUBLIC / name)
    (PUBLIC / name).chmod(0o644)  # readable by web servers / deploy tools
    print(f"copied {name} -> web/public/{name}")
