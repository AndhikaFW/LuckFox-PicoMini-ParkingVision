"""
Imports the real "LuckFox RAP Shield.step" into camera_housing.FCStd and places it
on top of the Base's standoffs, so the PCB is visible in the assembly.

Run:
    cd camera-housing
    QT_QPA_PLATFORM=offscreen ~/Downloads/FreeCAD-1.1.3.AppImage --console <<'EOF'
    exec(open('assemble_pcb.py').read())
    EOF

Coordinate note (verified against the STEP geometry directly, not assumed): KiCad's
STEP exporter negates Y (screen-Y-down -> world-Y-up convention) while leaving X and Z
unchanged. Confirmed by reading the 4 real M3 mounting-hole circle centers straight out
of the imported shape:
    KiCad absolute (117, 78.9)  -> STEP (117, -78.9)
    KiCad absolute (117, 134.3) -> STEP (117, -134.3)
    KiCad absolute (154, 134.3) -> STEP (154, -134.3)
    KiCad absolute (154, 78.9)  -> STEP (154, -78.9)
So the shape is mirrored back across the Y=0 plane (recovers exact raw KiCad absolute
coordinates -- verified the 4 holes land on (117,78.9) etc. exactly after mirroring),
then translated by (pcb_origin - board_corner) to sit on the Base standoffs, using the
exact same MOUNT_HOLES / pcb_origin numbers as build_housing.py.
"""

import Import
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else os.getcwd())

import build_housing as H  # reuses the same MARGIN/FLOOR_T/STANDOFF_H constants

STEP_PATH = os.path.join(
    H.OUT_DIR, "..", "LuckFox-RAP-Shield-PCB", "3d", "LuckFox RAP Shield.step"
)
STEP_PATH = os.path.abspath(STEP_PATH)

FCSTD_PATH = os.path.join(H.OUT_DIR, "camera_housing.FCStd")

BOARD_CORNER = (112.9978, 75.0)  # KiCad absolute XY of the board's bottom-left corner
PCB_ORIGIN = (H.MARGIN, H.PCB_ORIGIN_Y, H.FLOOR_T + H.STANDOFF_H)


def main():
    doc = App.openDocument(FCSTD_PATH)

    tmp_name = "StepImportTmp"
    if tmp_name in App.listDocuments():
        App.closeDocument(tmp_name)
    tmp = App.newDocument(tmp_name)
    Import.insert(STEP_PATH, tmp_name)

    board = None
    for o in tmp.Objects:
        if o.TypeId == "Part::Feature":
            board = o
            break
    if board is None:
        raise RuntimeError("No Part::Feature found in imported STEP")

    shape = board.Shape.copy()
    mirrored = shape.mirror(App.Vector(0, 0, 0), App.Vector(0, 1, 0))

    dx = PCB_ORIGIN[0] - BOARD_CORNER[0]
    dy = PCB_ORIGIN[1] - BOARD_CORNER[1]
    dz = PCB_ORIGIN[2] - 0.0
    mirrored.translate(App.Vector(dx, dy, dz))

    App.closeDocument(tmp_name)

    existing = doc.getObject("PCB")
    if existing:
        doc.removeObject("PCB")
    pcb_obj = doc.addObject("Part::Feature", "PCB")
    pcb_obj.Shape = mirrored

    doc.recompute()

    bb = mirrored.BoundBox
    print(
        "PCB placed bbox: X %.4f..%.4f  Y %.4f..%.4f  Z %.4f..%.4f"
        % (bb.XMin, bb.XMax, bb.YMin, bb.YMax, bb.ZMin, bb.ZMax)
    )
    print(
        "expected footprint: X %.4f..%.4f  Y %.4f..%.4f"
        % (
            PCB_ORIGIN[0],
            PCB_ORIGIN[0] + H.PCB_W,
            PCB_ORIGIN[1],
            PCB_ORIGIN[1] + H.PCB_H,
        )
    )

    doc.save()
    print("Saved:", FCSTD_PATH)


if __name__ == "__main__":
    main()
