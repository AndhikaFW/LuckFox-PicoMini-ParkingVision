"""
PCB mounting plate for one LuckFox-PicoMini-ParkingVision node (LuckFox RAP Shield PCB).

Camera mounting (SC3336 casing + manual pan/tilt hinge) lives entirely in
camera_casing.py now -- see full_assembly.py for how the two get combined onto one Base.
Base itself is just a flat plate + PCB standoffs; it no longer builds any camera-specific
geometry (the old Hood + fixed CameraPlate were removed once the pan-tilt CameraCasing
replaced them -- see git history if that flat/fixed version is ever needed again).

The PCB standoffs are a separate, non-printed part ("Standoffs"): plain hex male-female
M3 spacers, the kind sold off-the-shelf (confirmed via a real Tokopedia listing --
"Spacer Kuningan M3 Male Female", Prima Terang -- stocked in 5/6/8/10/15/20/25/30mm
lengths). Modeled here only as a reference/BOM shape (see STANDOFF_H/STANDOFF_HEX_AF
below), not something to print.

Run headlessly to (re)generate the FCStd/STL:
    QT_QPA_PLATFORM=offscreen ~/Downloads/FreeCAD-1.1.3.AppImage --console <<'EOF'
    exec(open('build_housing.py').read())
    EOF
or open in the FreeCAD GUI and run as a macro.

Two parameter blocks below:
  CONFIRMED   -- pulled directly from "LuckFox RAP Shield.kicad_pcb" (real board file).
  ASSUMED     -- placeholders because the exact figure isn't available yet (no datasheet
                 mechanical drawing / component not measured). MUST be checked against the
                 real hardware before this is sent to a printer. Search text "ASSUMED" to
                 find every one of these. (CAM_* / LENS_HOLE_D stay here even though Base
                 no longer uses them directly -- camera_casing.py imports them from this
                 module so there's exactly one place to correct the SC3336 guesses.)
"""

import FreeCAD as App
import Part
import os
import math

# ============================================================================
# CONFIRMED -- measured from LuckFox RAP Shield.kicad_pcb (edge cuts + mounting
# hole footprints), see camera-housing/README.md for how these were derived.
# ============================================================================
PCB_W = 45.0022          # board X extent (mm)
PCB_H = 63.2268          # board Y extent (mm)
PCB_T = 1.6               # board thickness (mm), from (thickness 1.6) stackup entry
MOUNT_HOLE_D = 3.2        # M3 clearance, MountingHole_3.2mm_M3 footprints
# relative to the board's bottom-left corner (112.9978, 75) in board coordinates
MOUNT_HOLES = [
    (4.0022, 3.9),
    (4.0022, 59.3),
    (41.0022, 59.3),
    (41.0022, 3.9),
]

# ============================================================================
# ASSUMED / PLACEHOLDER -- verify against real hardware before printing. Used by
# camera_casing.py, not by anything in this file (see module docstring).
# ============================================================================
CAM_BOARD_W = 20.0           # ASSUMED: SC3336 module board width -- no mechanical
CAM_BOARD_H = 20.0           # ASSUMED: drawing found publicly, only optical specs
CAM_BOARD_T = 1.5            # ASSUMED: (3.95mm focal length, F2.0, 1/2.8" CMOS).
CAM_MOUNT_HOLE_D = 2.2        # ASSUMED: M2 clearance guess
CAM_MOUNT_SPACING = 14.0     # ASSUMED: hole-to-hole spacing guess
LENS_HOLE_D = 9.5            # ASSUMED: lens barrel clearance

# ============================================================================
# Design choices (freely adjustable, not tied to any external spec)
# ============================================================================
MARGIN = 5.0                  # clearance around the PCB on the plate (both Y ends)
STANDOFF_H = 15.0             # standard off-the-shelf M3 hex spacer length (mm).
                               # Confirmed real stock sizes (Tokopedia, "Spacer Kuningan
                               # M3 Male Female", Prima Terang): 5, 6, 8, 10, 15, 20, 25,
                               # 30mm -- pick any of these once test-fitted.
