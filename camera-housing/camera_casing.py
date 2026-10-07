"""
Futuristic-minimalist camera BODY + manual 2-axis (pan/tilt) hinge.

The LuckFox RAP Shield PCB lives INSIDE this body along with the SC3336 module up front
behind the lens -- no external FPC run, the ribbon stays entirely inside one enclosure.
`build_housing.py`'s Base/Standoffs still exist and still work standalone if a flat
non-pivoting mount is ever wanted, but this file only imports board/PCB dimension
constants from it, not its build functions.

Heatsink work on the LuckFox Pico Mini still doesn't require touching the pan/tilt
mechanics: CameraBody has a removable BackCover (a few M3 self-tap screws) giving full
access to the PCB compartment without disturbing CeilingMount/ComponentBox/the hinge pins.

TILT HINGE IS ON THE LEFT/RIGHT SIDES of CameraBody (not a single bottom tab like the
first revision) -- two independent side pivots instead of one center yoke, on request.

STYLED AFTER DJI OSMO POCKET'S GIMBAL, on request: both pivots show the SAME flat disc
diameter (HINGE_DISC_OD) on CameraBody, whether solid (left) or bushing (right) -- not a
small boss on one side and a noticeably bigger one on the other. An earlier revision grew
the right boss alone (to ~22.4mm) just to contain its bushing hole while the left stayed
16mm; that was functionally fine but LOOKED like an odd separate "big tube" bolted on --
unifying both sides to one disc size fixes that. The reach was also shortened again in
this same pass (see "tightened" notes below) -- Osmo Pocket's pivot housings sit close and
flush, not on a long stalk.

THE SPIGOT LIVES ON THE ARM, NOT ON CAMERABODY. This is the key point: the arm (fixed to
ComponentBox) is STATIONARY with respect to TILT -- only CameraBody tilts (ComponentBox
itself does pan, but that's a separate axis, and the arm/spigot geometry is fixed relative
to ComponentBox regardless of pan angle). An earlier revision put the hollow shaft on
CameraBody instead (the part that ROTATES for tilt), which meant a hole connecting its bore
to anything else would only stay aligned across a limited tilt angle, since the hole would
sweep around as CameraBody rotated. Putting the spigot on the arm (stationary relative to
tilt) instead means a hole in its underside stays permanently connected to ComponentBox's
down-channel (see below) at ANY tilt angle -- no rotation-related misalignment, because
nothing at that joint is moving (tilt-wise).

Because of this, the two tilt pivots are mechanically different, and which side holds
which part matters:
  LEFT  pivot: solid, M5 wing bolt + wing nut through CameraBody's left disc and
               ComponentBox's left arm -- this is the structural/load-bearing side and the
               friction lock for the tilt angle.
  RIGHT pivot: ComponentBox's arm has a SHORT spigot (SPIGOT_OD outer, CABLE_HOLE_D bore,
               stationary relative to tilt, printed as one piece with the arm) -- just long enough
               (SPIGOT_LEN) to cross PIVOT_GAP and engage partway into CameraBody's disc,
               for real rotational support without reaching all the way to the wall. The
               CABLE's own path is a separate, longer bore cut independently (see below) --
               decoupled from how much solid spigot material there is. CameraBody's right
               disc just has a plain round bushing hole (same HINGE_DISC_OD outside, no
               spigot of its own) that the arm's spigot inserts into and rotates around. A
               radial M4 set-screw through CameraBody's disc (the ROTATING part now)
               presses inward on the stationary spigot for friction-lock.
  Retention caveat (search "NOT positively retained" below): the spigot isn't positively
  locked against CameraBody sliding back off it, only friction-held by the set-screw and
  by the left bolt keeping the body's attitude fixed. Fine for a first build; add a dab of
  glue or a zip-tie there if more security is wanted.

THE PAN PIVOT IS ALSO SOLID (plain M5 bolt, like the left tilt pivot) -- it does not carry
the cable either. Cable path, entirely enclosed the whole way (on request -- never open to
outside air, and never exiting any side face):
  right tilt spigot's bore -> continues through the arm's own body (one continuous bore,
  independent of the spigot's own shorter length) -> turns down through a hidden vertical
  channel inside the arm -> crosses ComponentBox's own top wall (ONE wall-hop now, not two
  -- see "COMPONENTBOX IS NOW A ROUND ROTATING TURRET" above for why) -> arrives inside
  ComponentBox's own interior, where the W5500 + buck converter will eventually live
  (mounting for them still not designed, out of scope for now).
CeilingMount has NO cable hole -- the electronics moved onto the rotating ComponentBox
itself, so there's nothing left for the cable to reach past ComponentBox's own interior.
NOTE this channel is off-center (at the arm's own position, not the pan axis), so it only
stays usably positioned relative to ComponentBox's interior across a LIMITED pan range
before rotating away from wherever the modules eventually get mounted inside it -- an
accepted tradeoff for keeping the pan pivot solid, not a full swivel connector. (The TILT
side doesn't have this limitation, per the "spigot on the stationary part" reasoning above
-- only pan does, since the pan pivot was deliberately kept solid instead of also being
hollow.)

SYMMETRIC ARMS, on request ("buat kedua lengan sama dimensinya"): both side arms share the
exact same `ARM_T` (thickness) and `ARM_W` (width) -- an earlier revision kept the left arm
slimmer since it never needed the down-channel's clearance margin, but unifying both to the
wider value the channel actually needs is what was asked for. The arms no longer need to
stay strictly within a square footprint (that constraint was specific to the earlier
square-box ComponentBox revision, "tidak keluar area kotak") -- now that ComponentBox is a
round turret, `TURRET_D` just needs to be big enough that the arms genuinely overlap/fuse
onto its own top face (checked via real FreeCAD bounding-box queries, not assumed, see
README), not that they stay fully inside its silhouette.

ARM_T (14mm, BOTH arms share this thickness, on request) was originally the RIGHT arm's own
wider value: the down-channel (10mm) needs to be fully enclosed with wall margin on both
faces, or it breaches through the arm's own front/back and becomes a visible stray hole --
which is what prompted an earlier cleanup pass (search "tidak terlihat" in the project
history / README). The left arm used to stay slimmer (6mm) since it never needed that
margin, but on request both arms are identical -- see "Symmetric arms" above.

Hinge hardware: M5 wing bolt + wing nut (pan pivot AND the left tilt pivot -- both stay
solid/structural), plus one M4 set-screw (right tilt pivot only, pressing on the
stationary spigot from CameraBody's rotating disc). Confirmed real, cheap, commonly
stocked (searched, not guessed): "WING NUT M4 M5 M6 M8 M10 ... MUR KUPING MUR KUPU KUPU"
on Tokopedia lists M4/M5 together. No bearings, no custom hollow bolts, no exotic
hardware -- the "spigot" is just a short printed shaft, part of ComponentBox's arm itself.

CAMERABODY IS NOW A SQUARE-CROSS-SECTION TUBE ("tabung persegi", on request): CASING_W and
CASING_H are equal (both driven up to CASING_W, since that's set by the real PCB width and
can't shrink) -- the body reads as a square tube extruded along its depth, not the flatter
rectangular box the first several revisions used. This is strictly MORE interior room than
the PCB/component stack needs (see _CASING_H_MIN), never less -- a styling choice, not a
fit requirement.

COMPONENTBOX IS NOW A ROUND ROTATING TURRET, on request ("rubah kotak diatas kamera ...
menjadi tabung bundar supaya dapat berputar"): this replaces the old MountPlate<->PanPlate
pan-pivot pair entirely. Explicitly confirmed with the user before building this (two
readings were possible -- just reshape ComponentBox into a cylinder while keeping it fixed,
or make ComponentBox itself the rotating part -- the user picked the latter: "ComponentBox
sendiri yang berputar").

New topology: a small FIXED `CeilingMount` plate (screws to wall/pole/ceiling bracket,
takes over MountPlate's old "fixed, generic mounting pattern" role) sits at the bottom of
the stack. `ComponentBox` is now a round, CLOSED cylinder (own top + bottom + side walls,
no separate lid needed anymore) that ROTATES on top of CeilingMount via a plain M5 wing
bolt + wing nut through both their centers (same friction-lock hardware pattern as every
other pivot in this design) -- and it's ComponentBox itself, not a separate PanPlate, that
the two side arms are now fused to. This merges what used to be THREE separate parts
(ComponentBox as a fixed electronics box + MountPlate as a fixed lid + PanPlate as the
rotating arm-holder) into TWO (CeilingMount fixed, ComponentBox rotating-with-arms).

Practical effect on the cable path: it used to be CameraBody -> arm -> PanPlate's own
down-channel -> a matching hole through MountPlate -> ComponentBox's interior (two
plate-hops). Now that the arms sit directly on ComponentBox's own top wall, the channel
only has to cross ONE wall (ComponentBox's own WALL_T-thick top) to reach the same
interior -- CeilingMount needs no cable hole at all anymore (reverted to a plain plate,
like the very first MountPlate design, since the electronics moved off of it).

`ComponentBox`'s pivot hole is on its BOTTOM face (mating with CeilingMount below it); the
arms are fused to its TOP face (same face they used to fuse to on PanPlate) -- these are
deliberately on OPPOSITE faces of the cylinder so the fixed pivot connection and the arm
attachment area can't physically collide with each other.

Assembly stack, all separate FreeCAD objects (not fused, so they can actually move
against each other once printed/assembled):
  CeilingMount -- NEW, FIXED, sits at the bottom of the stack (wherever this gets
                mounted). Plain M5 pan-pivot hole + 4 corner mounting holes, nothing else
                -- no cable routing through it anymore.
  ComponentBox -- NEW SHAPE: a round, closed cylindrical turret that ROTATES on top of
                CeilingMount (pan = left/right). Houses the buck converter + W5500 module
                eventually (no mounting designed for them yet, on request), and the two
                side arms are fused directly to its own top face, now IDENTICAL in
                thickness/width (on request -- left: M5 hole; right: the stationary spigot
                + bore + the hidden downward cable channel, now only one wall-hop deep,
                see above).
  CameraBody -- the camera shell (square-cross-section tube), PCB + SC3336 module inside.
                Left disc: solid, M5 hole. Right disc: same OD, with a bushing hole that
                the arm's stationary spigot inserts into -- CameraBody is what rotates
                here (tilt -- a SEPARATE axis from ComponentBox's own pan rotation).
  BackCover  -- separate, plugs CameraBody's open back. Remove only this for PCB access.

Run headlessly (same pattern as build_housing.py):
    cd camera-housing
    QT_QPA_PLATFORM=offscreen ~/Downloads/FreeCAD-1.1.3.AppImage --console <<'EOF'
    exec(open('camera_casing.py').read())
    EOF

ASSUMED values (search "ASSUMED" below): SC3336 board/lens dimensions and
COMPONENT_CLEARANCE are reused/defined here; PCB dimensions (CONFIRMED) come from
build_housing.py so there's exactly one place holding each number.
"""

