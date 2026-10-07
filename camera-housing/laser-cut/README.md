# Casing VIPARK untuk laser cutting (aluminium + baja)

Pola datar (DXF) untuk casing kamera + kotak plafon. Semua angka ada di `make_laser_cut.py` (bagian parameter);
ubah lalu jalankan ulang:

```
pip install ezdxf shapely matplotlib rectpack
python3 make_laser_cut.py        # DXF, pratinjau, tabel komponen -> out/
python3 make_print_a4.py         # PDF cetak 1:1 di kertas A4      -> out/cetak_A4_1to1.pdf
```

| Folder / file | Isi |
|---|---|
| `out/dxf/` | **satu DXF per komponen**, kirim ini ke toko laser |
| `out/sheets/` | komponen yang sama ditata per bahan (aluminium 2 mm, baja 3 mm, akrilik 3 mm) |
| `out/png/` | pratinjau tiap pola datar |
| `out/cetak_A4_1to1.pdf` | **4 halaman A4, skala 1:1**, tiap bagian utuh (tidak dibelah) |
| `out/assembly.png` | tinjauan susunan 3D (kotak kasar, bukan geometri lipatan) |
| `out/parts_table.md` | tabel komponen, massa, dan semua pemeriksaan otomatis |

## Komponen

| Kode | Bagian | Bahan | Pola datar | Tekuk |
|---|---|---|---|---|
| A1 | wadah badan kamera: saluran depan + atas + bawah, flens belakang, sirip sisi | Al 2 mm | 87 × 250 | ya |
| A2 | tutup belakang kamera (4 baut M3 ke rivet nut di flens A1) | Al 2 mm | 68 × 44 | - |
| A3 | tutup jendela RF (tempel double-tape) | akrilik 3 mm | 44 × 71 | - |
| S1 / S2 | **plat sisi kiri / kanan** badan kamera (membawa poros ke lengan) | baja 3 mm | 94 × 44 | - |
| S3 / S4 | lengan kiri (slot kunci sudut) / kanan (jalur kabel), braket L | baja 3 mm | 97 × 36 | ya (1) |
| B1 | kotak plafon: tray 4 sisi + 2 flens, bukaan sisi di dinding +Y | Al 2 mm | 217 × 168 | ya |
| B2 | tutup kotak plafon dengan telinga angkur | Al 2 mm | 154 × 54 | - |

Plat port **belum dibuat**. Kotak `B1` hanya punya **bukaan 96 × 30 mm** dan **4 lubang rivet nut M3** untuk plat
**116 × 40 mm** (baut di x = ±53, z = ±9 dari pusat bukaan). Plat yang nanti Anda buat mengikuti pola itu
(parameter `PLATE_*`, `OPENING_*`), atau kirim ukuran papan W5500 dan buck, lalu bukaannya saya sesuaikan.

Ukuran: kamera 62 (+2×3 mm plat baja = 68) × 44 × 94 mm; kotak plafon 124 × 54 × 50 mm (lid dengan telinga 154 mm).
Massa kerangka ±606 g (aluminium 256 g, baja 339 g, akrilik 11 g).

## Kamera SC3336: yang perlu Anda ukur

Lubang baut papan kamera **belum dipotong**. Dokumen publik hanya menyebut papan **25 × 24 mm**, tebal total **18 mm** dengan
lensa. Dari foto produk: **3 lubang baut di sudut**, lensa **tidak di tengah papan**, dan cincin depan laras lensa ±17 mm.
Karena itu asumsi lama (4 lubang M2, jarak 14 mm, lubang lensa Ø10,5) salah.

Ukur dengan jangka sorong, lalu isi di `make_laser_cut.py`:

```
LENS_HOLE_D = 18.5        # sekarang perkiraan dari foto; ganti dengan Ø laras terlebar yang melewati plat + 0,5 mm
CAM_HOLES   = [(dx, dz), ...]   # pusat tiap lubang baut relatif terhadap SUMBU LENSA, dilihat dari DEPAN
                                # (dx ke kanan, dz ke atas), dalam mm. Contoh: [(-8.5, 7.5), (9.0, -9.5), (9.0, 8.0)]
CAM_HOLE_D  = 2.2         # diameter lubang baut (M2)
CAM_DEPTH   = 15.0        # kedalaman rongga di belakang plat depan (papan + kabel FFC + standoff)
```

