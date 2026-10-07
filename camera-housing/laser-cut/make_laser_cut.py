#!/usr/bin/env python3
"""Laser-cut version of the VIPARK camera: flat patterns (DXF) for every part.

Run:  python3 make_laser_cut.py        (needs: ezdxf, shapely, matplotlib)
Out:  out/dxf/*.dxf          one file per part (send these to the laser shop)
      out/sheets/*.dxf       the same parts nested on one sheet per material
      out/png/*.png          previews of every flat pattern
      out/assembly.png       3D sanity view of the assembled camera + ceiling box
      out/parts_table.md     parts, material, mass, automatic checks

Design (all numbers below are parameters -- edit and re-run):

  CEILING BOX (aluminium 2 mm)  -- 5-sided bent tray + flat lid with mounting ears.
      The +Y wall has an OPENING for a carrier plate (RJ45 port, boards on standoffs --
      the plate itself is NOT designed yet; its bolt pattern is fixed by PLATE_* below).
  ARMS (steel 3 mm)             -- two L brackets (1 bend each) bolted under the box.
  CAMERA BODY
      side plates (steel 3 mm)  -- the two SIDES of the body; they carry the pivots.
      "wadah" (aluminium 2 mm)  -- C-channel: front + top + bottom walls, rear return
                                   flanges, and short side tabs that the steel plates
                                   bolt to. Open at both sides (closed by the plates) and
                                   at the back.
      "tutup" (aluminium 2 mm)  -- flat lid, 4 screws into rivet nuts in the rear flanges.
  PIVOTS  right = hollow M10x1 stud (cable passes through its bore) + lock nuts
          left  = ordinary M6 bolt + nyloc, plus an arc slot / M5 wing-nut tilt lock

CONVENTIONS
  * mm. DXF layers: CUT (cut through), BEND (fold here, centre of bend zone, do NOT cut),
    LABEL (text, ignore).
  * Every flat pattern is drawn looking at the OUTSIDE face; all bends fold AWAY from you.
  * Bend model: outside setback a = r + t, bend allowance BA = (r + K t) * pi/2.
    Aluminium 5052-H32: r = t = 2, K = 0.40.  Steel: r = t = 3, K = 0.40.
    Your fabricator's own bend table wins: give them the OUTSIDE dimensions.
"""
import math
import os

import ezdxf
from ezdxf.math import bulge_to_arc
from shapely import affinity
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

# =====================================================================================
# MATERIAL / BENDING
# =====================================================================================
T_AL, R_AL, K_FACTOR = 2.0, 2.0, 0.40
A_AL = R_AL + T_AL
BA_AL = (R_AL + K_FACTOR * T_AL) * math.pi / 2
T_ST, R_ST = 3.0, 3.0
A_ST = R_ST + T_ST
BA_ST = (R_ST + K_FACTOR * T_ST) * math.pi / 2
CORNER_GAP = 0.4           # seam between neighbouring walls at tray corners
MIN_HOLE_TO_BEND = 1.5     # x thickness, hole edge to bend zone (checked by assert)
DENSITY = {"Aluminium 5052-H32": 2.68, "Baja lunak (mild steel)": 7.85, "Akrilik": 1.19}

# =====================================================================================
# PCB / ELECTRONICS (CONFIRMED from LuckFox RAP Shield.kicad_pcb, see ../README.md)
# =====================================================================================
PCB_W, PCB_H, PCB_T = 45.0022, 63.2268, 1.6
PCB_HOLES = [(4.0022, 3.9), (4.0022, 59.3), (41.0022, 59.3), (41.0022, 3.9)]
ESP_X0, ESP_Y0 = 121.53 - 112.9978, 81.98 - 75.0      # ESP32 DevKitC footprint origin, rel. PCB
ESP_W, ESP_L = 27.94, 55.04
M3_CLEAR, M2_CLEAR, M4_CLEAR = 3.2, 2.2, 4.5
M3_RIVNUT, M4_RIVNUT = 5.0, 6.0                        # drill sizes for rivet nuts (check your nut)

# ---- SC3336 camera board (Luckfox / Waveshare "SC3336 3MP Camera (B)") ----------------
# Public sources only give: board 25 x 24 mm, 18 mm deep incl. lens. The photo shows THREE
# mounting holes in corners and a lens that is NOT centred on the board; the lens barrel's
# front ring is roughly 17 mm across. Hole positions are NOT published: measure your board
# and fill CAM_HOLES = [(dx, dz), ...] = hole centres in mm relative to the LENS AXIS, seen
# from the FRONT (dx to the right, dz up). Empty list = no mounting holes cut (drill after
# test fit). LENS_HOLE_D must clear the widest part of the barrel that passes the plate.
CAM_BOARD_W, CAM_BOARD_H = 25.0, 24.0
LENS_HOLE_D = 18.5               # ESTIMATE from the photo (barrel ring ~17 mm) -- verify
CAM_HOLES = []                   # <-- fill in after measuring, e.g. [(-8.5, 7.5), (9.0, -9.5), (9.0, 8.0)]
CAM_HOLE_D = M2_CLEAR
CAM_DEPTH = 15.0                 # front cavity depth for board + FFC (module is 18 mm deep incl. lens)

STANDOFF_H = 15.0                # M3 hex spacer under the PCB (LuckFox hangs in this gap)
COMPONENT_CLEARANCE = 22.0       # tallest part above PCB (ESP32 on headers + 5 mm heatsink)

# =====================================================================================
# CAMERA BODY (aluminium channel + lid, steel side plates)
# =====================================================================================
BODY_W = 62.0                   # X between the steel plates (= channel outside width)
BODY_OUT_W = BODY_W + 2 * 3.0   # incl. the two 3 mm steel plates
BODY_H = 44.0                   # Z, outside
BODY_D = 94.0                   # Y, outside (front face to rear edge)
MARGIN_L = 7.0                  # PCB to LEFT plate  (room for M6 bolt head + M5 clamp head)
FLANGE_F = 16.0                 # rear return flange, outside height (holds lid rivet nuts)
LID_HOLE_DX, LID_HOLE_E = 20.0, 10.0   # lid screws: +-20 mm from centre, 10 mm from top/bottom
SIDE_TAB_H = 16.0               # side tabs the steel plates bolt to (outside height)
TAB_SEGS = [(6.0, 34.0), (60.0, 88.0)]  # depth ranges of the tabs (gap in the middle = pivot nuts)
SIDE_PLATE_T = T_ST
PLATE_CORNER_R = 5.0