import FreeCAD as App
import Part
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else os.getcwd())
import build_housing as H  # reuse PCB (CONFIRMED) + SC3336/lens (ASSUMED) constants only

# ============================================================================
# ASSUMED / PLACEHOLDER -- verify against real hardware before printing.
# ============================================================================
COMPONENT_CLEARANCE = 18.0      # ASSUMED: tallest stack above the PCB (ESP32 Dev Board
                                 # Breakout on pin headers) -- measure the real populated
                                 # board and adjust.
CAM_MODULE_DEPTH = 15.0         # ASSUMED: front cavity depth for the SC3336 board + lens
                                 # holder, from the inside of the front wall.

# ============================================================================
# Design choices (freely adjustable)
# ============================================================================
WALL_T = 3.0                    # body shell thickness
MARGIN = 5.0                    # clearance around the PCB inside the body (same value
                                 # build_housing.py used for its flat Base, reused here)
FILLET_R = 2.5                  # edge rounding on the body's 4 vertical edges -- the
                                 # "minimalist" cue; must stay under WALL_T (3.0mm) since
                                 # BackCover's flat plate is only WALL_T thick, or the
                                 # fillet operation fails there
LENS_BEZEL_R = H.LENS_HOLE_D / 2.0 + 4.0   # recessed ring around the lens, minimalist
LENS_BEZEL_DEPTH = 1.5

