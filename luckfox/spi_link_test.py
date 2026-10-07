#!/usr/bin/env python3
"""LuckFox -> ESP32 SPI link/load test, no camera or encoder needed.

Uses the same wire protocol as spi_sender.py (magic/header/4000-byte chunks)
to push one status message and N synthetic "video" frames, rotating over the
3 lane streams, so the whole chain (SPI -> WiFi relay -> W5500 -> RPi4
video_listener) can be exercised on its own.

Usage (on the LuckFox, needs SPI0 M0 enabled, see spi_sender.py):
    python3 spi_link_test.py [frames=10] [frame_bytes=8000] [speed_hz=4000000] [interval_s=0.3]
"""
import spidev, struct, sys, time
MAGIC=0x52415046; HDR="<IBBHI"; CH=4000; MAXP=11
n_frames=int(sys.argv[1]) if len(sys.argv)>1 else 10
size=int(sys.argv[2]) if len(sys.argv)>2 else 8000
spi=spidev.SpiDev(); spi.open(0,0); spi.max_speed_hz=int(sys.argv[3]) if len(sys.argv)>3 else 4000000; spi.mode=0
def chunk(b): spi.writebytes2(b+bytes(CH-len(b)))
def msg(t,s,seq,p):
    chunk(struct.pack(HDR,MAGIC,t,s,seq,len(p)))
    for o in range(0,len(p),CH): chunk(p[o:o+CH])
msg(1,0,0,struct.pack("<B",1)+b"LFTEST".ljust(MAXP+1,b"\0"))
print("status sent")
for seq in range(n_frames):
    stream=seq%3
    p=bytes((seq*31+stream*7+i)&0xFF for i in range(size))
    t=time.time(); msg(0,stream,seq,p); time.sleep(float(sys.argv[4]) if len(sys.argv)>4 else 0.3)
    print("frame",seq,"stream",stream,size,"B",round(time.time()-t,3),"s")
spi.close()
