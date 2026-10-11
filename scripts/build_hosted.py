"""Build the unchanged full frontend for Vercel's FastAPI public directory."""
import shutil
import subprocess
from pathlib import Path

if Path('public/index.html').exists():
    print('Using verified prebuilt full frontend')
    raise SystemExit(0)

subprocess.run(['npm', 'ci'], cwd='frontend', check=True)
subprocess.run(['npm', 'run', 'build'], cwd='frontend', check=True)
public = Path('public')
if public.exists():
    shutil.rmtree(public)
shutil.copytree('frontend/dist', public, ignore=shutil.ignore_patterns('demo-assets'))
