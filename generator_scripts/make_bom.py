import csv, collections
from design import PARTS
rows = collections.OrderedDict()
for p in PARTS:
    if p['kind'] == 'hole': continue
    fp = p['fp'].split(':')[1]
    key = (p['value'], fp, p.get('mpn', ''))
    rows.setdefault(key, []).append(p['ref'])
def natkey(r):
    import re
    m = re.match(r'([A-Z]+)(\d+)', r); return (m.group(1), int(m.group(2)))
with open('out/motor_ctrl_BOM.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['Qty', 'References', 'Value', 'Footprint', 'Manufacturer part / notes'])
    for (val, fp, mpn), refs in sorted(rows.items(), key=lambda kv: natkey(sorted(kv[1], key=natkey)[0])):
        refs = sorted(refs, key=natkey)
        w.writerow([len(refs), ' '.join(refs), val, fp, mpn])
print(open('out/motor_ctrl_BOM.csv').read())