CAM_BOARD_STANDOFF_H = 6.0      # SC3336 board standoffs, sticking out from the front wall
CAM_BOARD_STANDOFF_D = 4.0
CAM_BOARD_PILOT_D = 1.8          # self-tap pilot for the SC3336 board's own M2 screws

STANDOFF_HEX_AF = H.STANDOFF_HEX_AF    # PCB standoffs: same bought M3 hex spacers as
STANDOFF_H = H.STANDOFF_H              # build_housing.py used, just mounted inside this
STANDOFF_HOLE_D = H.STANDOFF_HOLE_D    # body's floor instead of on a flat Base

COVER_SKIRT_DEPTH = 6.0         # how far BackCover's skirt inserts into the open back
COVER_FIT_GAP = 0.3
COVER_SCREW_D = 2.5              # M3 self-tap pilot, BackCover to CameraBody
COVER_BACK_CLEARANCE = 2.0       # extra open-air gap between the PCB's back edge and
                                  # where BackCover's skirt begins -- MARGIN alone used to
                                  # be the only buffer there, which was thinner
                                  # (5mm) than the skirt itself (6mm), so the skirt
                                  # clipped into the PCB. Fixed by making CASING_DEPTH
                                  # explicitly account for the skirt + this extra margin.

HINGE_PIN_D = 5.3                # M5 wing bolt clearance (LEFT tilt pivot + pan pivot --
                                  # both stay solid/structural)
CABLE_HOLE_D = 10.0               # bore through the spigot -- the cable's actual path

HINGE_DISC_OD = 24.0               # BOTH pivots (left solid, right hollow) use this SAME
                                  # disc diameter now -- styled after DJI Osmo Pocket's
                                  # gimbal, where the arm and the module meet as matching
                                  # flush discs, not a small boss on one side and a big one
                                  # on the other. An earlier revision had the right boss
                                  # grow to ~22.4mm (RIGHT_BOSS_OD) just to contain its
                                  # bushing hole while the left stayed 16mm -- functionally
                                  # fine, but the size mismatch was exactly what looked like
                                  # an odd separate "big tube" bolted on, on request, fixed
                                  # by unifying both sides to one consistent disc size.
HINGE_DISC_LEN = 4.0               # short and flat, like Osmo Pocket's pivot housing --
                                  # replaces the old SIDE_BOSS_LEN-style long boss
PIVOT_GAP = 0.5                   # small clearance between the two discs, so they can
                                  # rotate against each other without rubbing

SPIGOT_OD = 16.0                   # RIGHT only: short alignment pin on the ARM's disc
                                  # (stationary), inserting into CameraBody's disc just far
                                  # enough for rotational support -- NOT a long tube
                                  # reaching all the way to the interior anymore; that job
                                  # is now the bore's alone (see below), decoupled from how
                                  # much solid spigot material there is
SPIGOT_LEN = 4.0                   # crosses PIVOT_GAP and reaches most of the way through
                                  # CameraBody's disc (HINGE_DISC_LEN) for real mechanical
                                  # engagement, without needing to reach the wall/interior
BUSHING_CLEARANCE = 0.4           # diameter clearance, CameraBody's hole vs. the spigot's
                                  # OD -- loose enough to actually rotate once printed
SETSCREW_PILOT_D = 3.3            # M4 self-tap pilot, pressing onto the spigot for
                                  # friction-lock (drilled through CameraBody's rotating
                                  # disc, from outside -- see build_camera_body())
BORE_ENGAGE = 1.0                 # how far the RIGHT cable bore reaches past the inner
                                  # wall face into CameraBody's cavity (kept short --
                                  # checked, not assumed, that it still clears the PCB;
                                  # see README). This is the bore's own reach, independent
                                  # of the spigot's shorter SPIGOT_LEN -- past the spigot's
                                  # tip, the cable just continues through open (already
                                  # cut) hole, no solid material needed there.