Yang diukur: (1) diameter lubang tiap baut, (2) posisi tiap lubang dari sudut kiri-bawah papan, (3) posisi sumbu lensa dari
sudut yang sama, (4) diameter terbesar laras lensa yang harus lewat lubang, (5) berapa mm laras menonjol di depan papan.
Foto papan dari atas bersama penggaris juga cukup.

## Cara baca gambar / pesan ke toko laser

* Layer **CUT** = potong; **BEND** = garis lipat (tengah zona tekuk, **jangan dipotong**); **LABEL** = teks, abaikan.
* Pola datar digambar menghadap sisi **luar**; semua tekukan 90° **menjauhi** pembaca.
* Aluminium **5052-H32 tebal 2 mm**: r dalam 2 mm, K = 0,40, setback luar 4 mm. Baja lunak **3 mm**: r dalam 3 mm.
  Jika toko punya tabel tekuk sendiri, minta mereka hitung ulang dari **ukuran LUAR** (tertera di `parts_table.md`).
* Lubang rivet nut `Ø5,0` (M3) dan `Ø6,0` (M4) mengikuti nut umum: **cocokkan dengan nut yang Anda beli**.
* Baja: bebas gerinda lalu cat/powder-coat atau zinc (atau stainless 304 3 mm). Aluminium + baja aman di dalam ruangan.

## Cara kerja sambungan

* **Plat baja = sisi kamera.** A1 tidak punya dinding samping; ia saluran dengan 4 sirip pendek (16 mm) di sisi.
  Plat `S1`/`S2` dibaut ke sirip dengan 4 baut M3×10 + mur nyloc per sisi. Sirip berhenti di sekitar poros supaya mur
  poros muat; mur dipasang dari sisi yang masih terbuka sebelum plat kedua dipasang.
* **Kotak plafon**: lengan `S3`/`S4` dibaut ke dasar `B1` dengan rivet nut M4 (kaki lurus ke tengah). Tutup `B2` dibaut
  dari atas ke rivet nut M3 di flens `B1`, telinganya untuk angkur plafon M6.
* **Kabel** keluar dari ujung pipa berongga di poros kanan, berbelok naik lalu masuk grommet Ø10 di dasar kotak (S-curve
  14 mm, radius ±41 mm, dicek di skrip).

## Baut bos jalur kabel + cincin pengunci (sisi KANAN)

**Pilihan utama: pipa ulir berongga M10×1,0** (*lamp pipe nipple*, bahan lampu gantung).

| Spesifikasi | Nilai |
|---|---|
| Ulir | M10 × 1,0 (halus) |
| Lubang dalam | ±6,7 mm (6,5–7,0 tergantung pabrik) → kabel **maks Ø5 mm** |
| Panjang | **25 mm** (beli 30–50 mm lalu gergaji dan haluskan ujungnya) |
| Bahan | kuningan atau baja berlapis seng |
| Mur pengunci | M10×1,0 tebal 4 mm, **3 buah** (1 di dalam badan, 2 di luar lengan = cincin pengunci + mur jam) |
| Ring | 2× ring datar M10, 1× ring nilon/PTFE Ø10,5×Ø20×1 mm antara plat baja dan lengan |

Urutan dari dalam ke luar (dicek di skrip): `mur 4 · ring 1,5 · plat baja 3 · nilon 1 · lengan 3 · ring 1,5 · mur 4 · mur jam 4`.
Mur dalam mengunci pipa ke badan; mur luar mengatur gesekan sudut miring.

**Alternatif siap pakai: cable gland logam PG9 / M16×1,5** (badan gland = bos, mur gland = cincin pengunci + penjepit
kabel). Lubang pivot harus Ø16,2 mm: ubah `RIGHT_BOSS_HOLE = 16.2`. Kabel Ø4–8 mm.

**Peringatan kabel:** lubang 6,7 mm tidak bisa dilewati konektor header 8-pin. Lewatkan kabel tanpa konektor, lalu
crimp/solder setelah menembus, atau pakai konektor sempit (≤ 6 mm).