PIVOT_D = BODY_D / 2.0          # pivot position along the depth (centre)
PIVOT_Z = BODY_H / 2.0
LEFT_BOLT_HOLE = 6.5            # M6 clearance
RIGHT_BOSS_HOLE = 10.5          # M10x1 hollow stud clearance (use 16.2 for a PG9/M16 gland)
CLAMP_R = 12.0                  # tilt-lock bolt radius from the pivot (slot must stay inside the arm's R18 end)
CLAMP_HOLE = 5.3                # M5 clearance
CLAMP_ARC_DEG = 45.0            # tilt-lock slot spans +-45 deg
# plate-to-tab screws (d along depth, z from the bottom outer face); z=10 -> bottom tab, z=H-10 -> top tab
SIDE_SCREW_POS = [(12.0, 10.0), (82.0, 10.0), (12.0, BODY_H - 10.0), (82.0, BODY_H - 10.0)]

# =====================================================================================
# ARMS (steel L brackets) AND CEILING BOX
# =====================================================================================
ARM_W = 36.0                    # arm strip width (Y)
ARM_FOOT_LEN = 24.0             # outside length of the foot (from the leg's outer face)
ARM_FOOT_HOLE = 17.0            # hole centre, measured from the leg's outer face
ARM_FOOT_HOLE_Y = 10.0          # holes at y = +-10
AXIS_BELOW_BOX = 60.0           # tilt axis below the box bottom (body diagonal 52 + clearance)
ARM_INNER_GAP = BODY_OUT_W + 2 * 1.0     # 1 mm nylon washers each side
ARM_X_INNER = ARM_INNER_GAP / 2.0        # arm inner face at x = +-35

BOX_X, BOX_Y, BOX_Z = 124.0, 54.0, 50.0
BOX_FLANGE_F, BOX_LID_E = 14.0, 9.5
LID_EAR = 15.0                  # ceiling lid extends this much beyond the box each side (X)
ANCHOR_D = 6.5                  # ceiling anchor holes (M6)
OPENING_W, OPENING_H = 96.0, 30.0       # side opening in the +Y wall (boards pass through it)
# interface for the FUTURE carrier plate (not drawn): plate size and its 4 screws
PLATE_W, PLATE_H = 116.0, 40.0
PLATE_SCREWS = [(-53.0, -9.0), (53.0, -9.0), (-53.0, 9.0), (53.0, 9.0)]
GROMMET_D = 10.0
GROMMET_X, GROMMET_Y = 48.0, 0.0     # cable enters here (S-curve from where it leaves the pivot)

# =====================================================================================
# 2D GEOMETRY HELPERS
# =====================================================================================


def rounded_rect(x0, y0, x1, y1, r=0.0):
    if r <= 0:
        return [(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)]
    b = math.tan(math.pi / 8)
    return [(x0 + r, y0, 0), (x1 - r, y0, b), (x1, y0 + r, 0), (x1, y1 - r, b),
            (x1 - r, y1, 0), (x0 + r, y1, b), (x0, y1 - r, 0), (x0, y0 + r, b)]


def slot_path(cx, cy, length, width, angle_deg=0.0):
    """Straight slot, `length` = overall length, `width` = slot width."""
    h = max(length - width, 0.0) / 2.0
    r = width / 2.0
    pts = [(-h, -r, 0), (h, -r, 1.0), (h, r, 0), (-h, r, 1.0)]
    c, s = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    return [(cx + x * c - y * s, cy + x * s + y * c, bl) for x, y, bl in pts]


def arc_slot_path(cx, cy, radius, a0, a1, width):
    """Arc-shaped slot centred on (cx,cy), centre line radius `radius`, angles in degrees."""
    ro, ri, w = radius + width / 2.0, radius - width / 2.0, math.radians(a1 - a0)

    def pt(rr, ang):
        return cx + rr * math.cos(math.radians(ang)), cy + rr * math.sin(math.radians(ang))
    p1, p2, p3, p4 = pt(ro, a0), pt(ro, a1), pt(ri, a1), pt(ri, a0)
    bulge = math.tan(w / 4)
    return [(*p1, bulge), (*p2, 1.0), (*p3, -bulge), (*p4, 1.0)]


def path_points(path, n=24):
    """Flatten a bulge polyline to points (for bbox / shapely)."""
    out = []
    for i, (x, y, b) in enumerate(path):
        out.append((x, y))
        if b:
            x2, y2, _ = path[(i + 1) % len(path)]
            c, sa, ea, r = bulge_to_arc((x, y), (x2, y2), b)
            sa, ea = float(sa), float(ea)
            if b > 0 and ea < sa:
                ea += 2 * math.pi
            if b < 0 and ea > sa:
                ea -= 2 * math.pi
            for k in range(1, n):
                ang = sa + (ea - sa) * k / n
                out.append((c[0] + r * math.cos(ang), c[1] + r * math.sin(ang)))
    return out


