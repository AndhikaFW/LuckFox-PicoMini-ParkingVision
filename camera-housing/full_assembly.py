"""
Combines camera_casing.py's pan/tilt rig (CeilingMount + ComponentBox + CameraBody +
BackCover) with the real PCB (STEP import), so the whole thing can be
viewed/checked together in one FCStd.

Since the PCB now lives INSIDE CameraBody (see camera_casing.py's docstring for why),
this script no longer needs build_housing.py's Base/Standoffs at all -- CameraBody
already has its own PCB standoffs fused directly into its shell. build_housing.py is
still imported (via camera_casing.py) only for the PCB/SC3336 dimension constants.

Run:
    cd camera-housing
    QT_QPA_PLATFORM=offscreen ~/Downloads/FreeCAD-1.1.3.AppImage --console <<'EOF'
    exec(open('full_assembly.py').read())
    EOF
"""

import Import
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else os.getcwd())
import build_housing as H
import camera_casing as C

STEP_PATH = os.path.abspath(
    os.path.join(H.OUT_DIR, "..", "LuckFox-RAP-Shield-PCB", "3d", "LuckFox RAP Shield.step")
)
BOARD_CORNER = (112.9978, 75.0)


def main():
    doc = App.newDocument("FullAssembly")

    ceiling = C.build_ceiling_mount()
    doc.addObject("Part::Feature", "CeilingMount").Shape = ceiling

    turret, cx, pivot_y, pivot_z, channel_x = C.build_component_box_with_arms()
    turret_obj = doc.addObject("Part::Feature", "ComponentBox")
    turret_obj.Shape = turret
    turret_obj.Placement = App.Placement(App.Vector(0, 0, C.CEILING_T), App.Rotation())

    body = C.build_camera_body()
    body_obj = doc.addObject("Part::Feature", "CameraBody")
    body_obj.Shape = body

    world_pivot_z = pivot_z + C.CEILING_T
    cy = pivot_y - C.TILT_LOCAL_Y
    cz = world_pivot_z - C.TILT_LOCAL_Z
    body_obj.Placement = App.Placement(App.Vector(cx, cy, cz), App.Rotation())

    cover = C.build_back_cover()
    cover_obj = doc.addObject("Part::Feature", "BackCover")
    cover_obj.Shape = cover
    cover_obj.Placement = App.Placement(App.Vector(cx, cy + C.CASING_DEPTH, cz), App.Rotation())

    # --- real PCB, positioned at CameraBody's own internal pcb_origin (see
    # camera_casing.build_camera_body()), mirror-Y + translate same as assemble_pcb.py
    pcb_local = (C.WALL_T + C.MARGIN, C.WALL_T + C.CAM_MODULE_DEPTH, C.WALL_T + C.STANDOFF_H)

    tmp_name = "StepImportTmp"
    if tmp_name in App.listDocuments():
        App.closeDocument(tmp_name)
    tmp = App.newDocument(tmp_name)
    Import.insert(STEP_PATH, tmp_name)
    board = next(o for o in tmp.Objects if o.TypeId == "Part::Feature")
    pcb_shape = board.Shape.copy().mirror(App.Vector(0, 0, 0), App.Vector(0, 1, 0))
    # translate straight to CameraBody's world position in one step (pcb_local offset
    # PLUS the body's own cx,cy,cz) -- do NOT also set an object Placement afterwards,
    # that would double-apply the cx,cy,cz shift on top of what's already baked in here
    dx = pcb_local[0] - BOARD_CORNER[0] + cx
    dy = pcb_local[1] - BOARD_CORNER[1] + cy
    dz = pcb_local[2] - 0.0 + cz
    pcb_shape.translate(App.Vector(dx, dy, dz))
    App.closeDocument(tmp_name)

    pcb_obj = doc.addObject("Part::Feature", "PCB")
    pcb_obj.Shape = pcb_shape

    doc.recompute()

    # --- verify, don't assume: real collision + fit checks
    def overlap(a, b_):
        return doc.getObject(a).Shape.common(doc.getObject(b_).Shape).Volume

    for a, b_ in (
        ("CeilingMount", "ComponentBox"),
        ("ComponentBox", "CameraBody"),
        ("PCB", "CameraBody"),
    ):
        vol = overlap(a, b_)
        print("%s / %s overlap volume: %.4f" % (a, b_, vol))

    pcb_bb = pcb_obj.Shape.BoundBox
    body_bb = body_obj.Shape.BoundBox
    print("PCB world bbox: X %.2f..%.2f Y %.2f..%.2f Z %.2f..%.2f" % (
        pcb_bb.XMin, pcb_bb.XMax, pcb_bb.YMin, pcb_bb.YMax, pcb_bb.ZMin, pcb_bb.ZMax))
    print("CameraBody world bbox: X %.2f..%.2f Y %.2f..%.2f Z %.2f..%.2f" % (
        body_bb.XMin, body_bb.XMax, body_bb.YMin, body_bb.YMax, body_bb.ZMin, body_bb.ZMax))
    fits = (
        pcb_bb.XMin >= body_bb.XMin and pcb_bb.XMax <= body_bb.XMax
        and pcb_bb.YMin >= body_bb.YMin and pcb_bb.YMax <= body_bb.YMax
        and pcb_bb.ZMin >= body_bb.ZMin and pcb_bb.ZMax <= body_bb.ZMax
    )
    print("PCB bbox fully inside CameraBody bbox:", fits)

    # CameraBody's right bushing hole (where the arm's stationary spigot inserts, see
    # camera_casing.py) must clear the PCB -- it's coaxial with the tilt pivot
    # (TILT_LOCAL_Y/Z), which sits close to the PCB's own height, so this is checked
    # directly rather than assumed clear. Probe matches the hole's REAL extent (not a
    # full-width sweep -- an earlier version of this check used a full-width probe and
    # flagged a false positive, since a cable-shaped sweep spanning the entire body width
    # will always cross the PCB somewhere; that's not what's actually drilled).
    import Part
    bore_x0 = cx + C.CASING_W - C.WALL_T - C.BORE_ENGAGE - 1
    bore_len = C.HINGE_DISC_LEN + C.WALL_T + C.BORE_ENGAGE + 2
    cable_world_y = cy + C.TILT_LOCAL_Y
    cable_world_z = cz + C.TILT_LOCAL_Z
    cable_probe = Part.makeCylinder(
        C.CABLE_HOLE_D / 2.0, bore_len, App.Vector(bore_x0, cable_world_y, cable_world_z), App.Vector(1, 0, 0)
    )
    cable_pcb_overlap = cable_probe.common(pcb_obj.Shape).Volume
    print("Right bushing hole (real extent) / PCB overlap volume (expect 0):", cable_pcb_overlap)
    gap = bore_x0 - pcb_obj.Shape.BoundBox.XMax
    print("Open-air gap from the bushing hole's inner reach to the PCB's edge: %.2f mm" % gap)

    fcstd_path = os.path.join(H.OUT_DIR, "full_assembly.FCStd")
    doc.saveAs(fcstd_path)
    print("Saved:", fcstd_path)


if __name__ == "__main__":
    main()
