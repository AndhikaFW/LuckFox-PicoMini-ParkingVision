| Kode | Komponen | Bahan | Tebal (mm) | Jml | Pola datar (mm) | Massa (g) | Tekuk |
|---|---|---|---|---|---|---|---|
| A1 | Badan kamera - WADAH (saluran: depan + atas + bawah) | Aluminium 5052-H32 | 2 | 1 | 87 x 250 | 80 | ya |
| A2 | Badan kamera - TUTUP belakang | Aluminium 5052-H32 | 2 | 1 | 68 x 44 | 15 | - |
| S1 | Plat sisi KIRI badan kamera (baut M6 + kunci miring) | Baja lunak (mild steel) | 3 | 1 | 94 x 44 | 95 | - |
| S2 | Plat sisi KANAN badan kamera (baut bos berongga M10x1) | Baja lunak (mild steel) | 3 | 1 | 94 x 44 | 94 | - |
| S3 | Lengan KIRI (braket L, slot busur kunci miring) | Baja lunak (mild steel) | 3 | 1 | 97 x 36 | 75 | ya |
| S4 | Lengan KANAN (braket L, jalur kabel) | Baja lunak (mild steel) | 3 | 1 | 97 x 36 | 75 | ya |
| B1 | Kotak plafon - WADAH (tray terbuka di atas) | Aluminium 5052-H32 | 2 | 1 | 217 x 168 | 118 | ya |
| B2 | Kotak plafon - TUTUP atas dengan telinga | Aluminium 5052-H32 | 2 | 1 | 154 x 54 | 44 | - |
| A3 | Tutup jendela RF (akrilik, tempel dengan double-tape) | Akrilik | 3 | 1 | 44 x 71 | 11 | - |

Massa total: Aluminium 5052-H32 256 g, Baja lunak (mild steel) 339 g, Akrilik 11 g

Lembar nesting (file di `out/sheets/`):

- `sheet_aluminium_2mm.dxf`: Aluminium 5052-H32 2 mm, 4 bagian, area 568 x 250 mm
- `sheet_baja_3mm.dxf`: Baja lunak (mild steel) 3 mm, 4 bagian, area 423 x 44 mm
- `sheet_akrilik_3mm.dxf`: Akrilik 3 mm, 1 bagian, area 44 x 71 mm

Pemeriksaan otomatis yang lulus:

- OK: vent slot clear of standoff screws (19.8 mm)
- OK: vent slot clear of standoff screws (26.5 mm)
- OK: vent slot clear of standoff screws (15.5 mm)
- OK: vent slot clear of standoff screws (24.2 mm)
- OK: vent slot clear of standoff screws (29.9 mm)
- OK: vent slot clear of standoff screws (20.8 mm)
- OK: PCB stack fits under the top wall (38.6 <= 40.0)
- OK: PCB clears the rear flange (USB-C overhang ~5 mm) (85.2 <= 92.0)
- OK: room for the pivot nuts either side of the PCB (left 7.0, right 10.0 mm)
- OK: RF window inside the top wall's flat width
- OK: lens window fits the front plate (18.5 <= 36.0)
- OK: tilt-lock slot stays inside the arm width (11.1 <= 16.0)
- OK: body can rotate under the box feet (>= 3 mm) (5.1 mm)
- OK: arm strip is wide enough around the boss hole
- OK: hollow stud (25 mm) sticks out >= 0.5 mm past the jam nut (stud end x=50.0, nuts end x=47.5)
- OK: right pivot nut + washer clear the PCB (intrusion 6.0 mm, PCB margin 10.0 mm)
- OK: left M6 head + washer clear the PCB (intrusion 5.6 mm, margin 7.0 mm)
- OK: tab gap leaves room for the pivot nut (tabs end at d=34, restart at d=60, pivot at d=47)
- OK: cable S-curve to the grommet is gentle (radius >= 25 mm) (rises at x=62.0, grommet x=48.0, S radius ~41 mm)
- OK: grommet clear of the arm foot (>= 3 mm) (5.0 mm)
- OK: grommet inside the flat part of the box base (53.0 + 3 <= 58.0)
- OK: plate interface fits the wall's flat height (40.0 <= 42.0)
- OK: plate interface fits the wall's flat width
- OK: plate screws keep a web >= 2 mm beside the opening (2.5 mm)
- OK: plate screws keep >= 2 mm to the plate edge
- OK: arm foot fits under the box
- OK: arm legs sit inside the box footprint in Y (18.0 <= 23.0)

Fakta per bagian:

- A1: Pelat dasar 62 x 44 mm (ukuran LUAR), kedalaman dinding 94 mm
- A1: Tekukan 90 derajat x 12, r dalam 2, K=0.4, BA=4.398, setback=4
- A1: Pola datar 86.8 x 249.6 mm
- A1: Jendela RF 32 x 59 mm di dinding atas (tutup akrilik A3)
- S3: Panjang pola datar 96.6 mm (s_axis=78.6), lebar 36 mm
- S3: Kaki 24 mm luar, lurus ke tengah; sumbu 60 mm di bawah dasar kotak
- S4: Panjang pola datar 96.6 mm (s_axis=78.6), lebar 36 mm
- S4: Kaki 24 mm luar, lurus ke tengah; sumbu 60 mm di bawah dasar kotak
- B1: Pelat dasar 124 x 54 mm (ukuran LUAR), kedalaman dinding 50 mm
- B1: Tekukan 90 derajat x 6, r dalam 2, K=0.4, BA=4.398, setback=4
- B1: Pola datar 216.8 x 167.6 mm
- B1: Bukaan sisi 96 x 30 mm di dinding +Y; 4 lubang rivet nut M3 untuk plat 116 x 40 mm (plat belum dibuat)