class Part:
    """One flat pattern. Coordinates are free; export shifts the bbox to the origin."""

    def __init__(self, key, title, material, thickness, qty, note="", bent=False):
        self.key, self.title, self.material, self.t, self.qty = key, title, material, thickness, qty
        self.note, self.bent = note, bent
        self.outer = None          # shapely polygon (outline, flat)
        self.outer_path = None     # bulge path for a rounded outline (else derived from shapely)
        self.holes = []            # circles (x, y, d)
        self.cutouts = []          # bulge paths (slots, windows, ...)
        self.bends = []            # ((x1,y1),(x2,y2))
        self.bend_zones = []       # shapely boxes (for hole checks)
        self.facts = []            # human-readable facts for BOM

    # --- feature API -------------------------------------------------------------
    def hole(self, x, y, d):
        self._check(Point(x, y).buffer(d / 2.0), f"hole d={d} at ({x:.1f},{y:.1f})")
        self.holes.append((x, y, d))

    def cut(self, path, label=""):
        self._check(Polygon(path_points(path)), f"cutout {label}")
        self.cutouts.append(path)

    def _check(self, geom, what):
        assert self.outer is not None, "outline first"
        assert self.outer.buffer(1e-6).contains(geom), f"[{self.key}] {what} sticks out of the part"
        for z in self.bend_zones:
            d = geom.distance(z)
            assert d >= MIN_HOLE_TO_BEND * self.t - 1e-6, (
                f"[{self.key}] {what} only {d:.2f} mm from a bend (min {MIN_HOLE_TO_BEND * self.t:.1f})")

    # --- geometry ------------------------------------------------------------------
    def bbox(self):
        pts = self.outline_points()
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def outline_points(self):
        if self.outer_path:
            return path_points(self.outer_path)
        return list(self.outer.exterior.coords)[:-1]

    def size(self):
        x0, y0, x1, y1 = self.bbox()
        return x1 - x0, y1 - y0

    def area_mm2(self):
        a = self.outer.area
        a -= sum(math.pi * (d / 2) ** 2 for _, _, d in self.holes)
        a -= sum(Polygon(path_points(p)).area for p in self.cutouts)
        return a

    def mass_g(self):
        return self.area_mm2() * self.t * DENSITY[self.material] / 1000.0

    # --- export ----------------------------------------------------------------------
    def draw(self, msp, dx=0.0, dy=0.0, label=True):
        x0, y0, _, _ = self.bbox()
        ox, oy = dx - x0, dy - y0
        ep = {"layer": "CUT"}
        if self.outer_path:
            self._poly(msp, self.outer_path, ox, oy, ep)
        else:
            msp.add_lwpolyline([(x + ox, y + oy) for x, y in self.outer.exterior.coords[:-1]],
                               close=True, dxfattribs=ep)
        for p in self.cutouts:
            self._poly(msp, p, ox, oy, ep)
        for x, y, d in self.holes:
            msp.add_circle((x + ox, y + oy), d / 2.0, dxfattribs=ep)
        for (a, b) in self.bends:
            msp.add_line((a[0] + ox, a[1] + oy), (b[0] + ox, b[1] + oy),
                         dxfattribs={"layer": "BEND", "linetype": "DASHED"})
        if label:
            w, h = self.size()
            msp.add_text(f"{self.key} {self.title} | {self.material} {self.t:g} mm | x{self.qty}",
                         height=3.0, dxfattribs={"layer": "LABEL", "insert": (dx, dy + h + 3)})

    @staticmethod
    def _poly(msp, path, ox, oy, attribs):
        return msp.add_lwpolyline([(x + ox, y + oy, 0, 0, b) for x, y, b in path], format="xyseb",
                                  close=True, dxfattribs=attribs)


def new_doc():
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.layers.add("CUT", color=7)
    doc.layers.add("BEND", color=5, linetype="DASHED")
    doc.layers.add("LABEL", color=8)
    return doc


# =====================================================================================
# TRAY (bent box / channel) FLAT PATTERN
# =====================================================================================
class Tray:
    """Base plate P x Q with walls of depth D folded away from the viewer.

    +v / -v walls ("narrow", top/bottom) have a rear return flange of outside height F.
    full_walls=True : +u / -u walls run the whole height (ordinary 5-sided tray).
    full_walls=False: NO side walls; instead the narrow walls carry short side tabs
                      (outside height tab_h) in the depth ranges tab_segs -> a C-channel
                      whose open ends are closed by separate plates."""

    def __init__(self, part, P, Q, D, t, r, k, F, full_walls=True, tab_h=None, tab_segs=()):
        self.part, self.P, self.Q, self.D, self.t, self.F = part, P, Q, D, t, F
        self.a = a = r + t
        self.b = b = (r + k * t) * math.pi / 2
        g = CORNER_GAP
        Uf, Vf = P / 2 - a, Q / 2 - a
        Wn = (P / 2 - t - g) if full_walls else Uf
        neck = Uf if full_walls else P / 2
        V1 = Vf + b
        V2 = V1 + D - 2 * a
        Vend = V2 + b + (F - a)
        self.Uf, self.Vf, self.V1, self.V2, self.Vend, self.Wn = Uf, Vf, V1, V2, Vend, Wn
        mid = b / 2

        top = [box(-neck, Vf, neck, V1), box(-Wn, V1, Wn, V2), box(-Wn, V2, Wn, V2 + b),
               box(-(Wn - 0.5), V2 + b, Wn - 0.5, Vend)]
        base_half = Uf if full_walls else P / 2
        rects = [box(-base_half, -Vf, base_half, Vf)]
        rects += top + [affinity.scale(g_, 1, -1, origin=(0, 0)) for g_ in top]
        bends = [((-neck, Vf + mid), (neck, Vf + mid)), ((-neck, -(Vf + mid)), (neck, -(Vf + mid))),
                 ((-Wn, V2 + mid), (Wn, V2 + mid)), ((-Wn, -(V2 + mid)), (Wn, -(V2 + mid)))]
        zones = [box(-neck, Vf, neck, V1), box(-neck, -V1, neck, -Vf),
                 box(-Wn, V2, Wn, V2 + b), box(-Wn, -(V2 + b), Wn, -V2)]

        if full_walls:
            U1 = Uf + b
            U2 = U1 + D - a
            self.U1, self.U2 = U1, U2
            right = [box(Uf, -Vf, U1, Vf), box(U1, -Q / 2, U2, Q / 2)]
            rects += right + [affinity.scale(g_, -1, 1, origin=(0, 0)) for g_ in right]
            bends += [((Uf + mid, -Vf), (Uf + mid, Vf)), ((-(Uf + mid), -Vf), (-(Uf + mid), Vf))]
            zones += [box(Uf, -Vf, U1, Vf), box(-U1, -Vf, -Uf, Vf)]
        else:
            assert tab_h, "channel needs tab_h"
            tab_flat = tab_h - a
            self.tab_h = tab_h
            for (d0, d1) in tab_segs:
                v0, v1 = self.v_wall(d0), self.v_wall(d1)
                for su in (1, -1):
                    for sv in (1, -1):
                        u_in, u_out = Uf, Uf + b + tab_flat
                        x0, x1 = sorted((su * u_in, su * u_out))
                        y0, y1 = sorted((sv * v0, sv * v1))
                        rects.append(box(x0, y0, x1, y1))
                        ub = su * (Uf + mid)
                        bends.append(((ub, y0), (ub, y1)))
                        xb0, xb1 = sorted((su * Uf, su * (Uf + b)))
                        zones.append(box(xb0, y0, xb1, y1))

        poly = unary_union(rects).simplify(1e-6)
        part.outer = poly
        part.bends = bends
        part.bend_zones = zones
        minx, miny, maxx, maxy = poly.bounds
        part.facts += [f"Pelat dasar {P:g} x {Q:g} mm (ukuran LUAR), kedalaman dinding {D:g} mm",
                       f"Tekukan 90 derajat x {len(bends)}, r dalam {r:g}, K={k:g}, BA={b:.3f}, setback={a:g}",
                       f"Pola datar {maxx - minx:.1f} x {maxy - miny:.1f} mm"]

    # 3D (outer) coordinates -> flat coordinates; depth d measured from the base outer face
    def u_wall(self, d):
        return self.P / 2 - 2 * self.a + self.b + d

    def v_wall(self, d):
        return self.Q / 2 - 2 * self.a + self.b + d

    def v_flange(self, e):                   # e = distance from the wall's outer face inward
        return self.Q / 2 + self.D + 2 * self.b - 4 * self.a + e

    def tab_u(self, e):                      # e = distance from the narrow wall's outer face
        return self.Uf + self.b + (e - self.a)


