"""Generate brand assets (icon.png / logo.png) with no third-party deps.

Pure-python PNG writer + a 4x supersampled renderer so the edges are
antialiased. Design: Jellyfin's purple->blue gradient on a rounded square,
with a white microphone glyph for the voice half of "Voice Jellyfin".
"""
import math
import struct
import zlib
from pathlib import Path

SS = 4  # supersample factor

# Jellyfin brand gradient endpoints
C0 = (170, 92, 195)   # purple
C1 = (0, 164, 220)    # blue


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _rounded_square(x, y, size, radius):
    """Signed test: is (x, y) inside a rounded square of `size` with corner
    radius `radius`? Coordinates are relative to the square's origin."""
    cx = min(max(x, radius), size - radius)
    cy = min(max(y, radius), size - radius)
    dx, dy = x - cx, y - cy
    if dx == 0 and dy == 0:
        return True
    return dx * dx + dy * dy <= radius * radius


def _mic(x, y, size):
    """White microphone glyph: capsule head, arc, and stand."""
    s = size
    cx = s / 2

    # Capsule head — the two end-circle centres must differ or it renders
    # as a plain circle instead of a capsule.
    head_w, head_top, head_bot = s * 0.115, s * 0.17, s * 0.60
    if abs(x - cx) <= head_w:
        if head_top + head_w <= y <= head_bot - head_w:
            return True
    for cy_ in (head_top + head_w, head_bot - head_w):
        if (x - cx) ** 2 + (y - cy_) ** 2 <= head_w * head_w:
            return True

    # Arc under the head
    arc_r, arc_t = s * 0.235, s * 0.038
    d = math.hypot(x - cx, y - (head_bot - head_w))
    if abs(d - arc_r) <= arc_t and y >= head_bot - head_w:
        return True

    # Stand
    stem_y0, stem_y1 = head_bot - head_w + arc_r, s * 0.845
    if abs(x - cx) <= arc_t and stem_y0 <= y <= stem_y1:
        return True
    if abs(y - stem_y1) <= arc_t and abs(x - cx) <= s * 0.125:
        return True
    return False


def render(size):
    """Return RGBA bytes for one `size` x `size` image."""
    big = size * SS
    radius = big * 0.22
    rows = []
    for py in range(size):
        row = bytearray()
        for px in range(size):
            r = g = b = a = 0
            for sy in range(SS):
                for sx in range(SS):
                    X = px * SS + sx + 0.5
                    Y = py * SS + sy + 0.5
                    if not _rounded_square(X, Y, big, radius):
                        continue
                    t = (X + Y) / (2 * big)          # diagonal gradient
                    cr, cg, cb = _lerp(C0, C1, t)
                    if _mic(X, Y, big):
                        cr = cg = cb = 255
                    r += cr; g += cg; b += cb; a += 255
            n = SS * SS
            if a:
                # average colour over covered samples only, so edge pixels
                # keep their hue instead of darkening toward black
                cov = a // 255
                row += bytes((r // cov, g // cov, b // cov, a // n))
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    return rows


def write_png(path, rows, size):
    raw = b"".join(b"\0" + r for r in rows)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    Path(path).write_bytes(png)
    return len(png)


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, size in (("icon.png", 256), ("icon@2x.png", 512),
                       ("logo.png", 256), ("logo@2x.png", 512)):
        rows = render(size)
        n = write_png(out / name, rows, size)
        print(f"{name}: {size}x{size}, {n} bytes")
