# Camera body + manual pan/tilt hinge (per parking-lot node)

One integrated camera body (LuckFox RAP Shield PCB + SC3336 module both INSIDE it) on a
manual 2-axis (pan + tilt) hinge, futuristic-minimalist styling. Four scripts:

- **`build_housing.py`** -- flat `Base` + `Standoffs` (a plain, non-pivoting PCB mounting
  plate). No longer used by the camera design below; kept because it's still a valid,
  independently-printable option if a flat non-pivoting mount is ever wanted, and because
  `camera_casing.py` imports the PCB/SC3336 dimension constants from it.
- **`camera_casing.py`** -- the actual camera design: `CeilingMount` (fixed) +
  `ComponentBox` (round, ROTATING turret -- placeholder enclosure for a future buck
  converter + W5500 module, also carries the pan/tilt arms) + `CameraBody` (the shell, PCB
  + SC3336 both inside, square-cross-section tube) + `BackCover` (removable, for
  PCB/heatsink access).
- **`assemble_pcb.py`** -- adds the real PCB (STEP import) onto `build_housing.py`'s Base,
  into `camera_housing.FCStd`. Only relevant if that flat mount is actually used.
- **`full_assembly.py`** -- combines `camera_casing.py`'s parts with the real PCB (STEP
  import, positioned inside `CameraBody`) into one `full_assembly.FCStd`.
- **`render_hero.py`** -- renders a genuine angled 3D shot (`hero_render.png`) from
  `full_assembly.FCStd`, working around the offscreen top-down-only bug the older render
  scripts hit (see "Regenerating everything" below for the actual root cause found).

## Regenerating everything

```bash
cd camera-housing
QT_QPA_PLATFORM=offscreen ~/Downloads/FreeCAD-1.1.3.AppImage --console <<'EOF'
exec(open('camera_casing.py').read())
EOF
QT_QPA_PLATFORM=offscreen ~/Downloads/FreeCAD-1.1.3.AppImage --console <<'EOF'
exec(open('full_assembly.py').read())
EOF
```
(`build_housing.py`/`assemble_pcb.py` only needed if you also want the standalone flat
mount -- see their own section below.)

The older renders (`render_casing.py`, `render_full.py`, `render_screenshot.py`) each
produce a `.png` from their matching `.FCStd`, but all render a straight-down top view
regardless of the `viewIsometric()` call in the script. **Root cause found**: inspecting
`view.getCamera()` right after `viewIsometric()` shows the camera's orientation is left at
identity (axis-angle `angle=0`) in this offscreen setup -- `viewIsometric()` silently fails
to actually rotate the camera here, even though it doesn't raise an error. `render_hero.py`
works around this by building and setting a real camera string directly (`view.setCamera(...)`
with a manually-computed non-identity orientation) instead of relying on `viewIsometric()`
-- confirmed via `getCamera()` showing a proper non-zero angle afterward, and the resulting
image actually being a real angled view, not another flat top-down one. Geometry
correctness in this project is still verified via real bounding-box/circle-center/
boolean-overlap queries first and foremost (see each section below for what was actually
checked) -- `render_hero.py` is for producing an actual presentable image, not for
verification.

(`--console camera_casing.py` as a direct CLI arg does *not* auto-run it in FreeCAD 1.1.3
-- pipe the `exec(...)` line into stdin as shown, or open the files as macros from the GUI.)

---

## The camera design (`camera_casing.py` + `full_assembly.py`)

### Why the PCB moved inside

Earlier revisions kept the PCB on a separate flat `Base`, cabled to a small external
camera head, specifically so heatsink work on the LuckFox Pico Mini never had to touch
the pan/tilt mechanics. On request, the PCB now lives inside `CameraBody` instead -- one
integrated unit, no external FPC run. Heatsink/PCB access is still separable: remove only
`BackCover` (a few M3 self-tap screws), the rest of the rig stays untouched.

### Hardware: M5 wing bolt (pan + left tilt), M4 set-screw (right tilt only)

M5 bumped up from M4 (used in the small SC3336-only version) now that the body is much
bigger/heavier -- it holds the full PCB, not just a 20x20mm sensor board. Only the right
tilt pivot uses an M4 self-tap set-screw instead of a wing bolt, since that's the only
bore that has to stay open end-to-end for the cable (see "Cable path" below) -- the pan
pivot is a plain M5 bolt like the left tilt one. Confirmed real, commonly stocked
(searched on Tokopedia, not guessed): "WING NUT M4 M5 M6 M8 M10 ... MUR KUPING MUR KUPU
KUPU" lists M4/M5 together.