def feat_cam(tray):
    """Camera channel: front plate = base, x -> u, z -> v. x runs 0..W across the channel."""
    W, H = tray.P, tray.Q
    return {
        "front": lambda x, z: (x - W / 2, z - H / 2),
        "bottom": lambda x, d: (x - W / 2, -tray.v_wall(d)),
        "top": lambda x, d: (x - W / 2, tray.v_wall(d)),
        "fl_top": lambda x, e: (x - W / 2, tray.v_flange(e)),
        "fl_bot": lambda x, e: (x - W / 2, -tray.v_flange(e)),
        # side tab: sx=+1 right/-1 left, top=True/False, depth d, e = distance from the wall's outer face
        "tab": lambda sx, top, d, e: (sx * tray.tab_u(e), (1 if top else -1) * tray.v_wall(d)),
    }


# =====================================================================================
# PARTS
# =====================================================================================
PARTS = []
CHECKS = []          # (description, ok, detail)


def add(p):
    PARTS.append(p)
    return p


def check(desc, ok, detail=""):
    CHECKS.append((desc, bool(ok), detail))
    assert ok, f"CHECK FAILED: {desc} {detail}"


def build_camera_channel():
    p = add(Part("A1", "Badan kamera - WADAH (saluran: depan + atas + bawah)", "Aluminium 5052-H32", T_AL, 1,
                 "Tekuk atas/bawah + 2 flens belakang + 4 sirip sisi. Sisi kiri/kanan = plat baja S1/S2.", bent=True))
    tr = Tray(p, BODY_W, BODY_H, BODY_D, T_AL, R_AL, K_FACTOR, FLANGE_F,
              full_walls=False, tab_h=SIDE_TAB_H, tab_segs=TAB_SEGS)
    f = feat_cam(tr)
    W, H, D = BODY_W, BODY_H, BODY_D
    pcb_x0, pcb_y0 = MARGIN_L, T_AL + CAM_DEPTH

    # lens window + camera board holes (front plate). Lens axis = centre of the front plate.
    p.hole(*f["front"](W / 2, H / 2), LENS_HOLE_D)
    for dx, dz in CAM_HOLES:
        p.hole(*f["front"](W / 2 + dx, H / 2 + dz), CAM_HOLE_D)
    # PCB standoff screws through the bottom wall
    stand = [(pcb_x0 + hx, pcb_y0 + hy) for hx, hy in PCB_HOLES]
    for x, d in stand:
        p.hole(*f["bottom"](x, d), M3_CLEAR)
    # ventilation slots under the LuckFox (J1 is at rel. x=12.0, y=35.0 on the PCB)
    for dxr in (12.0, 20.0):
        for dyr in (22.0, 34.0, 46.0):
            x, d = pcb_x0 + dxr, pcb_y0 + dyr
            near = min(math.hypot(x - sx, d - sd) for sx, sd in stand)
            check("vent slot clear of standoff screws", near >= 7.0, f"{near:.1f} mm")
            u, v = f["bottom"](x, d)
            p.cut(slot_path(u, v, 10.0, 3.0, 90.0), "vent")
    # RF window above the ESP32 (aluminium shields the antenna!)
    ex0, ex1 = pcb_x0 + ESP_X0 - 2.0, pcb_x0 + ESP_X0 + ESP_W + 2.0
    ed0, ed1 = pcb_y0 + ESP_Y0 - 2.0, pcb_y0 + ESP_Y0 + ESP_L + 2.0
    (u0, v0), (u1, v1) = f["top"](ex0, ed0), f["top"](ex1, ed1)
    p.cut(rounded_rect(min(u0, u1), min(v0, v1), max(u0, u1), max(v0, v1), 2.0), "RF window")
    p.facts.append(f"Jendela RF {ex1 - ex0:.0f} x {ed1 - ed0:.0f} mm di dinding atas (tutup akrilik A3)")
    # plate-to-tab screws (same pattern on both sides)
    for d, z in SIDE_SCREW_POS:
        top = z > H / 2
        e = (H - z) if top else z
        for sx in (-1, 1):
            p.hole(*f["tab"](sx, top, d, e), M3_CLEAR)
    # lid rivet nuts in the rear flanges (top + bottom)
    for sx in (-1, 1):
        p.hole(*f["fl_top"](W / 2 + sx * LID_HOLE_DX, LID_HOLE_E), M3_RIVNUT)
        p.hole(*f["fl_bot"](W / 2 + sx * LID_HOLE_DX, LID_HOLE_E), M3_RIVNUT)

    # ---- fit checks (inner clearances) ----
    inner_h = H - 2 * T_AL
    stack_top = STANDOFF_H + PCB_T + COMPONENT_CLEARANCE
    check("PCB stack fits under the top wall", stack_top <= inner_h, f"{stack_top:.1f} <= {inner_h:.1f}")
    pcb_rear = pcb_y0 + PCB_H
    check("PCB clears the rear flange (USB-C overhang ~5 mm)", pcb_rear + 5 <= D - T_AL,
          f"{pcb_rear + 5:.1f} <= {D - T_AL:.1f}")
    margin_r = BODY_W - MARGIN_L - PCB_W
    check("room for the pivot nuts either side of the PCB", margin_r >= 6.0 and MARGIN_L >= 6.0,
          f"left {MARGIN_L:.1f}, right {margin_r:.1f} mm")
    check("RF window inside the top wall's flat width", ex0 >= (W / 2 - tr.Uf) + 3 and ex1 <= (W / 2 + tr.Uf) - 3, "")
    check("lens window fits the front plate", LENS_HOLE_D <= min(W, H) - 8, f"{LENS_HOLE_D} <= {min(W, H) - 8}")
    return p, tr


