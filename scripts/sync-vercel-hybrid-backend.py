"""Refresh apps/web/python_backend from apps/api for hybrid Vercel releases."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
src = root / "apps" / "api"
dst = root / "apps" / "web" / "python_backend"
if dst.exists():
    shutil.rmtree(dst)
dst.mkdir(parents=True)
shutil.copytree(src / "app", dst / "app")
shutil.copytree(src / "alembic", dst / "alembic")
shutil.copy2(src / "alembic.ini", dst / "alembic.ini")
print(f"Synced canonical API runtime into {dst}")
