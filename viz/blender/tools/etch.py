"""The etch model for the 3D fab (docs/FAB-3D.md); see kit.py. From the SMT2020 testbed; not a real fab.

    Blender -b -P viz/blender/tools/etch.py -- --out data/fab3d/models/etch.glb
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit  # noqa: E402

kit.main("etch")