def build_lid():
    p = add(Part("A2", "Badan kamera - TUTUP belakang", "Aluminium 5052-H32", T_AL, 1,
                 "Plat datar menutupi juga tepi plat baja. 4 baut M3 ke rivet nut di flens wadah."))
    p.outer_path = rounded_rect(0, 0, BODY_OUT_W, BODY_H, 4.0)
    p.outer = Polygon(path_points(p.outer_path))
    for sx in (-1, 1):
        for z in (LID_HOLE_E, BODY_H - LID_HOLE_E):
            p.hole(BODY_OUT_W / 2 + sx * LID_HOLE_DX, z, 3.4)
    for xr in (-12.0, -4.0, 4.0, 12.0):                 # chimney vents, upper half
        p.cut(slot_path(BODY_OUT_W / 2 + xr, BODY_H / 2 + 5.0, 14.0, 3.0, 90.0), "lid vent")
    return p


def steel_side_plate(key, title, right):
    p = add(Part(key, title, "Baja lunak (mild steel)", T_ST, 1,
                 "SISI badan kamera. Cat/powder-coat atau pakai stainless 304 3 mm."))
    p.outer_path = rounded_rect(0, 0, BODY_D, BODY_H, PLATE_CORNER_R)
    p.outer = Polygon(path_points(p.outer_path))
    p.hole(PIVOT_D, PIVOT_Z, RIGHT_BOSS_HOLE if right else LEFT_BOLT_HOLE)
    if not right:
        p.hole(PIVOT_D, PIVOT_Z - CLAMP_R, CLAMP_HOLE)
    for d, z in SIDE_SCREW_POS:
        p.hole(d, z, M3_CLEAR)
    return p


def arm(key, title, right):
    a, b = A_ST, BA_ST
    foot_flat = ARM_FOOT_LEN - a
    leg_start = foot_flat + b
    h_axis = AXIS_BELOW_BOX
    end_r = ARM_W / 2.0
    leg_out = h_axis + end_r                       # leg outside length from the outer corner
    total = ARM_FOOT_LEN + leg_out - (2 * a - b)
    p = add(Part(key, title, "Baja lunak (mild steel)", T_ST, 1,
                 "Braket L, 1 tekukan. Kaki (foot) dibaut ke dasar kotak plafon dengan rivet nut M4.", bent=True))
    s_axis = leg_start + (h_axis - a)              # flat position of the pivot centre
    r_c = 4.0
    bl = math.tan(math.pi / 8)
    path = [(r_c, -ARM_W / 2, 0), (s_axis, -ARM_W / 2, 1.0), (s_axis, ARM_W / 2, 0),
            (r_c, ARM_W / 2, bl), (0, ARM_W / 2 - r_c, 0), (0, -ARM_W / 2 + r_c, bl)]
    p.outer_path = path
    p.outer = Polygon(path_points(path))
    p.bends = [((foot_flat + b / 2, -ARM_W / 2), (foot_flat + b / 2, ARM_W / 2))]
    p.bend_zones = [box(foot_flat, -ARM_W / 2, leg_start, ARM_W / 2)]
    p.facts += [f"Panjang pola datar {total:.1f} mm (s_axis={s_axis:.1f}), lebar {ARM_W:g} mm",
                f"Kaki {ARM_FOOT_LEN:g} mm luar, lurus ke tengah; sumbu {AXIS_BELOW_BOX:g} mm di bawah dasar kotak"]
    for sy in (-1, 1):
        p.hole(ARM_FOOT_LEN - ARM_FOOT_HOLE, sy * ARM_FOOT_HOLE_Y, M4_CLEAR)
    if right:
        p.hole(s_axis, 0.0, RIGHT_BOSS_HOLE)
        for h in (22.0, 36.0):                      # zip-tie pairs for the cable run
            s = foot_flat + b + (h - a)
            for sy in (-1, 1):
                p.hole(s, sy * 5.0, 3.5)
    else:
        p.hole(s_axis, 0.0, LEFT_BOLT_HOLE)
        p.cut(arc_slot_path(s_axis, 0.0, CLAMP_R, -CLAMP_ARC_DEG, CLAMP_ARC_DEG, CLAMP_HOLE), "tilt-lock slot")
        half = CLAMP_R * math.sin(math.radians(CLAMP_ARC_DEG)) + CLAMP_HOLE / 2
        check("tilt-lock slot stays inside the arm width", half <= ARM_W / 2 - 2, f"{half:.1f} <= {ARM_W / 2 - 2:.1f}")
    return p


