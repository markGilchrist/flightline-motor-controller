import os, math
from kiutils.footprint import Footprint
# Footprint library locations. Override with KICAD_FP_DIR (folder of *.pretty) and ESP_FP_DIR
# (folder holding the Espressif .kicad_mod files) on a new machine.
FP_DIR = os.environ.get('KICAD_FP_DIR', '/usr/share/kicad/footprints')
ESP_DIR = os.environ.get('ESP_FP_DIR', '/home/user/vendor/esp')
def fp_path(lib):
    l,n=lib.split(':')
    if l=='Espressif': return f'{ESP_DIR}/{n}.kicad_mod'
    return f'{FP_DIR}/{l}.pretty/{n}.kicad_mod'
def load(lib):
    return Footprint.from_file(fp_path(lib))
def bbox(fp, layers=('F.CrtYd','B.CrtYd')):
    xs=[];ys=[]
    for g in fp.graphicItems:
        if getattr(g,'layer',None) in layers:
            for a in ('start','end','center','mid'):
                p=getattr(g,a,None)
                if p is not None: xs.append(p.X); ys.append(p.Y)
            for p in (getattr(g,'coordinates',None) or []):
                xs.append(p.X); ys.append(p.Y)
    if not xs:
        for p in fp.pads: xs+= [p.position.X-p.size.X/2,p.position.X+p.size.X/2]; ys+=[p.position.Y-p.size.Y/2,p.position.Y+p.size.Y/2]
    return min(xs),min(ys),max(xs),max(ys)