DOWN_CHANNEL_D = 10.0             # the hidden channel inside the arm + ComponentBox's own
                                  # top wall (from the spigot's bore down into the turret's
                                  # interior) -- same diameter as CABLE_HOLE_D, named
                                  # separately since it's a distinct feature (not coaxial
                                  # with a pivot)

# CASING_W needed below (TURRET_D depends on it) -- pulled up ahead of the rest of the
# "body dimensions" block further down, which still uses it (not duplicated)
CASING_W = H.PCB_W + 2 * MARGIN + 2 * WALL_T

ARM_T = 14.0                      # BOTH side arms use this SAME thickness (X direction),
                                  # on request ("buat kedua lengan sama dimensinya") -- an
                                  # earlier revision kept the left arm slim (6mm, just
                                  # enough for its M5 hole) and only the right arm wide
                                  # (14mm, needed so DOWN_CHANNEL_D (10mm) stays fully
                                  # enclosed with wall margin on both faces, or it breaches
                                  # through as a visible stray hole); unifying both to the
                                  # right arm's wider value is what the channel needs
ARM_DISC_COVER = 2.0              # how far the arm posts must exceed HINGE_DISC_OD's own
                                  # radius/diameter, so the post visibly COVERS the hinge
                                  # disc instead of the disc overhanging past a narrower
                                  # post -- an earlier revision made the arm narrower than
                                  # the disc on purpose (Osmo-Pocket "slim arm" look), but
                                  # that made the disc look bigger than its own support, on
                                  # request, fixed by tying the post's size to the disc's
ARM_W = HINGE_DISC_OD + 2 * ARM_DISC_COVER   # width (Y direction) now exceeds the disc's
                                              # own diameter on both sides, not the other
                                              # way around -- same for both arms
ARM_TOP_MARGIN = HINGE_DISC_OD / 2.0 + ARM_DISC_COVER   # reaches past the disc's own top
                                                        # edge too (disc's radius + margin),
                                                        # not just partway up it

# ---- ComponentBox: round ROTATING turret, on request ("rubah kotak ... menjadi tabung
# bundar supaya dapat berputar") -- houses the buck converter + W5500 Ethernet module
# eventually (no mounting designed for them yet, "tidak perlu dibuat dudukan untuk
# sekarang"), AND now carries the two side arms directly (see module docstring for the
# full topology change). TURRET_D is sized off REAL searched module dimensions (not
# guessed): a common LM2596 buck module is 43.2 x 21 x 14mm, and a W5500 module with an
# RJ45 jack is ~55 x 28 x 15mm -- both fit comfortably within a 110mm-diameter circle side
# by side, with real margin left over (checked, not assumed -- see README). TURRET_H
# clears the taller module (15mm) with real room for wiring above it.
TURRET_D = 110.0                  # ASSUMED placeholder, same reasoning as the old
                                  # BOX_SIZE/PLATE_SIZE -- exact component placement inside
                                  # still isn't designed. Unlike the old square box, the
                                  # arms are NOT required to stay fully within this
                                  # footprint anymore (see "Symmetric arms" in the module
                                  # docstring) -- they just need to genuinely overlap/fuse
                                  # onto the turret's own top face, checked below.
TURRET_H = 25.0                   # same value/reasoning as the old BOX_H

# ---- CeilingMount: the new FIXED base, on request -- takes over the old MountPlate's
# "generic mounting pattern, screws to whatever bracket" role, but carries no electronics
# and no cable hole anymore (that moved onto the rotating ComponentBox, see docstring)
CEILING_SIZE = TURRET_D           # square footprint, sized to visually match the turret's
                                  # own diameter -- not a functional constraint, since this
                                  # plate only needs the pivot hole + 4 mount holes
CEILING_T = 5.0                   # same value/role as the old PLATE_T
CEILING_MOUNT_HOLE_D = 5.3        # M5 clearance, generic mounting pattern to whatever this
                                  # attaches to (wall bracket, off-the-shelf CCTV pole
                                  # bracket -- e.g. "Adjustable Bracket Tiang Kamera CCTV"
                                  # on Tokopedia, confirmed real listing)
CEILING_MOUNT_INSET = 8.0

# ---- body dimensions, driven by the real PCB + the SC3336/component ASSUMED values ----
# (CASING_W itself is defined earlier, above ARM_T -- TURRET_D needs it too)
_CASING_H_MIN = STANDOFF_H + H.PCB_T + COMPONENT_CLEARANCE + 2 * WALL_T  # what the PCB +
                                  # component stack actually needs -- 40.6mm
CASING_H = CASING_W               # SQUARE cross-section tube, on request ("badan kamera
                                  # tabung persegi") -- CASING_W can't shrink (it's set by
                                  # the real PCB width + margins), so CASING_H grows to
                                  # match it instead, well above the _CASING_H_MIN it
                                  # actually needs; the extra vertical room is just spare
                                  # interior, not a fit problem
assert CASING_H >= _CASING_H_MIN, "square cross-section is smaller than the PCB/component stack needs"
# back stays open (BackCover) -- explicitly includes the cover's own skirt depth so the
# skirt can't clip into the PCB (see COVER_BACK_CLEARANCE above)
CASING_DEPTH = (
    WALL_T + CAM_MODULE_DEPTH + H.PCB_H + MARGIN + COVER_BACK_CLEARANCE + COVER_SKIRT_DEPTH
)