def build_box():
    p = add(Part("B1", "Kotak plafon - WADAH (tray terbuka di atas)", "Aluminium 5052-H32", T_AL, 1,
                 "Tekuk 4 sisi + 2 flens atas (dinding +Y/-Y). Bukaan sisi di dinding +Y.", bent=True))
    tr = Tray(p, BOX_X, BOX_Y, BOX_Z, T_AL, R_AL, K_FACTOR, BOX_FLANGE_F)
    X, Y, Z = BOX_X, BOX_Y, BOX_Z
    # base viewed from below: u = x - X/2, v = -(y - Y/2). Wall +Y -> flat 'bottom', wall -Y -> flat 'top'.
    base = lambda x, y: (x - X / 2, -(y - Y / 2))
    wall_py = lambda x, z: (x - X / 2, -tr.v_wall(z))        # +Y wall (the one with the opening)
    fl_py = lambda x, e: (x - X / 2, -tr.v_flange(e))
    fl_ny = lambda x, e: (x - X / 2, tr.v_flange(e))
    # arm feet (rivet nuts M4) and cable grommet in the base
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.hole(*base(X / 2 + sx * (ARM_X_INNER + SIDE_PLATE_T - ARM_FOOT_HOLE), Y / 2 + sy * ARM_FOOT_HOLE_Y), M4_RIVNUT)
    p.hole(*base(X / 2 + GROMMET_X, Y / 2 + GROMMET_Y), GROMMET_D)
    # opening + future carrier plate's rivet nuts (M3) in the +Y wall
    cx, cz = X / 2, Z / 2
    ux, uz = wall_py(cx, cz)
    p.cut(rounded_rect(ux - OPENING_W / 2, uz - OPENING_H / 2, ux + OPENING_W / 2, uz + OPENING_H / 2, 4.0), "opening")
    for sx, sz in PLATE_SCREWS:
        p.hole(*wall_py(cx + sx, cz + sz), M3_RIVNUT)
    # lid rivet nuts in the flanges of both Y walls
    for sx in (-1, 1):
        p.hole(*fl_py(X / 2 + sx * 45.0, BOX_LID_E), M3_RIVNUT)
        p.hole(*fl_ny(X / 2 + sx * 45.0, BOX_LID_E), M3_RIVNUT)
    p.facts.append(f"Bukaan sisi {OPENING_W:g} x {OPENING_H:g} mm di dinding +Y; 4 lubang rivet nut M3 untuk plat "
                   f"{PLATE_W:g} x {PLATE_H:g} mm (plat belum dibuat)")
    return p


def build_box_lid():
    p = add(Part("B2", "Kotak plafon - TUTUP atas dengan telinga", "Aluminium 5052-H32", T_AL, 1,
                 "Plat datar. Telinga kiri/kanan = lubang angkur plafon. 4 baut M3 ke flens kotak."))
    Wl = BOX_X + 2 * LID_EAR
    p.outer_path = rounded_rect(0, 0, Wl, BOX_Y, 5.0)
    p.outer = Polygon(path_points(p.outer_path))
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.hole(Wl / 2 + sx * 45.0, BOX_Y / 2 + sy * (BOX_Y / 2 - BOX_LID_E), 3.4)
            p.hole(Wl / 2 + sx * (BOX_X / 2 + LID_EAR / 2), BOX_Y / 2 + sy * 16.0, ANCHOR_D)
    return p


def build_rf_cover():
    ex = ESP_W + 4.0 + 12.0
    ey = ESP_L + 4.0 + 12.0
    p = add(Part("A3", "Tutup jendela RF (akrilik, tempel dengan double-tape)", "Akrilik", 3.0, 1,
                 "Menutup jendela di dinding atas A1 agar debu tidak masuk tapi WiFi tetap tembus."))
    p.outer_path = rounded_rect(0, 0, ex, ey, 3.0)
    p.outer = Polygon(path_points(p.outer_path))
    return p


def build_all():
    cam, cam_tr = build_camera_channel()
    build_lid()
    steel_side_plate("S1", "Plat sisi KIRI badan kamera (baut M6 + kunci miring)", right=False)
    steel_side_plate("S2", "Plat sisi KANAN badan kamera (baut bos berongga M10x1)", right=True)
    arm("S3", "Lengan KIRI (braket L, slot busur kunci miring)", right=False)
    arm("S4", "Lengan KANAN (braket L, jalur kabel)", right=True)
    build_box()
    build_box_lid()
    build_rf_cover()
    return cam_tr


