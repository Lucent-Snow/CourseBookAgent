"""Upload source and an explicitly exported preset; exclude local data/secrets."""
import argparse
import base64
import json
import os
import subprocess
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--project', default='coursebook-demo')
parser.add_argument('--production', action='store_true')
parser.add_argument('--preset', type=Path, default=Path('data/deployment-preset'))
args = parser.parse_args()
credential = Path.home() / 'Library/Application Support/com.vercel.cli/auth.json'
token = os.getenv('VERCEL_TOKEN') or json.loads(credential.read_text())['token']
# Only deploy application source, dependencies and frontend source.
roots = ['coursebook_agent','frontend/src','frontend/tests']
paths = [path for root in roots for path in Path(root).rglob('*') if path.is_file() and '__pycache__' not in path.parts]
paths += [Path(name) for name in ('app.py','pyproject.toml','uv.lock','vercel.json','scripts/build_hosted.py')]
paths += [p for p in Path('frontend').glob('*') if p.is_file() and p.suffix in ('.json','.ts','.html')]
subprocess.run(['npm','run','build'], cwd='frontend', check=True, stdout=subprocess.DEVNULL)
files = [{'file':str(path),'data':base64.b64encode(path.read_bytes()).decode(),'encoding':'base64'} for path in paths]
files += [{'file':str(Path('public')/path.relative_to('frontend/dist')), 'data':base64.b64encode(path.read_bytes()).decode(),'encoding':'base64'} for path in Path('frontend/dist').rglob('*') if path.is_file() and 'demo-assets' not in path.parts]
if not (args.preset/'preset-imported.json').exists():
    raise SystemExit('Export a selected completed Job first')
files += [{'file':str(Path('bundled-preset')/path.relative_to(args.preset)), 'data':base64.b64encode(path.read_bytes()).decode(),'encoding':'base64'} for path in args.preset.rglob('*') if path.is_file()]
payload = {'name':args.project,'files':files,'projectSettings':{'framework':'fastapi','buildCommand':'python scripts/build_hosted.py','installCommand':None,'outputDirectory':None}}
if args.production: payload['target']='production'
request = urllib.request.Request('https://api.vercel.com/v13/deployments?skipAutoDetectionConfirmation=1', data=json.dumps(payload).encode(), method='POST', headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
with urllib.request.urlopen(request, timeout=50) as response:
    result = json.load(response)
metadata = {k:result.get(k) for k in ('id','url','readyState','projectId')}
Path('frontend/.vercel/workbench-deployment.json').write_text(json.dumps(metadata))
print(json.dumps(metadata))
