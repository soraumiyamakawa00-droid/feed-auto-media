#!/usr/bin/env python3
"""ロウを正方形のアイコンとして書き出す。

    python3 character/pixel/icon.py                  # 512/256/128/64 を生成
    python3 character/pixel/icon.py -s 512 --bg none # 透過で1枚だけ
    python3 character/pixel/icon.py happy            # 表情を指定

スプライトは必ず整数倍で拡大するので、どのサイズでもドットがにじみません。
"""
import argparse
import pathlib

import render

HERE = pathlib.Path(__file__).resolve().parent
BACKGROUNDS = {
    "cream": (243, 230, 204, 255),   # パレットの C
    "white": (255, 255, 255, 255),
    "navy": (22, 33, 62, 255),       # パレットの #
    "none": (0, 0, 0, 0),
}


def trim(grid):
    cols = [x for x in range(len(grid[0])) if any(row[x] != "." for row in grid)]
    rows = [y for y, row in enumerate(grid) if row.strip(".")]
    return [row[cols[0]:cols[-1] + 1] for row in grid[rows[0]:rows[-1] + 1]]


def head_center(grid):
    """横方向の中心は頭で取る。しっぽまで含めると顔が左に寄る。"""
    upper = grid[:max(1, int(len(grid) * 0.6))]
    cols = [x for x in range(len(grid[0])) if any(row[x] != "." for row in upper)]
    return (cols[0] + cols[-1] + 1) / 2


def compose(grid, table, size, bg, margin=0.08):
    """スプライトを整数倍して、頭が中央に来るように置く。"""
    h, w = len(grid), len(grid[0])
    scale = max(1, int(size * (1 - 2 * margin) / max(w, h)))
    draw_h = h * scale
    left = int(size / 2 - head_center(grid) * scale)
    top = (size - draw_h) // 2
    px = bytearray(bytes(bg) * size * size)
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            color = table[ch]
            if color[3] == 0:
                continue
            for dy in range(scale):
                oy = top + y * scale + dy
                if not 0 <= oy < size:
                    continue
                start = (oy * size + left + x * scale) * 4
                px[start:start + 4 * scale] = bytes(color) * scale
    return bytes(px), scale


def main():
    ap = argparse.ArgumentParser(description="ロウのアイコンを書き出す")
    ap.add_argument("expression", nargs="?", default="normal")
    ap.add_argument("-s", "--size", type=int, action="append",
                    help="書き出すサイズ（複数可、既定は 512 256 128 64）")
    ap.add_argument("--bg", default="cream", choices=sorted(BACKGROUNDS), help="背景")
    ap.add_argument("-o", "--out", default=str(HERE / "icons"), help="出力先")
    args = ap.parse_args()

    stem = "rou" if args.expression == "normal" else f"rou_{args.expression}"
    source = HERE / f"{stem}.txt"
    if not source.exists():
        raise SystemExit(f"{source.name} がありません")

    table = render.load_palette(HERE / "palette.json")
    grid = trim(render.read_grid(source))
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.bg == "cream" else f"_{args.bg}"

    for size in args.size or [512, 256, 128, 64]:
        pixels, scale = compose(grid, table, size, BACKGROUNDS[args.bg])
        path = out / f"{stem}_icon_{size}{suffix}.png"
        render.write_png(path, pixels, size, size)
        print(f"{path.relative_to(HERE.parent.parent)}  {size}x{size}  (x{scale})")


if __name__ == "__main__":
    main()