# hinge pivot position, in CameraBody's own local frame -- centered both in depth and
# height so the body balances reasonably around the tilt axis. The right shaft's cable
# bore is coaxial with this SAME point (it has to be, mechanically -- both sides of a
# trunnion must share one axis or the body binds/wobbles instead of tilting cleanly).
# Checked, not assumed: at this Z the PCB's own solid material doesn't actually reach the
# side walls (PCB's local X range stops ~8mm short of them, see README), so the bore
# breaching the wall doesn't cut into the PCB -- but the cable, once through, does emerge
# at roughly the PCB's own height and has to be routed around its edge by hand at
# assembly time, not through any additionally-modeled channel.
TILT_LOCAL_Y = CASING_DEPTH / 2.0
TILT_LOCAL_Z = CASING_H / 2.0

OUT_DIR = H.OUT_DIR


def box(l, w, h, pos=(0, 0, 0)):
    b = Part.makeBox(l, w, h)
    b.translate(App.Vector(*pos))
    return b


def cyl(r, h, pos=(0, 0, 0), direction=(0, 0, 1)):
    return Part.makeCylinder(r, h, App.Vector(*pos), App.Vector(*direction))


def fillet_vertical_edges(shape, radius):
    edges = []
    for e in shape.Edges:
        v = e.Vertexes
        if len(v) == 2 and abs(v[0].X - v[1].X) < 1e-6 and abs(v[0].Y - v[1].Y) < 1e-6:
            edges.append(e)
    if not edges:
        return shape
    return shape.makeFillet(radius, edges)


def fillet_vertical_and_cap_edges(shape, radius, cap_axis, cap_value):
    """Rounds the 4 vertical edges (full length) PLUS the 2 horizontal edges of ONE
    specific capping face (chosen by cap_axis='x'/'y'/'z' and cap_value, e.g. cap_axis='y',
    cap_value=0 for CameraBody's front/lens face) -- giving a rounded "capsule" look on that
    one face and continuously rounded sides, WITHOUT touching the opposite face's edges.
    Used where the opposite face is a functional mating surface that needs to stay flat/
    sharp (CameraBody's open back, for BackCover's skirt to nest into) -- rounding that
    side too would need the mating part's own profile to match, which isn't done here."""
    idx = {"x": 0, "y": 1, "z": 2}[cap_axis]
    edges = []
    for e in shape.Edges:
        v = e.Vertexes
        if len(v) != 2:
            continue
        p0, p1 = v[0].Point, v[1].Point
        vertical = abs(p0.x - p1.x) < 1e-6 and abs(p0.y - p1.y) < 1e-6
        c0, c1 = (p0.x, p0.y, p0.z)[idx], (p1.x, p1.y, p1.z)[idx]
        cap_horizontal = abs(c0 - c1) < 1e-6 and abs(c0 - cap_value) < 1e-6
        if vertical or cap_horizontal:
            edges.append(e)
    if not edges:
        return shape
    return shape.makeFillet(radius, edges)


def build_ceiling_mount():
    """Fixed base plate, replacing the old MountPlate (on request -- see "COMPONENTBOX IS
    NOW A ROUND ROTATING TURRET" in the module docstring for the full topology change).
    Plain M5 pan-pivot hole + 4 corner mounting holes, nothing else -- no cable hole
    anymore, since the electronics moved onto the rotating ComponentBox itself, so there's
    nothing left for a cable to reach past this plate."""
    plate = box(CEILING_SIZE, CEILING_SIZE, CEILING_T)
    plate = fillet_vertical_edges(plate, FILLET_R)

    center = (CEILING_SIZE / 2.0, CEILING_SIZE / 2.0)
    pivot_hole = cyl(HINGE_PIN_D / 2.0, CEILING_T + 1.0, (center[0], center[1], -0.5))
    plate = plate.cut(pivot_hole)

    for dx in (CEILING_MOUNT_INSET, CEILING_SIZE - CEILING_MOUNT_INSET):
        for dy in (CEILING_MOUNT_INSET, CEILING_SIZE - CEILING_MOUNT_INSET):
            hole = cyl(CEILING_MOUNT_HOLE_D / 2.0, CEILING_T + 1.0, (dx, dy, -0.5))
            plate = plate.cut(hole)

    return plate


