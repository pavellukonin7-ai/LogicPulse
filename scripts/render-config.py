#!/usr/bin/env python3
import json, os, re, sys
from pathlib import Path
p=Path(__file__).resolve().parent.parent
values={}
for line in (p/'.env').read_text().splitlines():
    if line and not line.startswith('#'):
        k,v=line.split('=',1); values[k]=v
mode=sys.argv[1] if len(sys.argv)>1 else 'production'
if mode not in ('bootstrap','production'): raise SystemExit('Invalid mode')
domain=values['DOMAIN']
if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',domain): raise SystemExit('Invalid domain')
config=(p/f'nginx/templates/{mode}.conf').read_text().replace('__DOMAIN__',domain)
out=p/'nginx/conf.d'; out.mkdir(parents=True,exist_ok=True)
tmp=out/'logicpulse.conf.tmp'; tmp.write_text(config); tmp.chmod(0o644); tmp.replace(out/'logicpulse.conf')
servers={'Servers':{'1':{'Name':'LogicPulse PostgreSQL','Group':'LogicPulse','Host':'postgres','Port':5432,
    'MaintenanceDB':values['POSTGRES_DB'],'Username':values['POSTGRES_USER'],'SSLMode':'prefer'}}}
(p/'pgadmin').mkdir(exist_ok=True)
server_file=p/'pgadmin/servers.json'
server_file.write_text(json.dumps(servers,ensure_ascii=False,indent=2)+'\n'); server_file.chmod(0o644)
print(f'Nginx: {mode}; pgAdmin: server configured without stored database password')
