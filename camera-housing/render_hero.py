"""
Genuine angled 3D render of full_assembly.FCStd, working around this offscreen FreeCAD
setup's real bug: viewIsometric() leaves the camera orientation at identity (angle=0, a
plain top-down view) even though it reports success -- confirmed by inspecting
view.getCamera() before/after the call. Manually constructing and setting the camera string
(with a real non-zero axis-angle orientation) fixes it.

Run:
    cd camera-housing
    QT_QPA_PLATFORM=offscreen ~/Downloads/FreeCAD-1.1.3.AppImage --console <<'EOF'
    exec(open('render_hero.py').read())
    EOF
"""

import math
import os
import FreeCADGui as Gui
import FreeCAD as App

OUT_DIR = os.getcwd()
FCSTD_PATH = os.path.join(OUT_DIR, "full_assembly.FCStd")

Gui.showMainWindow()
doc = App.openDocument(FCSTD_PATH)
Gui.ActiveDocument = Gui.getDocument(doc.Name)

# nice, distinct colors per part instead of flat uniform gray -- makes the assembly
# actually readable in a still image (which part is which)
COLORS = {
    "CeilingMount": (0.75, 0.76, 0.78),
    "ComponentBox": (0.55, 0.58, 0.62),
    "CameraBody": (0.85, 0.87, 0.90),
    "BackCover": (0.70, 0.72, 0.75),
    "PCB": (0.10, 0.45, 0.20),
}

body_obj = None
for obj in doc.Objects:
    if not hasattr(obj, "Shape"):
        continue
    vobj = Gui.ActiveDocument.getObject(obj.Name)
    # PCB is fully enclosed inside CameraBody (that's the whole point of this design) --
    # showing it here would only be visible as an odd green sliver through the lens hole,
    # an artifact of not modeling an actual lens assembly. Hide it for a clean product shot.
    vobj.Visibility = obj.Name != "PCB"
    color = COLORS.get(obj.Name, (0.8, 0.8, 0.8))
    vobj.ShapeColor = color
    vobj.LineColor = (0.15, 0.15, 0.15)
    if obj.Name == "CameraBody":
        body_obj = obj

# find CameraBody's front (lens) face -- its world bbox MIN-Y face, so the camera can be
# aimed to actually show the lens/bezel side rather than the back/mount side
body_bb = body_obj.Shape.BoundBox
scene_bb = None
for obj in doc.Objects:
    if hasattr(obj, "Shape"):
        if scene_bb is None:
            scene_bb = App.BoundBox(obj.Shape.BoundBox)
        else:
            scene_bb.add(obj.Shape.BoundBox)

center = App.Vector(
    (scene_bb.XMin + scene_bb.XMax) / 2.0,
    (scene_bb.YMin + scene_bb.YMax) / 2.0,
    (scene_bb.ZMin + scene_bb.ZMax) / 2.0,
)
diag = scene_bb.DiagonalLength

# camera looks toward the scene center from a point offset toward CameraBody's FRONT
# (min-Y side), up and to one side -- a classic 3/4 "product shot" angle
front_y = body_bb.YMin
cam_pos = App.Vector(center.x + diag * 0.55, front_y - diag * 0.55, center.z + diag * 0.45)

view_dir = (center - cam_pos)
view_dir.normalize()
up_hint = App.Vector(0, 0, 1)
right = view_dir.cross(up_hint)
right.normalize()
up = right.cross(view_dir)
up.normalize()

# build a rotation matrix from (right, up, -view_dir) as columns -> quaternion, matching
# how Coin3D cameras orient themselves (camera looks down its own -Z axis)
cam_z = view_dir.negative()
cam_x = right
cam_y = up

m = App.Matrix(
    cam_x.x, cam_y.x, cam_z.x, 0,
    cam_x.y, cam_y.y, cam_z.y, 0,
    cam_x.z, cam_y.z, cam_z.z, 0,
    0, 0, 0, 1,
)
rot = App.Rotation(m)
axis, angle = rot.Axis, rot.Angle

cam_str = """#Inventor V2.1 ascii

OrthographicCamera {{
  viewportMapping ADJUST_CAMERA
  position {px} {py} {pz}
  orientation {ax} {ay} {az}  {angle}
  nearDistance 1
  farDistance {far}
  aspectRatio 1.333
  focalDistance {focal}
  height {height}
}}
""".format(
    px=cam_pos.x, py=cam_pos.y, pz=cam_pos.z,
    ax=axis.x, ay=axis.y, az=axis.z, angle=angle,
    far=diag * 4, focal=diag * 0.8, height=diag * 0.9,
)

view = Gui.ActiveDocument.ActiveView
view.setCamera(cam_str)

img_path = os.path.join(OUT_DIR, "hero_render.png")
view.saveImage(img_path, 1600, 1200, "White")
print("Saved:", img_path)
