#!/usr/bin/env python3
"""ロウのアニメーション GIF を書き出す。

    python3 character/pixel/anim.py              # 全部を書き出す
    python3 character/pixel/anim.py idle -s 8    # 1本だけ、倍率を指定
    python3 character/pixel/anim.py --list

GIF は標準ライブラリだけで組み立てています（LZW も自前）。
"""
import argparse
import pathlib
import struct

import render

HERE = pathlib.Path(__file__).resolve().parent

# (元になるグリッド, 表示時間 1/100 秒, 上下のずれ px)
ANIMATIONS = {
    # 待機：たまにまばたきする
    "idle": [("rou", 110), ("rou_half", 4), ("rou_blink", 7), ("rou_half", 4),
             ("rou", 60), ("rou_half", 4), ("rou_blink", 7), ("rou_half", 4)],
    # 投稿した瞬間：ひと吠え
    "bark": [("rou", 16), ("rou_half", 5), ("rou_bark", 9, -1), ("rou_bark", 22),
             ("rou_bark", 9, -1), ("rou", 18)],
    # 投稿成功：跳ねて喜ぶ
    "hop": [("rou_happy", 9), ("rou_happy", 6, -2), ("rou_happy", 6, -4),
            ("rou_happy", 6, -2), ("rou_happy", 12)],
    # キューが空：寝息
    "sleep": [("rou_sleep", 75), ("rou_sleep", 75, 1)],
}


def load_frames(spec):
    grids, offsets, delays = [], [], []
    for item in spec:
        stem, delay = item[0], item[1]
        offsets.append(item[2] if len(item) > 2 else 0)
        delays.append(delay)
        grids.append(render.read_grid(HERE / f"{stem}.txt"))
    return grids, offsets, delays


def build_indexed(grids, offsets, scale):
    """全フレームを同じ画面に置き、パレット番号の並びにする。"""
    width = max(len(g[0]) for g in grids)
    height = max(len(g) for g in grids)
    up, down = max(0, -min(offsets)), max(0, max(offsets))
    height += up + down

    chars = sorted({c for g in grids for row in g for c in row if c != "."})
    order = ["."] + chars                      # 0 番を透過にする
    index_of = {c: i for i, c in enumerate(order)}

    frames = []
    for grid, offset in zip(grids, offsets):
        canvas = [[0] * width for _ in range(height)]
        for y, row in enumerate(grid):
            ty = y + up + offset
            if not 0 <= ty < height:
                continue
            for x, ch in enumerate(row):
                if ch != ".":
                    canvas[ty][x] = index_of[ch]
        scaled = []
        for row in canvas:
            wide = [v for v in row for _ in range(scale)]
            scaled.extend([wide] * scale)
        frames.append([v for row in scaled for v in row])
    return frames, width * scale, height * scale, order


def lzw(indices, min_code_size):
    clear, end = 1 << min_code_size, (1 << min_code_size) + 1
    code_size = min_code_size + 1
    table = {(i,): i for i in range(clear)}
    next_code = end + 1
    bits = nbits = 0
    out = bytearray()

    def emit(code, size):
        nonlocal bits, nbits
        bits |= code << nbits
        nbits += size
        while nbits >= 8:
            out.append(bits & 0xFF)
            bits >>= 8
            nbits -= 8

    emit(clear, code_size)
    prefix = ()
    for value in indices:
        candidate = prefix + (value,)
        if candidate in table:
            prefix = candidate
            continue
        emit(table[prefix], code_size)
        if next_code < 4096:
            table[candidate] = next_code
            next_code += 1
            if next_code > (1 << code_size) and code_size < 12:
                code_size += 1
        else:
            emit(clear, code_size)
            table = {(i,): i for i in range(clear)}
            next_code = end + 1
            code_size = min_code_size + 1
        prefix = (value,)
    if prefix:
        emit(table[prefix], code_size)
    emit(end, code_size)
    if nbits:
        out.append(bits & 0xFF)
    return bytes(out)


def blocks(data):
    out = bytearray()
    for i in range(0, len(data), 255):
        chunk = data[i:i + 255]
        out.append(len(chunk))
        out += chunk
    out.append(0)
    return bytes(out)


def write_gif(path, frames, width, height, order, table, delays):
    size_bits = max(1, (len(order) - 1).bit_length())
    table_size = 1 << size_bits
    palette = bytearray()
    for ch in order:
        rgba = table[ch]
        palette += bytes(rgba[:3]) if rgba[3] else b"\x00\x00\x00"
    palette += b"\x00" * 3 * (table_size - len(order))

    out = bytearray(b"GIF89a")
    out += struct.pack("<HHBBB", width, height, 0xF0 | (size_bits - 1), 0, 0)
    out += palette
    out += b"\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00"   # 無限ループ
    min_code_size = max(2, size_bits)
    for pixels, delay in zip(frames, delays):
        out += b"\x21\xF9\x04\x09" + struct.pack("<H", delay) + b"\x00\x00"
        out += b"\x2C" + struct.pack("<HHHHB", 0, 0, width, height, 0)
        out.append(min_code_size)
        out += blocks(lzw(pixels, min_code_size))
    out += b"\x3B"
    pathlib.Path(path).write_bytes(bytes(out))


def main():
    ap = argparse.ArgumentParser(description="ロウのアニメーション GIF を書き出す")
    ap.add_argument("name", nargs="?", help="書き出すアニメーション（省略時は全部）")
    ap.add_argument("-s", "--scale", type=int, default=6, help="拡大率（既定 6）")
    ap.add_argument("-o", "--out", default=str(HERE / "anim"), help="出力先")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        print(" ".join(ANIMATIONS))
        return
    if args.name and args.name not in ANIMATIONS:
        raise SystemExit(f"{args.name!r} はありません: {' '.join(ANIMATIONS)}")

    table = render.load_palette(HERE / "palette.json")
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in ([args.name] if args.name else ANIMATIONS):
        grids, offsets, delays = load_frames(ANIMATIONS[name])
        frames, width, height, order = build_indexed(grids, offsets, args.scale)
        path = out_dir / f"rou_{name}.gif"
        write_gif(path, frames, width, height, order, table, delays)
        total = sum(delays) / 100
        print(f"{path.relative_to(HERE.parent.parent)}  {width}x{height}  "
              f"{len(frames)}コマ {total:.1f}秒")


if __name__ == "__main__":
    main()
