"""Draw the app icon (blue rounded square, white house, bell dot) as PNGs – no dependencies.

Run once:  python3 scripts/make_icons.py
"""

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "hlidac" / "web" / "static"
BLUE, WHITE, AMBER = (31, 95, 191), (255, 255, 255), (255, 183, 3)
SS = 4  # supersampling for smooth edges


def inside(x: float, y: float, rounded: bool) -> tuple[int, int, int] | None:
    """Colour at a point in the unit square, or None for transparent."""
    r = 0.22 if rounded else 0.0
    cx, cy = min(max(x, r), 1 - r), min(max(y, r), 1 - r)
    if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
        return None
    # bell dot (top right)
    if (x - 0.74) ** 2 + (y - 0.27) ** 2 < 0.075 ** 2:
        return AMBER
    # roof: triangle apex (0.5, 0.2), base y = 0.48 from x 0.18..0.82
    if 0.2 <= y <= 0.48 and abs(x - 0.5) <= (y - 0.2) / 0.28 * 0.32:
        return WHITE
    # body with a door
    if 0.47 <= y <= 0.8 and 0.27 <= x <= 0.73:
        if 0.43 <= x <= 0.57 and y >= 0.6:
            return BLUE
        return WHITE
    return BLUE


def png(size: int, rounded: bool) -> bytes:
    rows = []
    for py in range(size):
        row = bytearray([0])
        for px in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(SS):
                for sx in range(SS):
                    c = inside((px + (sx + .5) / SS) / size, (py + (sy + .5) / SS) / size, rounded)
                    if c:
                        acc[0] += c[0]; acc[1] += c[1]; acc[2] += c[2]; acc[3] += 255
            n = SS * SS
            a = acc[3] // n
            if a:
                k = acc[3] // 255
                row += bytes([acc[0] // k, acc[1] // k, acc[2] // k, a])
            else:
                row += bytes(4)
        rows.append(bytes(row))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    # iOS adds its own rounded mask, so the apple-touch icon is a full square.
    for name, size, rounded in (("icon-192.png", 192, True), ("icon-512.png", 512, False),
                                ("icon-180.png", 180, False)):
        (OUT / name).write_bytes(png(size, rounded))
        print("wrote", OUT / name)