def build_component_box_with_arms():
    """Returns (turret, cx, pivot_y, pivot_z, channel_x). ComponentBox is now a round,
    ROTATING turret (on request, "rubah kotak ... menjadi tabung bundar supaya dapat
    berputar") -- see module docstring for the full topology change (this used to be a
    fixed square box, with a separate PanPlate carrying the arms; now ComponentBox itself
    is round, rotates on CeilingMount, and carries the arms directly).

    Pivot hole is on the BOTTOM face (mates with CeilingMount below it); the two side arms
    are fused to the TOP face -- deliberately on OPPOSITE faces of the cylinder so the
    fixed pivot connection and the arm attachment area can't physically collide (checked,
    not assumed -- see README)."""
    center = (TURRET_D / 2.0, TURRET_D / 2.0)
    turret = cyl(TURRET_D / 2.0, TURRET_H, (center[0], center[1], 0.0))
    # NOT filleting the rims: tried rounding the top rim with a full-circular-edge fillet,
    # but OCC's fillet on a FULL 360-degree closed circular edge doesn't round it inward
    # like a normal edge fillet -- it balloons the radius outward instead (checked, not
    # assumed: a plain unfilleted TURRET_D=110mm cylinder measured bbox X 0..110 as
    # expected, but after that fillet call the SAME cylinder measured X -4.53..114.53, a
    # real ~4.5mm radius INCREASE, not a rounded-off corner). Left sharp for now rather
    # than ship a shape that's silently bigger than its own stated diameter; revisit with a
    # proper chamfer or a revolved profile if a rounded rim is wanted later.

    inner = cyl(
        TURRET_D / 2.0 - WALL_T, TURRET_H - 2 * WALL_T,
        (center[0], center[1], WALL_T),
    )
    turret = turret.cut(inner)

    # pan pivot: plain M5 bolt hole through the BOTTOM wall only, solid/structural like the
    # left tilt pivot -- it does NOT carry the cable (see module docstring for where the
    # cable actually goes instead)
    pivot_hole = cyl(HINGE_PIN_D / 2.0, WALL_T + 2.0, (center[0], center[1], -1.0))
    turret = turret.cut(pivot_hole)

    cx = TURRET_D / 2.0 - CASING_W / 2.0
    pivot_y = TURRET_D / 2.0
    pivot_z = TURRET_H + TILT_LOCAL_Z + 10.0   # +10mm so CameraBody's lower half (which
                                               # hangs TILT_LOCAL_Z below the pivot)
                                               # clears the turret underneath it

    # LEFT arm: post starts right after CameraBody's disc + PIVOT_GAP -- short and simple,
    # a plain M5 hole is enough since a bolt (not a spigot) provides alignment here.
    left_x0 = cx - HINGE_DISC_LEN - PIVOT_GAP - ARM_T
    left_h = pivot_z + ARM_TOP_MARGIN - TURRET_H
    left = box(ARM_T, ARM_W, left_h,
               (left_x0, pivot_y - ARM_W / 2.0, TURRET_H - 0.01))
    left = fillet_vertical_edges(left, FILLET_R)   # rounded posts, matching the discs' look
    left_hole = cyl(HINGE_PIN_D / 2.0, ARM_T + 2, (left_x0 - 1, pivot_y, pivot_z), direction=(1, 0, 0))
    left = left.cut(left_hole)

    # RIGHT arm: this side is STATIONARY relative to CameraBody's tilt (fixed to
    # ComponentBox, doesn't tilt -- only CameraBody tilts; ComponentBox itself DOES pan,
    # but that's a separate axis from tilt). It carries the spigot (on request), NOT
    # CameraBody -- since it never rotates relative to CameraBody's tilt axis, a hole in
    # its underside stays permanently aligned with the down-channel below, at any tilt
    # angle (an off-axis hole on a ROTATING part, tried in an earlier revision, only stayed
    # aligned across a limited angle range; this doesn't have that limitation).
    #
    # No separate disc on the arm's own side -- only CameraBody needs one (to contain its
    # bushing hole; see module docstring on the Osmo-Pocket-style matching-disc fix). The
    # arm's flat post face sprouts the spigot directly, which keeps the reach SHORT (this
    # whole revision was a "the body-to-hinge distance is too far" request).
    right_x0 = cx + CASING_W + HINGE_DISC_LEN + PIVOT_GAP
    right_h = pivot_z + ARM_TOP_MARGIN - TURRET_H
    right = box(ARM_T, ARM_W, right_h,
                (right_x0, pivot_y - ARM_W / 2.0, TURRET_H - 0.01))
    right = fillet_vertical_edges(right, FILLET_R)   # rounded post, matching the left arm

    # the spigot: SHORT, just crosses PIVOT_GAP and reaches partway into CameraBody's disc
    # for real mechanical engagement (not all the way to the wall/interior -- the bore
    # below handles the cable's own longer reach independently)
    spigot = cyl(SPIGOT_OD / 2.0, SPIGOT_LEN, (right_x0, pivot_y, pivot_z), direction=(-1, 0, 0))
    right = right.fuse(spigot)

    # one continuous bore through the spigot AND partway into the arm's own body, just far
    # enough to reach the down-channel below (see README for how this was verified, not
    # assumed) -- stops at channel_x + a small overlap margin, NOT out at the arm's own
    # outer face. An earlier revision started this cut 1mm PAST the arm's outer face and
    # bored all the way through to the spigot, which meant the whole arm thickness got
    # drilled straight out its far side -- a real, visible hole open to outside air right
    # where the arm should look solid (caught after being asked "kenapa ada lobang besar di
    # luar lengan"). The two cuts still connect cleanly here: both cylinders share the same
    # Y center (pivot_y), and the down-channel already spans through Z=pivot_z at channel_x,
    # so reaching channel_x is enough -- no isthmus of material left between them.
    channel_x = right_x0 + ARM_T / 2.0
    horiz_bore_start_x = channel_x + 1.0
    horiz_bore_len = ARM_T / 2.0 + SPIGOT_LEN + 2
    horiz_bore = cyl(
        CABLE_HOLE_D / 2.0, horiz_bore_len,
        (horiz_bore_start_x, pivot_y, pivot_z), direction=(-1, 0, 0),
    )
    right = right.cut(horiz_bore)

    # hidden cable channel: straight down from where the horizontal bore passes through
    # the arm's own body, through ComponentBox's own top wall (ONE wall-hop now, on
    # request -- see module docstring for why this used to be two plate-hops), into its
    # hollow interior. The cable never leaves solid material/open-air-inside-the-parts
    # anywhere along the way, and never exits a side face -- not through the pan pivot
    # either. ARM_T is wide enough (with margin) to keep this fully enclosed instead of
    # breaching the arm's own front/back faces (checked -- see README).
    down_channel_len = pivot_z - (TURRET_H - WALL_T) + 2
    down_channel = cyl(
        DOWN_CHANNEL_D / 2.0, down_channel_len, (channel_x, pivot_y, pivot_z + 0.5), direction=(0, 0, -1)
    )
    right = right.cut(down_channel)
    turret = turret.cut(down_channel)

    turret = turret.fuse(left).fuse(right)

    return turret, cx, pivot_y, pivot_z, channel_x


