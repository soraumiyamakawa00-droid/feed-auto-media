#!/usr/bin/env python3
"""ドット絵のテキストグリッドを PNG に変換する。

使い方:
    python3 character/pixel/render.py                 # 全 *.txt を等倍と x8 で書き出し
    python3 character/pixel/render.py mascot.txt -s 16

グリッドは1文字=1ピクセル。対応表は palette.json。
"""
import argparse
import json
import pathlib
import zlib
import struct

HERE = pathlib.Path(__file__).resolve().parent


def load_palette(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    table = {}
    for key, value in raw.items():
        if key.startswith("_"):
            continue
        if value is None:
            table[key] = (0, 0, 0, 0)
        else:
            h = value.lstrip("#")
            table[key] = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
    return table


def read_grid(path):
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    width = max(len(line) for line in lines)
    return [line.ljust(width, ".") for line in lines]


def write_png(path, pixels, width, height):
    """RGBA のバイト列を PNG として書き出す（依存ライブラリなし）。"""
    raw = b"".join(b"\x00" + pixels[y * width * 4:(y + 1) * width * 4] for y in range(height))

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def render(grid, table, scale):
    height, width = len(grid), len(grid[0])
    out = bytearray()
    for row in grid:
        line = bytearray()
        for ch in row:
            if ch not in table:
                raise SystemExit(f"palette.json に定義のない文字: {ch!r}")
            line += bytes(table[ch]) * scale
        out += line * scale
    return bytes(out), width * scale, height * scale


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("grids", nargs="*", help="変換するグリッド（省略時はディレクトリ内の全 *.txt）")
    ap.add_argument("-s", "--scale", type=int, action="append", help="拡大率（複数指定可、既定は 1 と 8）")
    args = ap.parse_args()

    table = load_palette(HERE / "palette.json")
    scales = args.scale or [1, 8]
    targets = [pathlib.Path(g) for g in args.grids] or sorted(HERE.glob("*.txt"))

    for target in targets:
        if not target.is_absolute() and not target.exists():
            target = HERE / target
        grid = read_grid(target)
        for scale in scales:
            pixels, width, height = render(grid, table, scale)
            suffix = "" if scale == 1 else f"_x{scale}"
            out = target.with_name(f"{target.stem}{suffix}.png")
            write_png(out, pixels, width, height)
            try:
                shown = out.relative_to(pathlib.Path.cwd())
            except ValueError:
                shown = out
            print(f"{shown}  {width}x{height}")


if __name__ == "__main__":
    main()
