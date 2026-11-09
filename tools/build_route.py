import sys, os, importlib.util
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapengine.seapath import sea_route
spec = importlib.util.spec_from_file_location("route", sys.argv[1]); R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
pts, lab = sea_route(R.ROUTE)
print(len(pts), lab)
# verify smoothed path
import numpy as np
from mapengine.seapath import _seg_hits_land
bad=[i for i in range(len(pts)-1) if _seg_hits_land(pts[i], pts[i+1])]
print("smoothed segments touching land:", len(bad), [tuple(np.round(pts[i],2)) for i in bad[:20]])
