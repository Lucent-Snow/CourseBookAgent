"""Deploy the built public demonstration without uploading workspace secrets."""
from pathlib import Path
import json,base64,urllib.request,urllib.error,os,argparse
credential=Path.home()/'Library/Application Support/com.vercel.cli/auth.json'
token=os.environ.get('VERCEL_TOKEN') or json.loads(credential.read_text())['token']
parser=argparse.ArgumentParser()
parser.add_argument('--project', required=True)
args=parser.parse_args()
name=args.project
root=Path('frontend/dist')
if not (root/'demo-assets/demo.json').exists():
 raise SystemExit('Build the demonstration bundle before deploying')
files=[{'file':str(p.relative_to(root)), 'data':base64.b64encode(p.read_bytes()).decode(), 'encoding':'base64'} for p in root.rglob('*') if p.is_file()]
config={'version':2,'rewrites':[{'source':'/demo/:path*','destination':'/index.html'}]}
files.append({'file':'vercel.json','data':json.dumps(config),'encoding':'utf-8'})
payload={'name':name,'target':'production','files':files,'projectSettings':{'framework':None,'buildCommand':'','installCommand':'','outputDirectory':None}}
req=urllib.request.Request('https://api.vercel.com/v13/deployments?skipAutoDetectionConfirmation=1',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
try:
 with urllib.request.urlopen(req,timeout=50) as r: response=json.load(r)
 Path('frontend/.vercel').mkdir(parents=True, exist_ok=True)
 Path('frontend/.vercel/demo-deployment.json').write_text(json.dumps({k:response.get(k) for k in ['id','url','readyState','alias','projectId']}))
 print(json.dumps({k:response.get(k) for k in ['id','url','readyState','alias','projectId']}))
except urllib.error.HTTPError as e:
 print('deployment_error',e.code,e.read().decode()[:1500]); raise SystemExit(1)