def build_camera_body():
    outer = box(CASING_W, CASING_DEPTH, CASING_H)
    # rounded front ("capsule" cap, where the lens sits) + continuously rounded sides, on
    # request ("buat desain supaya lebih menarik") -- the BACK (Y=CASING_DEPTH) stays sharp
    # since BackCover's flat skirt needs a flat rectangular opening to mate against
    outer = fillet_vertical_and_cap_edges(outer, FILLET_R, "y", 0.0)

    # hollow interior -- open back (Y = CASING_DEPTH face) for BackCover; front (Y=0) and
    # the other 4 sides keep WALL_T of material
    inner = box(
        CASING_W - 2 * WALL_T, CASING_DEPTH - WALL_T + 1, CASING_H - 2 * WALL_T,
        (WALL_T, WALL_T, WALL_T),
    )
    shell = outer.cut(inner)

    lens_pos = (CASING_W / 2.0, -1.0, CASING_H / 2.0)
    lens_hole = cyl(H.LENS_HOLE_D / 2.0 + 0.5, WALL_T + 2, lens_pos, direction=(0, 1, 0))
    shell = shell.cut(lens_hole)

    # minimalist recessed bezel ring around the lens (front face only)
    bezel_outer = cyl(LENS_BEZEL_R, LENS_BEZEL_DEPTH + 0.5, (CASING_W / 2.0, -0.5, CASING_H / 2.0), direction=(0, 1, 0))
    bezel_inner = cyl(H.LENS_HOLE_D / 2.0 + 0.5, LENS_BEZEL_DEPTH + 1.5, (CASING_W / 2.0, -1.0, CASING_H / 2.0), direction=(0, 1, 0))
    bezel_cut = bezel_outer.cut(bezel_inner)
    shell = shell.cut(bezel_cut)

    # SC3336 board standoffs, sticking out from the inside of the front wall
    half_spacing = H.CAM_MOUNT_SPACING / 2.0
    board_y = WALL_T
    for dx in (-half_spacing, half_spacing):
        for dz in (-half_spacing, half_spacing):
            pos = (CASING_W / 2.0 + dx, board_y, CASING_H / 2.0 + dz)
            boss = cyl(CAM_BOARD_STANDOFF_D / 2.0, CAM_BOARD_STANDOFF_H, pos, direction=(0, 1, 0))
            pilot = cyl(CAM_BOARD_PILOT_D / 2.0, CAM_BOARD_STANDOFF_H + 1, pos, direction=(0, 1, 0))
            shell = shell.fuse(boss.cut(pilot))

    # PCB standoffs (bought M3 hex spacers, same as build_housing.py's Standoffs part),
    # behind the camera compartment, sitting on the body's floor
    pcb_origin = (WALL_T + MARGIN, WALL_T + CAM_MODULE_DEPTH)
    for (x, y) in H.MOUNT_HOLES:
        pos = (pcb_origin[0] + x, pcb_origin[1] + y, WALL_T)
        body_hex = H.hex_prism(STANDOFF_HEX_AF, STANDOFF_H, pos)
        bore = cyl(STANDOFF_HOLE_D / 2.0, STANDOFF_H + 1.0, (pos[0], pos[1], pos[2] - 0.5))
        shell = shell.fuse(body_hex.cut(bore))
        # floor pilot hole so a screw can reach the spacer from outside the (closed) floor
        floor_pilot = cyl(STANDOFF_HOLE_D / 2.0, WALL_T + 1.0, (pos[0], pos[1], -0.5))
        shell = shell.cut(floor_pilot)

    # LEFT tilt pivot: solid disc, M5 bolt through it (structural side). Same HINGE_DISC_OD
    # as the right side now -- see module docstring for why (DJI Osmo Pocket-style matching
    # discs instead of a small-left/big-right mismatch).
    left_disc = cyl(HINGE_DISC_OD / 2.0, HINGE_DISC_LEN, (0.0, TILT_LOCAL_Y, TILT_LOCAL_Z), direction=(-1, 0, 0))
    left_pivot_hole = cyl(
        HINGE_PIN_D / 2.0, HINGE_DISC_LEN + WALL_T + 2, (0.5, TILT_LOCAL_Y, TILT_LOCAL_Z), direction=(-1, 0, 0)
    )
    shell = shell.fuse(left_disc).cut(left_pivot_hole)

    # RIGHT tilt pivot: THIS side rotates (tilts) -- the spigot lives on the arm instead
    # (stationary relative to tilt, see build_component_box_with_arms()), so CameraBody
    # just needs a solid disc
    # (same HINGE_DISC_OD as the left) with a hole that the arm's spigot inserts into and
    # rotates inside. The hole reaches BORE_ENGAGE past the inner wall face into the
    # cavity, for the cable to continue past the spigot's own (shorter) tip -- checked to
    # still clear the PCB, not assumed -- see README.
    right_disc = cyl(HINGE_DISC_OD / 2.0, HINGE_DISC_LEN, (CASING_W, TILT_LOCAL_Y, TILT_LOCAL_Z), direction=(1, 0, 0))
    right_bushing_hole = cyl(
        (SPIGOT_OD + BUSHING_CLEARANCE) / 2.0, HINGE_DISC_LEN + WALL_T + BORE_ENGAGE + 2,
        (CASING_W - WALL_T - BORE_ENGAGE - 1, TILT_LOCAL_Y, TILT_LOCAL_Z), direction=(1, 0, 0),
    )
    shell = shell.fuse(right_disc).cut(right_bushing_hole)

    # radial set-screw through the disc (the ROTATING part now), pressing inward onto the
    # stationary spigot for friction-lock. Drilled from 2mm clear of the disc's own outer
    # surface down to 1mm INTO the spigot's outer surface (SPIGOT_OD/2, not
    # HINGE_DISC_OD/2) so it actually reaches and presses on the spigot, not just the
    # disc's own material around it.
    setscrew_top_z = TILT_LOCAL_Z + HINGE_DISC_OD / 2.0 + 2.0
    setscrew_bottom_z = TILT_LOCAL_Z + SPIGOT_OD / 2.0 - 1.0
    right_setscrew_pilot = cyl(
        SETSCREW_PILOT_D / 2.0, setscrew_top_z - setscrew_bottom_z,
        (CASING_W + HINGE_DISC_LEN / 2.0, TILT_LOCAL_Y, setscrew_top_z),
        direction=(0, 0, -1),
    )
    shell = shell.cut(right_setscrew_pilot)

    return shell


