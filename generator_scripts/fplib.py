import os, math
from kiutils.footprint import Footprint
V='/home/claude/vendor'
def fp_path(lib):
    l,n=lib.split(':')
    if l=='Espressif': return f'{V}/esp/footprints/Espressif.pretty/{n}.kicad_mod'
    return f'{V}/fp/{l}.pretty/{n}.kicad_mod'
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