# =====================================================================================
# GEOMETRY CHECKS ON THE ASSEMBLY
# =====================================================================================
def assembly_checks():
    # rotation envelope of the body (steel plate is the largest rotating part)
    diag = math.hypot(BODY_D / 2, BODY_H / 2)
    clearance = AXIS_BELOW_BOX - diag - T_ST            # to the underside of the arm feet (z = -T_ST)
    check("body can rotate under the box feet (>= 3 mm)", clearance >= 3.0, f"{clearance:.1f} mm")
    check("arm strip is wide enough around the boss hole", ARM_W >= RIGHT_BOSS_HOLE + 2 * 8, "")

    # ---- pivot hardware stacks (right = hollow M10x1 stud, left = M6 bolt, head INSIDE the body) ----
    WASH, NUT10, NUT10_OUT, NYLON = 1.5, 4.0, 4.0, 1.0
    half = BODY_W / 2                                    # steel plate's inner face is at x = +-half
    tip_x = half - WASH - NUT10 - 0.5                    # inner end of the stud
    nipple_len = 25.0
    end_x = tip_x + nipple_len
    outer_stack = half + SIDE_PLATE_T + NYLON + T_ST + WASH + 2 * NUT10_OUT   # plate+nylon+arm+washer+2 nuts
    check("hollow stud (25 mm) sticks out >= 0.5 mm past the jam nut", end_x - outer_stack >= 0.5,
          f"stud end x={end_x:.1f}, nuts end x={outer_stack:.1f}")
    margin_r = BODY_W - MARGIN_L - PCB_W
    check("right pivot nut + washer clear the PCB", WASH + NUT10 + 0.5 <= margin_r - 1.0,
          f"intrusion {WASH + NUT10 + 0.5:.1f} mm, PCB margin {margin_r:.1f} mm")
    check("left M6 head + washer clear the PCB", 4.0 + 1.6 <= MARGIN_L - 1.0, f"intrusion 5.6 mm, margin {MARGIN_L:.1f} mm")
    # pivot nut (AF 14) must clear the side tabs (the tabs stop around the pivot)
    gap0, gap1 = TAB_SEGS[0][1], TAB_SEGS[1][0]
    check("tab gap leaves room for the pivot nut", gap0 + 7.0 <= PIVOT_D <= gap1 - 7.0,
          f"tabs end at d={gap0:g}, restart at d={gap1:g}, pivot at d={PIVOT_D:g}")

    # ---- cable: leaves the stud end, quarter turn R = 12 mm, then an S-curve to the grommet ----
    turn_r = 12.0
    rise_x = end_x + turn_r
    shift = rise_x - GROMMET_X
    run = AXIS_BELOW_BOX - turn_r
    s_radius = run ** 2 / (4 * shift) if shift > 0 else float("inf")
    check("cable S-curve to the grommet is gentle (radius >= 25 mm)", s_radius >= 25.0,
          f"rises at x={rise_x:.1f}, grommet x={GROMMET_X:.1f}, S radius ~{s_radius:.0f} mm")
    arm_outer = ARM_X_INNER + T_ST
    check("grommet clear of the arm foot (>= 3 mm)", GROMMET_X - GROMMET_D / 2 - arm_outer >= 3.0,
          f"{GROMMET_X - GROMMET_D / 2 - arm_outer:.1f} mm")
    check("grommet inside the flat part of the box base", GROMMET_X + GROMMET_D / 2 + 3.0 <= BOX_X / 2 - A_AL,
          f"{GROMMET_X + GROMMET_D / 2:.1f} + 3 <= {BOX_X / 2 - A_AL:.1f}")
    # box: opening + future plate screws fit the +Y wall
    wall_flat_z = BOX_Z - 2 * A_AL
    check("plate interface fits the wall's flat height", PLATE_H <= wall_flat_z, f"{PLATE_H} <= {wall_flat_z}")
    check("plate interface fits the wall's flat width", PLATE_W <= BOX_X - 2 * (T_AL + CORNER_GAP), "")
    sx = max(abs(s[0]) for s in PLATE_SCREWS)
    check("plate screws keep a web >= 2 mm beside the opening", sx - OPENING_W / 2 - M3_RIVNUT / 2 >= 2.0,
          f"{sx - OPENING_W / 2 - M3_RIVNUT / 2:.1f} mm")
    check("plate screws keep >= 2 mm to the plate edge", PLATE_W / 2 - sx - 1.7 >= 2.0, "")
    check("arm foot fits under the box", ARM_X_INNER + T_ST + 5 <= BOX_X / 2, "")
    check("arm legs sit inside the box footprint in Y", ARM_W / 2 <= BOX_Y / 2 - A_AL + 0.01,
          f"{ARM_W / 2} <= {BOX_Y / 2 - A_AL}")


# =====================================================================================
# EXPORT
# =====================================================================================
FILE_NAMES = {"A1": "wadah_badan_kamera", "A2": "tutup_badan_kamera", "A3": "tutup_jendela_RF_akrilik",
              "B1": "kotak_plafon_wadah", "B2": "kotak_plafon_tutup_telinga",
              "S1": "plat_sisi_kiri", "S2": "plat_sisi_kanan_bos_kabel", "S3": "lengan_kiri_slot",
              "S4": "lengan_kanan_kabel"}


def export_dxf():
    d = os.path.join(OUT, "dxf")
    os.makedirs(d, exist_ok=True)
    for old in os.listdir(d):
        os.remove(os.path.join(d, old))
    for part in PARTS:
        doc = new_doc()
        part.draw(doc.modelspace(), 0, 0)
        doc.saveas(os.path.join(d, f"{part.key}_{FILE_NAMES[part.key]}.dxf"))


def nest(parts, sheet_w, gap=14.0):
    """Shelf packing; returns (placements, sheet_h)."""
    items = sorted(parts, key=lambda q: -q.size()[1])
    x = y = row_h = 0.0
    placed = []
    for q in items:
        for _ in range(q.qty):
            w, h = q.size()
            if x + w > sheet_w and x > 0:
                x, y, row_h = 0.0, y + row_h + gap, 0.0
            placed.append((q, x, y))
            x += w + gap
            row_h = max(row_h, h)
    return placed, y + row_h


def export_sheets():
    d = os.path.join(OUT, "sheets")
    os.makedirs(d, exist_ok=True)
    for old in os.listdir(d):
        os.remove(os.path.join(d, old))
    groups = {}
    for q in PARTS:
        groups.setdefault((q.material, q.t), []).append(q)
    summary = []
    for (mat, t), parts in groups.items():
        placed, h = nest(parts, 600.0)
        w = max(px + q.size()[0] for q, px, _ in placed)
        doc = new_doc()
        for q, px, py in placed:
            q.draw(doc.modelspace(), px, py)
        name = f"sheet_{mat.split()[0].lower()}_{t:g}mm.dxf"
        doc.saveas(os.path.join(d, name))
        summary.append((name, mat, t, w, h, len(placed)))
    return summary


def export_png():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.COLOR)
    d = os.path.join(OUT, "png")
    os.makedirs(d, exist_ok=True)
    for old in os.listdir(d):
        os.remove(os.path.join(d, old))

    def render(doc, path, size):
        fig = plt.figure(figsize=size, dpi=110, facecolor="white")
        ax = fig.add_axes([0.02, 0.02, 0.96, 0.96])
        ax.set_aspect("equal")
        Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(doc.modelspace())
        fig.savefig(path, facecolor="white")
        plt.close(fig)

    for part in PARTS:
        doc = new_doc()
        part.draw(doc.modelspace(), 0, 0)
        w, h = part.size()
        s = 9.0 / max(w, h + 8)
        render(doc, os.path.join(d, f"{part.key}.png"), (max(w * s, 4) + 1, max((h + 8) * s, 3) + 1))
    for f in sorted(os.listdir(os.path.join(OUT, "sheets"))):
        doc = ezdxf.readfile(os.path.join(OUT, "sheets", f))
        render(doc, os.path.join(d, f.replace(".dxf", ".png")), (12, 9))