STANDOFF_HEX_AF = 5.5         # ASSUMED: hex spacer across-flats (common M3 spacers are
                               # 5-6mm AF) -- reference geometry only, not toleranced
STANDOFF_HOLE_D = MOUNT_HOLE_D  # M3 clearance through the spacer, same as the PCB/base holes
FLOOR_T = 2.0                  # thin mounting plate

EXT_W = PCB_W + 2 * MARGIN
PCB_ORIGIN_Y = MARGIN
EXT_H = PCB_ORIGIN_Y + PCB_H + MARGIN

try:
    OUT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    OUT_DIR = os.getcwd()


def box(l, w, h, pos=(0, 0, 0)):
    b = Part.makeBox(l, w, h)
    b.translate(App.Vector(*pos))
    return b


def cyl(r, h, pos=(0, 0, 0), direction=(0, 0, 1)):
    return Part.makeCylinder(r, h, App.Vector(*pos), App.Vector(*direction))


def hex_prism(across_flats, height, pos=(0, 0, 0)):
    r = across_flats / math.sqrt(3)
    pts = []
    for i in range(6):
        angle = math.pi / 6 + i * math.pi / 3
        pts.append(App.Vector(r * math.cos(angle), r * math.sin(angle), 0))
    pts.append(pts[0])
    wire = Part.makePolygon(pts)
    face = Part.Face(wire)
    solid = face.extrude(App.Vector(0, 0, height))
    solid.translate(App.Vector(*pos))
    return solid


def build_base(ext_h=None):
    # thin flat mounting plate -- floor with M3 clearance holes only. `ext_h` lets
    # full_assembly.py request a longer plate (to fit the pan/tilt rig at the front)
    # without duplicating this function.
    h = EXT_H if ext_h is None else ext_h
    base = box(EXT_W, h, FLOOR_T)

    pcb_origin = (MARGIN, PCB_ORIGIN_Y if ext_h is None else h - PCB_H - MARGIN)
    for (x, y) in MOUNT_HOLES:
        pos = (pcb_origin[0] + x, pcb_origin[1] + y, -0.5)
        hole = cyl(MOUNT_HOLE_D / 2.0, FLOOR_T + 1.0, pos)
        base = base.cut(hole)

    return base


def build_standoffs(pcb_origin_y=None):
    # Reference/BOM geometry for 4x off-the-shelf M3 hex male-female spacers -- not
    # meant to be printed. See STANDOFF_H/STANDOFF_HEX_AF for the assumptions.
    pcb_origin = (MARGIN, PCB_ORIGIN_Y if pcb_origin_y is None else pcb_origin_y)
    standoffs = None
    for (x, y) in MOUNT_HOLES:
        pos = (pcb_origin[0] + x, pcb_origin[1] + y, FLOOR_T)
        body = hex_prism(STANDOFF_HEX_AF, STANDOFF_H, pos)
        bore = cyl(STANDOFF_HOLE_D / 2.0, STANDOFF_H + 1.0, (pos[0], pos[1], pos[2] - 0.5))
        one = body.cut(bore)
        standoffs = one if standoffs is None else standoffs.fuse(one)
    return standoffs


def main():
    doc = App.newDocument("CameraHousing")

    base = build_base()
    doc.addObject("Part::Feature", "Base").Shape = base

    standoffs = build_standoffs()
    doc.addObject("Part::Feature", "Standoffs").Shape = standoffs

    doc.recompute()

    fcstd_path = os.path.join(OUT_DIR, "camera_housing.FCStd")
    doc.saveAs(fcstd_path)

    for name in ("Base", "Standoffs"):
        obj = doc.getObject(name)
        bb = obj.Shape.BoundBox
        print(
            "%s bbox: %.2f x %.2f x %.2f mm, volume=%.1f mm3"
            % (name, bb.XLength, bb.YLength, bb.ZLength, obj.Shape.Volume)
        )
        stl_path = os.path.join(OUT_DIR, "%s.stl" % name)
        obj.Shape.exportStl(stl_path)
        print("  -> %s" % stl_path)

    print("Saved: %s" % fcstd_path)


if __name__ == "__main__":
    main()