def build_back_cover():
    # Local Y=0 is the plane where this meets CameraBody's open back edge. The cap plate
    # extends OUTWARD (+Y, away from the body, Y 0..WALL_T) and the skirt extends INWARD
    # (-Y, into the body's hollow interior, Y -COVER_SKIRT_DEPTH..0) so it actually plugs
    # the opening instead of just butting up against it.
    #
    # not filleted -- WALL_T (3mm) is too thin relative to FILLET_R for OCC's fillet to
    # reliably succeed here, and the cover isn't a visible "styling" surface anyway (it
    # faces the mount/wall side)
    plate = box(CASING_W, WALL_T, CASING_H)

    skirt_outer = box(
        CASING_W - 2 * WALL_T - 2 * COVER_FIT_GAP, COVER_SKIRT_DEPTH,
        CASING_H - 2 * WALL_T - 2 * COVER_FIT_GAP,
        (WALL_T + COVER_FIT_GAP, -COVER_SKIRT_DEPTH, WALL_T + COVER_FIT_GAP),
    )
    cover = plate.fuse(skirt_outer)

    inset = 8.0
    for dx in (inset, CASING_W - inset):
        for dz in (inset, CASING_H - inset):
            hole = cyl(COVER_SCREW_D / 2.0 + 0.3, WALL_T + 1.0, (dx, -0.5, dz))
            cover = cover.cut(hole)

    return cover


def main():
    doc = App.newDocument("CameraCasing")

    # CeilingMount is FIXED, sits at Z=0 (bottom of the stack -- wherever this gets
    # mounted). ComponentBox (the round rotating turret) stacks on top of it.
    ceiling = build_ceiling_mount()
    doc.addObject("Part::Feature", "CeilingMount").Shape = ceiling

    turret, cx, pivot_y, pivot_z, channel_x = build_component_box_with_arms()
    turret_obj = doc.addObject("Part::Feature", "ComponentBox")
    turret_obj.Shape = turret
    # ComponentBox's own pivot hole (its BOTTOM face) sits right on top of CeilingMount's
    # own pivot hole -- the pan pivot (M5 bolt + wing nut through both central holes) is
    # what actually lets it rotate once printed/assembled; this Placement is just this
    # preview doc showing them pre-stacked.
    turret_obj.Placement = App.Placement(App.Vector(0, 0, CEILING_T), App.Rotation())

    body = build_camera_body()
    body_obj = doc.addObject("Part::Feature", "CameraBody")
    body_obj.Shape = body

    # place CameraBody so its side pivot bosses line up with the arms' pivot holes.
    # pivot_z from build_component_box_with_arms() is a LOCAL coordinate (within
    # ComponentBox's own unplaced shape); ComponentBox's own Placement then adds CEILING_T
    # on top of that when stacked on CeilingMount, so the true world Z needs that same
    # CEILING_T added here too.
    world_pivot_z = pivot_z + CEILING_T
    cy = pivot_y - TILT_LOCAL_Y
    cz = world_pivot_z - TILT_LOCAL_Z
    body_obj.Placement = App.Placement(App.Vector(cx, cy, cz), App.Rotation())

    cover = build_back_cover()
    cover_obj = doc.addObject("Part::Feature", "BackCover")
    cover_obj.Shape = cover
    cover_obj.Placement = App.Placement(
        App.Vector(cx, cy + CASING_DEPTH, cz), App.Rotation()
    )

    doc.recompute()

    fcstd_path = os.path.join(OUT_DIR, "camera_casing.FCStd")
    doc.saveAs(fcstd_path)

    for name in ("CeilingMount", "ComponentBox", "CameraBody", "BackCover"):
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
