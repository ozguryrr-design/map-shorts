"""Usage: debug_route.py route.py x0 y0 x1 y1 out.png  -> land mask + route image"""
import sys, os, importlib.util, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw
from mapengine.seapath import sea_route, land_mask
spec = importlib.util.spec_from_file_location("route", sys.argv[1]); R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
x0,y0,x1,y1 = map(float, sys.argv[2:6])
res = (x1-x0)/900
m,nx,ny = land_mask(x0,y0,x1,y1,res)
im = Image.fromarray(np.where(m, 120, 20).astype(np.uint8)).convert("RGB")
d = ImageDraw.Draw(im)
pts,lab = sea_route(R.ROUTE)
P = [((p[0]-x0)/res, (y1-p[1])/res) for p in pts]
d.line(P, fill=(255,200,0), width=2)
for w in R.ROUTE:
    x,y=(w[0]-x0)/res,(y1-w[1])/res; d.ellipse([x-4,y-4,x+4,y+4], outline=(255,60,60))
for gx in np.arange(np.ceil(x0), x1, 1.0):
    X=(gx-x0)/res; d.line([(X,0),(X,ny)], fill=(60,60,90)); d.text((X+2,2), str(gx), fill=(200,200,255))
for gy in np.arange(np.ceil(y0), y1, 0.5):
    Y=(y1-gy)/res; d.line([(0,Y),(nx,Y)], fill=(60,60,90)); d.text((2,Y+2), str(gy), fill=(200,200,255))
im.save(sys.argv[6])