# =====================================================================================
# 3D SANITY VIEW (boxes, not the real folded geometry)
# =====================================================================================
def assembly_png():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    fig = plt.figure(figsize=(11, 8), dpi=110)
    ax = fig.add_subplot(111, projection="3d")

    def cuboid(x0, x1, y0, y1, z0, z1, color, alpha=0.35, edge="k"):
        v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        faces = [[v[i] for i in f] for f in ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 3, 7, 4))]
        ax.add_collection3d(Poly3DCollection(faces, facecolors=color, edgecolors=edge, linewidths=0.6, alpha=alpha))

    bx, by, bz = BOX_X / 2, BOX_Y / 2, BOX_Z
    cuboid(-bx, bx, -by, by, 0, bz, "#9fb4c7", 0.22)                                   # ceiling box
    cuboid(-bx - LID_EAR, bx + LID_EAR, -by, by, bz, bz + T_AL, "#7a8fa3", 0.6)        # lid + ears
    cuboid(-OPENING_W / 2, OPENING_W / 2, by, by + 0.5, bz / 2 - OPENING_H / 2, bz / 2 + OPENING_H / 2, "#f2c14e", 0.8)  # opening
    axz = -AXIS_BELOW_BOX
    for s in (-1, 1):                                                                # arms (leg + foot)
        xi, xo = s * ARM_X_INNER, s * (ARM_X_INNER + T_ST)
        cuboid(min(xi, xo), max(xi, xo), -ARM_W / 2, ARM_W / 2, axz - ARM_W / 2, 0, "#c0504d", 0.55)
        xf = s * (ARM_X_INNER + T_ST - ARM_FOOT_LEN)
        cuboid(min(xo, xf), max(xo, xf), -ARM_W / 2, ARM_W / 2, -T_ST, 0, "#c0504d", 0.7)
    y0, y1 = -BODY_D / 2, BODY_D / 2
    z0, z1 = axz - BODY_H / 2, axz + BODY_H / 2
    cuboid(-BODY_W / 2, BODY_W / 2, y0, y1, z1 - T_AL, z1, "#bcd3b0", 0.5)               # channel: top wall
    cuboid(-BODY_W / 2, BODY_W / 2, y0, y1, z0, z0 + T_AL, "#bcd3b0", 0.5)               # bottom wall
    cuboid(-BODY_W / 2, BODY_W / 2, y0, y0 + T_AL, z0, z1, "#bcd3b0", 0.5)               # front wall
    for s in (-1, 1):                                                                # steel side plates
        xi = s * BODY_W / 2
        cuboid(min(xi, xi + s * T_ST), max(xi, xi + s * T_ST), y0, y1, z0, z1, "#5b6b7b", 0.5)
    pcb_x0 = -BODY_W / 2 + MARGIN_L
    pcb_y0 = y0 + T_AL + CAM_DEPTH
    cuboid(pcb_x0, pcb_x0 + PCB_W, pcb_y0, pcb_y0 + PCB_H, z0 + T_AL + STANDOFF_H, z0 + T_AL + STANDOFF_H + PCB_T, "#2e7d32", 0.9)
    ax.plot([BODY_W / 2 - 8, BODY_W / 2 + 22], [0, 0], [axz, axz], color="#e08b00", lw=4)     # M10 hollow stud
    ax.plot([-BODY_W / 2 - 8, -BODY_W / 2 - 14], [0, 0], [axz, axz], color="#444", lw=4)       # M6 bolt
    ax.plot([BODY_W / 2 + 22, GROMMET_X + 14, GROMMET_X], [0, 0, 0], [axz, axz + 25, 0], color="#e08b00", lw=1.5, ls="--")  # cable
    ax.scatter([0], [y0], [axz], color="r", s=30)                                              # lens side (front)
    ax.set_xlim(-100, 100); ax.set_ylim(-100, 100); ax.set_zlim(-120, 90)
    ax.set_box_aspect((200, 200, 210))
    ax.set_xlabel("X (arah sumbu putar)"); ax.set_ylabel("Y (depan = -Y)"); ax.set_zlabel("Z")
    ax.view_init(elev=18, azim=-58)
    ax.set_title("VIPARK laser-cut - tinjauan susunan (kotak sederhana, bukan geometri lipatan)")
    fig.savefig(os.path.join(OUT, "assembly.png"), facecolor="white")
    plt.close(fig)


# =====================================================================================
# PARTS TABLE
# =====================================================================================
def write_table(sheet_summary):
    rows, total = [], {}
    for q in PARTS:
        w, h = q.size()
        rows.append(f"| {q.key} | {q.title} | {q.material} | {q.t:g} | {q.qty} | {w:.0f} x {h:.0f} | {q.mass_g():.0f} | {'ya' if q.bent else '-'} |")
        total[q.material] = total.get(q.material, 0) + q.mass_g() * q.qty
    with open(os.path.join(OUT, "parts_table.md"), "w") as f:
        f.write("| Kode | Komponen | Bahan | Tebal (mm) | Jml | Pola datar (mm) | Massa (g) | Tekuk |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        f.write("\n".join(rows) + "\n\n")
        f.write("Massa total: " + ", ".join(f"{m} {g:.0f} g" for m, g in total.items()) + "\n\n")
        f.write("Lembar nesting (file di `out/sheets/`):\n\n")
        for name, mat, t, w, h, n in sheet_summary:
            f.write(f"- `{name}`: {mat} {t:g} mm, {n} bagian, area {w:.0f} x {h:.0f} mm\n")
        f.write("\nPemeriksaan otomatis yang lulus:\n\n")
        for d, ok, detail in CHECKS:
            f.write(f"- {'OK' if ok else 'GAGAL'}: {d}" + (f" ({detail})" if detail else "") + "\n")
        f.write("\nFakta per bagian:\n\n")
        for q in PARTS:
            for fact in q.facts:
                f.write(f"- {q.key}: {fact}\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    build_all()
    assembly_checks()
    export_dxf()
    summary = export_sheets()
    export_png()
    assembly_png()
    write_table(summary)
    print(f"{len(PARTS)} parts, {sum(1 for _, ok, _ in CHECKS if ok)}/{len(CHECKS)} checks OK")
    for q in PARTS:
        w, h = q.size()
        print(f"  {q.key:3} {q.title[:58]:58} {q.material.split()[0]:9} {q.t:g}mm  {w:6.1f} x {h:6.1f}  {q.mass_g():6.1f} g")
    print("outputs ->", OUT)


if __name__ == "__main__":
    main()
