import json, subprocess, sys, os
from dsn import write_dsn, read_ses
os.makedirs('out', exist_ok=True)
write_dsn('out/motor_ctrl.dsn', route_classes={'Power': (0.8, 0.5)})
passes = sys.argv[1] if len(sys.argv) > 1 else '40'
cmd = ['java', '-Djava.awt.headless=true', '-jar', '/home/claude/vendor/fr/freerouting-2.1.0.jar',
       '-de', 'out/motor_ctrl.dsn', '-do', 'out/motor_ctrl.ses', '-mp', passes, '--gui.enabled=false']
r = subprocess.run(cmd, capture_output=True, text=True, timeout=1500)
log = r.stdout + r.stderr
open('out/freerouting.log', 'w').write(log)
print('\n'.join(l for l in log.splitlines() if 'JAVA_TOOL' not in l)[-3000:])
routes = read_ses('out/motor_ctrl.ses')
json.dump(routes, open('out/routes.json', 'w'))
print('tracks', len(routes['tracks']), 'vias', len(routes['vias']))
