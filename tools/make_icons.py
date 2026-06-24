#!/usr/bin/env python3
"""Generate app icons (no PIL): navy tile + sunrise. Writes icon-192/512 + apple-touch."""
import os, zlib, struct, math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def px(x, y, w, h):
    # background: dark navy
    bg = (15, 21, 32)
    cx, cy, r = w * 0.5, h * 0.42, w * 0.24
    d = math.hypot(x - cx, y - cy)
    horizon = h * 0.66
    # sun (warm orange), soft edge
    if d < r:
        return (232, 138, 46)
    if d < r + w * 0.012:
        t = (d - r) / (w * 0.012)
        return tuple(int(232 + (c - 232) * t) for c in (15,)) and (
            int(232 + (15 - 232) * t), int(138 + (21 - 138) * t), int(46 + (32 - 46) * t))
    # horizon band (slightly lighter navy) below the line
    if y > horizon:
        return (26, 34, 51)
    return bg

def make(size, path):
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter type 0
        for x in range(size):
            r, g, b = px(x, y, size, size)
            raw += bytes((r, g, b, 255))
    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + \
          chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    open(path, "wb").write(png)
    print("wrote", os.path.basename(path), size)

for s, name in [(192, "icon-192.png"), (512, "icon-512.png"), (180, "apple-touch-icon.png")]:
    make(s, os.path.join(ROOT, name))