### Assembly stack

**ComponentBox is now a round, ROTATING turret** (on request: "rubah kotak diatas kamera
... menjadi tabung bundar supaya dapat berputar"), replacing the old MountPlate<->PanPlate
pivot pair. Before implementing, the ambiguity in "supaya dapat berputar" (just reshape it
into a cylinder while keeping it fixed, vs. make ComponentBox itself the rotating part) was
checked directly with the user -- confirmed: ComponentBox itself rotates. This merges what
used to be three parts (a fixed square ComponentBox holding electronics + a fixed
MountPlate lid + a rotating PanPlate holding the arms) into two:

1. **CeilingMount** -- NEW, FIXED, sits at the bottom of the stack (wherever this gets
   mounted -- wall, pole, an off-the-shelf adjustable CCTV bracket, confirmed real listings
   exist, e.g. "Adjustable Bracket Tiang Kamera CCTV" on Tokopedia). Takes over MountPlate's
   old role but simpler: a plain M5 pan-pivot hole + 4 corner mounting holes, nothing else
   -- **no cable hole anymore** (the electronics moved onto the rotating ComponentBox
   itself, see "Cable path" below).
2. **ComponentBox** -- now a round, CLOSED cylindrical turret (`TURRET_D` diameter,
   `TURRET_H` tall) that ROTATES on top of CeilingMount via a plain M5 wing bolt + wing nut
   through both their centers (pan = left/right) -- same friction-lock hardware as every
   other pivot here. Meant to eventually hold a buck converter + W5500 Ethernet module (no
   standoffs/mounting holes for those two designed yet -- explicitly out of scope for now,
   see "What's NOT done yet"). The two side arms are now fused DIRECTLY to its own top
   face, **identical in thickness and width** (`ARM_T`/`ARM_W`, on request -- see
   "Symmetric arms" below) -- left has a plain M5 hole; right carries the **stationary
   spigot** (not CameraBody, see "Tilt hinge" below) + a hidden downward cable channel.
   ComponentBox's own pivot hole is on its BOTTOM face (mates with CeilingMount below);
   the arms are on the TOP face -- deliberately opposite faces so the two can't collide
   (checked, not assumed -- see "Cable path" below for the verification).
3. **CameraBody** -- the camera shell, a **square-cross-section tube** (`CASING_W` ==
   `CASING_H`, see "CameraBody dimensions" below). PCB standoffs (bought M3 hex spacers,
   fused in-place) behind an SC3336 mounting zone up front behind the lens; both fully
   enclosed, no external FPC needed since that ribbon run stays entirely inside this one
   cavity. Left side: solid pivot disc (M5 bolt). Right side: same-diameter disc with a
   bushing hole that the arm's spigot inserts into -- CameraBody is what rotates here
   (**tilt**, a separate axis from ComponentBox's own **pan** rotation). Open back.
4. **BackCover** -- separate part, plugs CameraBody's open back (skirt inserts into the
   cavity, 4 corner M3 self-tap screws through the cap). Remove only this for PCB access.

### Cable path: fully enclosed, one wall-hop into ComponentBox's own interior

The cable is for a **W5500 Ethernet module + a buck converter** that will eventually live
INSIDE **ComponentBox** itself (see "Assembly stack" above -- the electronics box and the
arm-holder are now the same rotating part). On request, it must never be open/exposed to
outside air anywhere along its run, and it must never have to exit any side face to reach
the box externally -- the pan pivot stays a plain solid bolt (it does not carry the cable),
so instead of crossing the pan joint coaxially, the cable stays entirely inside the right
arm and ComponentBox's own top wall:

1. Starts inside CameraBody (~3mm from the PCB's edge), through the **stationary spigot's**
   bore (see "Tilt hinge" below for why it's on the arm, not CameraBody).
2. One continuous bore carries it through the spigot AND partway into the arm's own body --
   just far enough to reach the down-channel (item 3), NOT all the way out to the arm's own
   outer face (see "Real bug caught" below).
3. Turns straight down through a hidden vertical channel (`DOWN_CHANNEL_D`, 10mm) inside
   the arm, continuing straight through ComponentBox's own top wall (`WALL_T`, 3mm) --
   **one wall-hop now, not two** (an earlier revision, before ComponentBox became the
   rotating turret, had this cross the arm's own plate AND a separate matching hole
   through a fixed MountPlate below it; now that the arms are fused directly onto
   ComponentBox's own body, there's no second plate to hop through anymore).
4. Arrives directly inside **ComponentBox**'s hollow interior -- the actual electronics
   destination, not a separate box one layer further down.

**CeilingMount has no cable hole at all** -- unlike the intermediate revision described
above (where a fixed MountPlate needed a hole reversing an earlier "no hole" rule), the
electronics moved onto the rotating ComponentBox itself, so there's nothing left for a
cable to reach past CeilingMount. It's back to a plain plate with just the pivot + 4
mounting holes.

**Real limitation, stated plainly, and already accepted**: this channel is off-center (at
the arm's own position, not the pan axis), so it only stays sensibly positioned relative to
ComponentBox's interior across a **limited pan range** -- rotating ComponentBox very far
swings the channel's exit point away from wherever the modules eventually get mounted
inside it. This is a deliberate tradeoff for keeping the pan pivot solid (not hollow), and
it does NOT apply to the tilt side -- see "Tilt hinge" below for why that one has no such
limitation.

**Checked, not assumed**: a probe run down through the arm's channel and ComponentBox's own
top wall confirmed the path is genuinely open at every height sampled (`pivot_z`,
`TURRET_H`, `TURRET_H - WALL_T`, and just past it into the hollow interior), and a separate
point deep inside ComponentBox's own interior confirmed it's genuinely hollow (not
accidentally solid). ComponentBox's pivot hole and CeilingMount's pivot hole were also
confirmed to land on the exact same X/Y (needed for the bolt to actually pass through
both) -- and the whole turret (body + both arms + spigot) was confirmed to be ONE connected
solid (`Solids` count == 1), not a floating, disconnected arm that only LOOKED fused on
screen.

**Went through several attempts before landing here** (each corrected after being told
what was actually meant, not guessed again):
1. An off-axis extra hole next to the tilt's M5 bolt, reusing that hardware unmodified --
   rejected, the cable needs to go through the *inside* of the hinge, not next to it.
2. Fixed the tilt hinge to be truly coaxial, but left the pan pivot a solid M5 bolt --
   still blocked one joint further down. Made the pan pivot hollow too.
3. Made the pan shaft's bore continue down through MountPlate and exit via a hole in its
   back edge, assuming the cable needed to reach some external point beyond MountPlate --
   wrong assumption (the destination modules sit ON MountPlate's deck, not beyond it).
4. The hollow pan shaft itself turned out to be unwanted, not just its exit hole -- the
   cable only needed to travel through the arm, not through the pan pivot at all. Reverted
   the pan pivot to a plain solid bolt and moved the path into a hidden channel inside
   PanPlate's own body instead.
5. That channel (10mm) was cut through an arm only 6mm thick -- it broke straight through
   the arm's front and back faces, a visible stray hole. Widened the right arm to 14mm
   specifically so the channel stays fully enclosed with wall margin on both faces -- and
   separately, moved the hollow tube from CameraBody to the arm (also this round), since
   the tube being on the ROTATING part is what limited the earlier tilt design to a partial
   angle range in the first place.
6. That tube's own receiving boss on CameraBody had to grow (~22mm) just to contain its
   bushing hole, while the left boss stayed 16mm -- functionally fine, but the size
   mismatch looked like an odd separate "big tube" bolted onto only one side. Fixed by
   unifying both discs to one `HINGE_DISC_OD` and decoupling the spigot's length from the
   cable bore's, so the spigot could shrink back down to a short alignment pin instead of a
   long tube.
7. Once `ComponentBox` was added below MountPlate as the actual electronics enclosure, the
   cable path still stopped at MountPlate's top deck -- which would have meant routing it
   externally along the outside of the box to actually reach the modules inside, exactly
   the "kabel keluar samping" the design was supposed to avoid. Fixed (the current design,
   above) by extending the same channel through a matching hole in MountPlate, reversing
   the earlier "no hole in MountPlate" rule now that the real destination moved below it.
8. **Real bug caught** ("kenapa di lengan yang ada jalur kabel ada lobang besar di bagian
   luar lengan"): the horizontal bore connecting the spigot's bore to the down-channel used
   to start 1mm PAST the arm's own outer (far, away-from-CameraBody) face and cut inward
   through the whole `ARM_T` thickness -- which meant the entire arm got drilled straight
   through to its exposed outer side, an open hole with no purpose (the bore only actually
   needs to reach `channel_x`, in the middle of the arm, to connect with the down-channel;
   it never needed to reach the outer face at all -- there's no drilling-access reason to,
   since this is 3D printed as one piece). Fixed by starting the cut at `channel_x + 1mm`
   instead, a blind bore that stops inside the arm. Checked, not assumed: probed the arm's
   own outer face at the pivot's Y/Z after the fix -- now solid (`isInside()` == True) right
   up to the true outer face, and a separate probe confirmed the horizontal bore still
   connects cleanly to the down-channel (both share the same Y center, so reaching
   `channel_x` is enough -- no isthmus of material left between them) and the full path
   from inside CameraBody down into ComponentBox is still completely open.
9. **Topology change**, on request ("rubah kotak diatas kamera ... menjadi tabung bundar
   supaya dapat berputar"): ComponentBox reshaped from a fixed square box into a round,
   ROTATING turret, absorbing PanPlate's old arm-holding role. This was explicitly
   clarified before building -- two readings were possible ("just make it round, keep it
   fixed" vs. "make ComponentBox itself the rotating part"), the user confirmed the
   latter. The old MountPlate<->PanPlate pivot pair is gone; CeilingMount (new, fixed,
   simpler than the old MountPlate since it carries no cable hole anymore) now pivots
   directly against the rotating ComponentBox. This also shortened the cable path from two
   plate-hops (arm+PanPlate, then a separate MountPlate hole) down to one (arm, then
   straight through ComponentBox's own top wall) -- see the walkthrough above.

### Tilt hinge (left/right, not a bottom tab) -- DJI Osmo Pocket-style matching discs

**Current design**: the two tilt pivots are mechanically different, and which side holds
the spigot matters -- but both now show the SAME `HINGE_DISC_OD` (24mm) disc on
CameraBody, styled after DJI Osmo Pocket's gimbal (flush matching pivot housings, not a
small boss on one side and a noticeably bigger one on the other).
- **Left** (`HINGE_DISC_OD`, solid): a normal M5 wing bolt + wing nut through CameraBody's
  disc and ComponentBox's arm -- this is the structural/load-bearing side.
- **Right** (`HINGE_DISC_OD` disc on CameraBody / `SPIGOT_OD` spigot on the arm): the arm
  (fixed to ComponentBox, doesn't tilt -- only CameraBody does) has a SHORT spigot --
  stationary relative to tilt, printed as one piece with ComponentBox -- that crosses
  `PIVOT_GAP` and engages
  `SPIGOT_LEN` into CameraBody's disc, just enough for real rotational support (it does
  NOT reach all the way to the wall/interior -- that's the cable bore's job, cut
  separately and independently, see "Cable path" above). CameraBody's disc has a bushing
  hole (not a bolt hole -- it has to stay open for the cable) that receives the spigot and
  rotates around it, so there's no wing nut on this side. A radial M4 self-tap set-screw,
  drilled through **CameraBody's disc** (the ROTATING part now), presses inward on the
  stationary spigot for friction-lock (loosen to retilt, tighten to hold).

Putting the spigot on the STATIONARY arm (not CameraBody) is what lets the down-channel
below stay connected at ANY tilt angle -- an earlier revision had it on CameraBody (the
ROTATING side) instead, which only stayed aligned across a limited angle, since a hole on
a rotating part sweeps around as it turns.

No custom hollow bolts, no bearings -- the spigot is just a short printed shaft, part of
ComponentBox's arm itself, and everything else is the same M4/M5 hardware used throughout.

**Two real things caught and fixed here, not just design choices**:
1. CameraBody's right boss initially reused a smaller diameter (16mm, matching the left
   boss) -- but the bushing hole through it needs to fit the shaft (~16.4mm with
   clearance), which is *bigger* than a 16mm boss. Cutting a 16.4mm hole through a
   16mm-diameter boss removes the entire boss -- checked, not assumed: CameraBody's
   measured width matched exactly what you'd get with the right boss totally absent (a
   flush wall, no protrusion at all). First fixed by growing just the right boss (~22mm) --
   which then became its own complaint ("why is there a big tube on just one side") --
   resolved properly by unifying BOTH sides to the same `HINGE_DISC_OD` (24mm), on request
   ("skema DJI Osmo Pocket").
2. The body-to-hinge reach kept creeping up across these fixes (10mm boss -> 22mm boss ->
   a long separate tube). Reset by decoupling the spigot's length (short, `SPIGOT_LEN`,
   just for mechanical engagement) from the cable bore's length (longer, cut
   independently, reaches wherever the cable actually needs to go) -- the spigot no longer
   has to be as long as the whole cable path, so it doesn't need to look like a stalk.

**Retention caveat, stated plainly**: the spigot is *not* positively retained against
CameraBody sliding back off it -- only friction (the set-screw, and the left bolt holding
the body's attitude fixed) keeps it seated. A flanged/captured version was considered and
dropped: the flange would need to be bigger than CameraBody's hole to retain it, which
makes it physically impossible to assemble (can't push a bigger flange through a smaller
hole) since the spigot+arm print as one piece. Fine for a first build; a dab of glue or a
zip-tie at that joint is a reasonable belt-and-suspenders addition if wanted.

**Both pivots must be coaxial** (same Y/Z axis) for the body to tilt cleanly without
binding -- this constrains the spigot's height to `TILT_LOCAL_Z`, the same as the left
pivot, which sits close to the PCB's own height. Checked, not assumed: CameraBody's actual
bushing hole (scoped to just the wall + disc length, not a full-width sweep) has exactly
**0mm³ overlap** with the PCB -- the PCB's own solid extent stops about 3mm short of the
wall, so the cable crosses that small open-air gap to reach the board's edge, then routes
by hand within the `COMPONENT_CLEARANCE` headroom to reach the connector (not itself
routed through any additionally-modeled channel -- a manual assembly detail).

**Verified via real geometry queries (not assumed)**, printed by `camera_casing.py` and
`full_assembly.py` themselves, plus ad-hoc probes during this revision:
- CeilingMount/ComponentBox, ComponentBox/CameraBody, CameraBody/BackCover: exactly 0mm³
  solid overlap (no collision).
- **Both of CameraBody's discs (left and right) measured at the exact same radius
  (12.0mm = `HINGE_DISC_OD`/2)** -- confirmed by reading circle centers straight out of
  the geometry, not just trusting that the formula was applied on both sides.
- Left M5 hole (both parts), and the spigot/bushing pair (arm's spigot OD, CameraBody's
  bushing hole), all share the exact same Y/Z axis line.
- The set-screw pilot (on CameraBody now) is confirmed to actually reach the spigot's
  outer surface -- probed at its expected end point, 0mm³ (open, as a drilled hole should
  be).
- CeilingMount is confirmed solid everywhere except its 4 corner mounting holes and central
  M5 pivot hole -- no cable hole at all anymore (the electronics moved onto ComponentBox,
  see "Cable path" above).
- ComponentBox's own pivot hole (bottom face) and CeilingMount's pivot hole are confirmed
  to land on the exact same X/Y (needed for the bolt to actually pass through both, not
  just look aligned from above).
- The whole ComponentBox turret (cylinder body + both arms + the spigot) is confirmed to be
  **ONE connected solid** (`Solids` count == 1) -- not a disconnected, floating arm that
  only looked fused in a still image.
- The arm's hidden down-channel, and its continuation straight through ComponentBox's own
  top wall into its hollow interior, are confirmed genuinely open the whole way -- probed
  at `pivot_z`, `TURRET_H`, `TURRET_H - WALL_T`, and just past it: all open, and a separate
  point deep inside the turret confirmed genuinely hollow (not accidentally solid). The
  channel is also still fully enclosed within `ARM_T` (shared by both arms, see "Symmetric
  arms" above), with a solid 2mm margin probed on both the arm's front and back faces (the
  "hole not visible" fix, still holding after this revision).
- **Bushing hole / PCB overlap: 0mm³**, and still exactly 3mm of open-air gap from the
  bore's inner reach to the PCB's edge -- unchanged after shortening the spigot, since the
  cable bore's own length is computed independently of the spigot's shorter one.
- BackCover's skirt actually nests inside CameraBody's open cavity (Y-ranges overlap,
  confirmed by bounding box) rather than just butting up against the opening -- an earlier
  version had the skirt pointing the wrong way (out, not in), also caught by this check.
- **BackCover/CameraBody overlap: 0mm³** (was ~3mm³, a sliver at the fillet corners, in an
  earlier revision -- fixed by giving `CASING_DEPTH` its own explicit term for
  `COVER_SKIRT_DEPTH` + `COVER_BACK_CLEARANCE` instead of reusing `MARGIN` alone, which
  used to be thinner (5mm) than the skirt itself (6mm) and let it clip into the PCB's back
  edge -- the original bug report that started this round of fixes).
- The real PCB (STEP import) bounding box is **fully contained inside** CameraBody's
  bounding box, and PCB/CameraBody solid overlap is exactly 0mm³.

### Body-to-hinge distance: tightened twice

**First pass** ("jarak body ke engsel terlalu jauh"): the old `SIDE_BOSS_LEN` 10mm -> 6mm
and `PIVOT_GAP` 1mm -> 0.5mm, shrinking the standoff from 11mm to 6.5mm. `PLATE_SIZE` was
reduced to match (95mm -> 88mm).

**Second pass**, as part of the Osmo Pocket disc-unification above: decoupling the
spigot's length from the cable bore's length meant the spigot only needs `SPIGOT_LEN`
(4mm) of real engagement, not a long reach all the way to the wall -- CameraBody's own
width shrank further as a direct result (69mm total for both discs, down from 73mm with
the old 6mm-boss-each-side version, itself down from the original 81mm).

Re-verified after each change, not assumed still valid: all the same checks above still
pass (0mm³ overlaps throughout, coaxial pivots, PCB clearance still exactly 3mm, the
hidden channel still has solid material on both of the arm's faces) -- shortening the
reach didn't quietly reopen any of the earlier bugs.

`HINGE_DISC_LEN`/`PIVOT_GAP`/`SPIGOT_LEN` weren't shrunk to zero: some length is still
needed for the disc to actually behave like a bearing surface (not just a thin wafer), for
an M5 wing nut to have room to be tightened by hand without hitting the wall, and for the
spigot to provide real rotational support rather than wobble. Current values are
tightened-but-functional, not proof of the true minimum -- there's likely still a bit more
room to shrink if that's ever wanted, just untested past this point.

**Note**: the plate/footprint size grew back up in a later pass ("Symmetric arms" below,
both arms widened to match), and then the whole footprint concept changed again when
ComponentBox became a round turret (`TURRET_D`) -- neither is a regression of this
tightening pass, just separate later changes layered on top.

### Symmetric arms

On request ("buat kedua lengan sama dimensinya dan tidak keluar area kotak"), both side
arms share the exact same `ARM_T` (thickness, X direction) and `ARM_W` (width, Y direction)
-- previously the left arm stayed slim (6mm) since it never needed the down-channel's
enclosure margin, while only the right arm was widened to 14mm for that reason (see "Cable
path" above). Unifying both to the wider value is what was asked for; nothing shrank below
what the channel actually needs.

This footprint constraint applied to the OLD square `ComponentBox`/`PanPlate` design (a
fixed `PLATE_SIZE`, derived so both arms stayed fully inside a square plate). Now that
`ComponentBox` is a round rotating turret (see "Assembly stack" above), that specific
"stay inside a square" requirement no longer applies -- `TURRET_D` (110mm) just needs to be
big enough that the arms genuinely overlap/fuse onto the turret's own top face, not that
they stay fully inside its circular silhouette (checked directly: the whole turret + both
arms + the spigot measured as ONE connected solid, `Solids` count == 1 -- not a
disconnected floating arm that only looked attached on screen).

### CameraBody dimensions

`CASING_W` is driven by the real, CONFIRMED PCB size (not guessed): `PCB_W` + 2×`MARGIN` +
2×`WALL_T` ≈ 61mm -- a real physical constraint, not a styling choice; a body enclosing a
45x63mm PCB cannot be a small compact camera, whatever the styling. `CASING_DEPTH` =
`WALL_T` + `CAM_MODULE_DEPTH` + `PCB_H` + `MARGIN` ≈ 86mm.

`CASING_H` is now set equal to `CASING_W` (≈61mm), on request -- CameraBody reads as a
**square-cross-section tube** ("tabung persegi"), not the flatter ~41mm-tall rectangular
box earlier revisions used. Since `CASING_W` can't shrink (real PCB constraint above),
`CASING_H` had to grow to match it rather than the other way around. The PCB/component
stack itself only actually needs `_CASING_H_MIN` = `STANDOFF_H` + `PCB_T` +
`COMPONENT_CLEARANCE` + 2×`WALL_T` ≈ 41mm -- `camera_casing.py` asserts `CASING_H >=
_CASING_H_MIN` at import time so this can never quietly regress into a too-short body; the
extra ~20mm of height versus the old design is genuinely spare interior, not needed for
fit. Rounded/filleted vertical edges (`FILLET_R`) and a recessed circular bezel ring around
the lens are the "futuristic minimalist" styling cues, same as the earlier SC3336-only
design.

**Assumed** (search `camera_casing.py` for "ASSUMED"): `COMPONENT_CLEARANCE` (18mm --
tallest stack above the PCB, e.g. ESP32 Dev Board Breakout on pin headers, not measured
against the real populated board); `CAM_MODULE_DEPTH` (15mm -- front cavity for the
SC3336 board + lens holder). SC3336/lens dimensions (`CAM_BOARD_W/H`, `CAM_MOUNT_HOLE_D`,
`CAM_MOUNT_SPACING`, `LENS_HOLE_D`) and PCB dimensions (CONFIRMED, from the real
`.kicad_pcb`) both come from `build_housing.py` -- one place per number, not duplicated.

### Styling pass: rounded edges everywhere a mating surface doesn't need to stay flat

On request ("buat desain supaya lebih menarik untuk dilihat"), extended the rounding
beyond just the 4 vertical corners (`fillet_vertical_edges()`, used throughout since the
first revision) to more edges on most parts:

- `fillet_vertical_and_cap_edges(shape, radius, cap_axis, cap_value)` -- rounds the 4
  vertical edges PLUS the 2 horizontal edges of ONE chosen face, leaving the opposite face
  sharp. **CameraBody**: front cap (`cap_axis="y", cap_value=0`, the lens face) is rounded
  into a "capsule" profile, blending into the same rounded vertical corners used all along
  its depth. The BACK stays sharp on purpose -- BackCover's flat skirt needs a flat
  rectangular opening to nest into (see "Assembly stack"); rounding the back too would need
  BackCover's own skirt profile to match, which isn't done here.
- Both arm posts (`fillet_vertical_edges()`, applied to each arm's own box before the
  spigot/holes are cut in) have rounded vertical corners too, matching the hinge discs'
  rounded look instead of being plain sharp-edged rectangular blocks.

**Two real OCC fillet failures caught here, both by checking the actual result instead of
trusting that the fillet call succeeded:**
1. Tried rounding ALL 12 edges of MountPlate/PanPlate's own flat plates at once (vertical +
   top perimeter + bottom perimeter). OCC's fillet needs a full 3-way corner blend at all 8
   box vertices when all 12 edges are selected together, and it threw
   `Part.OCCError: BRep_API: command not done` on that plate's proportions (thin relative
   to its footprint). Reverted to `fillet_vertical_edges()` (the proven approach) rather
   than force a fragile operation. (Those two parts don't exist anymore after the
   ComponentBox topology change below, but the lesson -- full-loop/multi-edge box fillets
   are fragile -- carried forward.)
2. Tried rounding ComponentBox's round top rim (a single, full 360-degree circular edge)
   when it became a cylinder. This one didn't error out -- it silently produced a WRONG
   result: instead of rounding the rim inward like a normal edge fillet, OCC ballooned the
   whole cylinder's radius outward. Caught by checking bbox before/after: a plain
   unfilleted `TURRET_D`=110mm cylinder measured X 0..110 as expected, but after the fillet
   call the SAME cylinder measured X -4.53..114.53 -- a real ~4.5mm radius INCREASE, not a
   rounded corner. Left the turret's rims sharp/unfilleted rather than ship a shape quietly
   bigger than its own stated diameter.

**Checked, not assumed**: re-ran the full build from scratch after both fixes --
succeeded cleanly with no errors, and `full_assembly.py`'s full overlap/PCB-containment
suite still passed unchanged (all 0mm³, PCB still fully inside CameraBody, 3mm clearance
gap unchanged). Also directly probed CameraBody's own front-top-left corner with
`isInside()` along a 45-degree sweep from the fillet arc's own center: solid out to ~2.6mm,
empty from 3.0mm onward -- confirming a genuinely rounded ~2.5mm (`FILLET_R`) arc is really
there, not just a fillet call that silently no-op'd. (Offscreen FreeCAD renders still only
show a flat top-down view regardless of camera angle -- see "Regenerating everything" above
-- so this numeric probe stood in for eyeballing a render.)

### ComponentBox: round rotating turret, placeholder enclosure for the buck converter + W5500 module

`ComponentBox` (`build_component_box_with_arms()`) is a round, closed cylinder --
`TURRET_D` (110mm) diameter, `TURRET_H` (25mm) tall -- that ROTATES on top of the new fixed
`CeilingMount` (see "Assembly stack" above for the full topology change). It's deliberately
minimal inside: hollow, closed top + bottom + side walls (own `WALL_T` walls, same as
CameraBody's shell), no standoffs or mounting holes for the buck converter/W5500 module
modeled yet -- on request ("tidak perlu dibuat dudukan untuk sekarang"), it's just an empty
enclosure for those. The cable itself, however, already reaches all the way inside (see
"Cable path" above).

`TURRET_D` (110mm) is a placeholder, but sized off REAL searched component dimensions
rather than guessed outright: a common LM2596 buck converter module measures 43.2 x 21 x
14mm, and a W5500 Ethernet module with an RJ45 jack measures roughly 55 x 28 x 15mm. Both
fit comfortably within a 110mm circle side by side, and `TURRET_H`'s 25mm clears the taller
module (15mm) with real room left for wiring -- but exact placement, orientation, and
mounting for either module still isn't designed (see "What's NOT done yet"). Unlike the old
square box, `TURRET_D` no longer has to satisfy an "arms must stay inside the footprint"
formula (see "Symmetric arms" above) -- it just needs to be big enough that the arms
genuinely fuse onto the turret's own top face, which is checked directly (turret + both
arms + spigot come out as ONE connected solid), not derived from a containment formula.

### What's NOT done yet

- **The buck converter + W5500 module themselves aren't designed** -- explicitly out of
  scope for now (on request). `ComponentBox` exists as an empty, round enclosure (see
  above) sized off real module dimensions, but has no standoffs or mounting holes yet. The
  cable path DOES now reach inside it (see "Cable path" above) -- what's missing is only
  where/how the two modules themselves physically mount once their real
  dimensions/orientation are decided.
- No weatherproofing anywhere along the cable path (the right tilt bushing joint, the
  hidden channel's crossing into ComponentBox's own top wall) or at BackCover's skirt fit
  -- worth real attention before outdoor use, since this is now also the water ingress
  path, not just a mechanical one. The new CeilingMount<->ComponentBox pan pivot is also
  unsealed.
- `CEILING_MOUNT_HOLE_D`/pattern on CeilingMount is generic -- match it to whatever
  pole/wall bracket actually gets bought.
- The right tilt shaft isn't positively retained in the arm's bushing bore -- relies on
  friction (its set-screw, plus the left M5 bolt keeping the body's attitude fixed). Fine
  for a first build; glue or a zip-tie at that joint is a reasonable addition if more
  security is wanted.
- Actual achievable tilt range isn't computed for the right (bushing) pivot -- being a
  true coaxial bushing, rotation itself isn't the limiter there; what would actually stop
  it at some angle is CameraBody's own corners swinging into ComponentBox. Pan range
  (ComponentBox on CeilingMount) is separately limited by the off-center cable channel
  losing alignment with ComponentBox's own interior (see "Cable path" above) -- neither
  has been swept/measured.
- Hasn't been checked against the LuckFox Pico Mini's actual heat output -- `CameraBody`
  is now a mostly-sealed box (BackCover screw holes and floor standoff pilot holes are the
  only openings to outside air, now that the cable path terminates inside the assembly
  instead of exiting anywhere), which may or may not be adequate passive cooling depending
  on real thermal load. Worth a real check before this goes in the field.

---

## `build_housing.py` + `assemble_pcb.py`: flat mounting plate (alternate, unused by the camera design above)

- **Base**: flat `FLOOR_T`-thick (2mm) plate, no walls, no camera geometry. 4x M3
  clearance through-holes at the real PCB mounting-hole positions. `build_base(ext_h=...)`
  takes an optional length override.
- **Standoffs**: reference/BOM part, not printed. Represents 4x off-the-shelf M3
  male-female hex spacers (confirmed real listing -- "Spacer Kuningan M3 Male Female",
  Prima Terang, Tokopedia -- stocked in 5/6/8/10/15/20/25/30mm) that hold the PCB above
  Base.

**Confirmed** (read directly from `../LuckFox-RAP-Shield-PCB/LuckFox RAP Shield.kicad_pcb`):
board outline 45.0022 x 63.2268mm, 1.6mm thick, 4x M3 mounting holes at
(4.0022,3.9) / (4.0022,59.3) / (41.0022,59.3) / (41.0022,3.9) relative to the board's
bottom-left corner.

`assemble_pcb.py` mirrors the imported STEP shape across the Y=0 plane before placing it
(KiCad's exporter converts screen-Y-down to world-Y-up) -- confirmed, not guessed, by
reading the 4 real M3 hole circle centers straight out of the STEP geometry: they land at
`(117,-78.9)` etc., exactly the KiCad absolute X/Y with Y negated. Mirroring back across
Y=0 recovers the exact raw KiCad coordinates that `MOUNT_HOLES` are defined against. The
same mirror/translate logic is reused in `full_assembly.py` for placing the PCB inside
CameraBody.

### History

This file used to build the camera mount too (first a full weatherproof enclosure with a
Lid + hinge, then a fixed `CameraPlate` behind a `Hood` recess, then nothing once
`camera_casing.py`'s external pan/tilt head took over). Now the PCB itself has also moved
into `camera_casing.py`'s `CameraBody`. See git log for any earlier version.