Kata kunci pencarian: *pipa ulir M10 lampu*, *hollow threaded rod M10x1*, *lamp pipe nipple M10*, *cable gland metal PG9*.
Referensi: [pipa ulir M10×1 berongga](https://www.mc-fact.eu/en/shop/lighting/lamp-threaded-nipple-m10-20mm/),
[PG9 / M16×1,5, lubang 15,5–16,3 mm](https://www.metalcablegland.com/metric-cable-gland/m16-metal-cable-gland/).
Stok marketplace lokal belum diperiksa.

## Sisi KIRI: baut biasa + kunci sudut

* Poros: baut **M6×25**, kepala di dalam badan (+ ring), ring nilon 1 mm, mur **nyloc M6** di luar lengan.
* Kunci sudut: baut **M5×20**, kepala di dalam, melewati **slot busur ±45°** di lengan `S3`, dikencangkan dengan
  **mur kupu-kupu M5**.

## Perangkat keras lain

| Untuk | Barang |
|---|---|
| Plat sisi ke sirip A1 (2 × 4) | 8× M3×10 + 8× mur nyloc M3 |
| PCB di lantai wadah | 4× standoff M3 **female-female 15 mm** + 4× M3×6 (dari bawah) + 4× M3×5 (atas) |
| Papan kamera SC3336 | standoff/baut M2 sesuai pola lubang yang Anda ukur |
| Tutup belakang `A2` | 4× rivet nut M3 di flens `A1` + 4× M3×6 |
| Kotak plafon | 4× rivet nut M3 + 4× M3×6 (tutup `B2`); 4× rivet nut M3 (plat port nanti); 4× rivet nut M4 + 4× M4×10 (lengan); grommet karet untuk lubang Ø10 |
| Plafon | 4× angkur M6 sesuai jenis plafon (lubang Ø6,5 di telinga `B2`) |
| Jendela RF | double-tape tipis / VHB untuk `A3` |

## Yang HARUS diperiksa sebelum memotong logam

1. **Antena WiFi/ESP-NOW.** Wadah aluminium meredam sinyal ESP32. Ada **jendela RF** 32 × 59 mm di dinding atas (di atas
   seluruh papan ESP32), ditutup akrilik `A3`. Dari diagram pin DevKitC-1, antena ada di ujung pin 3V3/RST (ujung depan
   di susunan ini). Ukur RSSI/packet loss antar-node **sebelum dan sesudah** casing ditutup.
2. **Lubang lensa dan baut SC3336**: lihat bagian di atas, harus diukur dari papan asli Anda.
3. **Dimensi asumsi lain**: kedalaman rongga kamera 15 mm, tinggi komponen di atas PCB 22 mm (ESP32 + heatsink).
4. **Rivet nut**: diameter lubang bergantung merek. Tanya toko atau ganti dengan baut + mur.
5. Uji dulu di kertas (PDF 1:1) lalu potongan kecil di MDF/akrilik sebelum memotong aluminium dan baja.

## Cetak 1:1 di kertas A4 (mock-up)

* Cetak **`out/cetak_A4_1to1.pdf` dengan "Ukuran sebenarnya / 100 %"**, bukan "Sesuaikan halaman". Tiap halaman punya
  penggaris 100 mm untuk dicek.
* Hal 1: `A1`. Hal 2–3: bagian kecil (beberapa per lembar). Hal 4 (landscape): `B1`. Tidak ada bagian yang dibelah.
* Tanda `+` merah = pusat lubang (tusuk dengan jarum). Garis hitam potong, garis putus biru lipat.
* Kertas tidak memodelkan tebal logam dan radius tekukan: untuk cek bentuk dan posisi lubang, bukan toleransi.

## Yang sudah diverifikasi

* 27 pemeriksaan otomatis lulus (lihat `out/parts_table.md`): PCB muat di bawah dinding atas, mur poros tidak menabrak PCB
  atau sirip, badan bisa berputar di bawah kaki lengan (sisa 5,1 mm), tumpukan baut cocok, kabel mendarat di grommet,
  semua lubang ≥ 3 mm dari zona tekuk, dll.
* Semua DXF dibaca ulang dan diaudit tanpa temuan; PDF cetak diukur: skala 100,2 mm per 100 mm (selisih = tebal garis),
  jarak isi ke tepi kertas ≥ 6,8 mm.
* **Belum**: simulasi lipatan di CAD dan percobaan fisik. Minta toko melakukan tinjauan DFM atas pola datar.
