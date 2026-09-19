#!/usr/bin/env python3
"""ロウをターミナルに表示する。

    python3 character/pixel/show.py              # 既定の顔
    python3 character/pixel/show.py happy        # 表情を指定
    python3 character/pixel/show.py --anim idle  # 動かす（Ctrl-C で止める）
    python3 character/pixel/show.py --list       # 表情の一覧

半角1マスに縦2ピクセルを詰めるので、ドットがほぼ正方形に見えます。
NO_COLOR が設定されているか、出力先が端末でないときは何も表示しません。
"""
import argparse
import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
UPPER, LOWER, FULL = "▀", "▄", " "


def load_palette():
    raw = json.loads((HERE / "palette.json").read_text(encoding="utf-8"))
    out = {}
    for key, value in raw.items():
        if key.startswith("_"):
            continue
        out[key] = None if value is None else tuple(
            int(value.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return out


def expressions():
    names = {}
    for path in sorted(HERE.glob("rou*.txt")):
        if path.stem.startswith("rou_front") or path.stem in ("rou_quad", "rou_head", "rou_chibi"):
            continue
        names["normal" if path.stem == "rou" else path.stem[len("rou_"):]] = path
    return names


def trim(grid):
    cols = [x for x in range(len(grid[0])) if any(row[x] != "." for row in grid)]
    rows = [y for y, row in enumerate(grid) if row.strip(".")]
    if not cols or not rows:
        return grid
    return [row[cols[0]:cols[-1] + 1] for row in grid[rows[0]:rows[-1] + 1]]


def render(grid, table, indent=2):
    lines = []
    pad = " " * indent
    for y in range(0, len(grid), 2):
        top = grid[y]
        bottom = grid[y + 1] if y + 1 < len(grid) else "." * len(top)
        cells = []
        for x in range(len(top)):
            up = table.get(top[x])
            dn = table.get(bottom[x] if x < len(bottom) else ".")
            if up is None and dn is None:
                cells.append("\x1b[0m ")
            elif dn is None:
                cells.append("\x1b[0m\x1b[38;2;%d;%d;%dm%s" % (*up, UPPER))
            elif up is None:
                cells.append("\x1b[0m\x1b[38;2;%d;%d;%dm%s" % (*dn, LOWER))
            else:
                cells.append("\x1b[38;2;%d;%d;%dm\x1b[48;2;%d;%d;%dm%s" % (*up, *dn, UPPER))
        lines.append(pad + "".join(cells) + "\x1b[0m")
    return "\n".join(lines)


def play(name):
    """anim.py のコマ割りをそのまま端末で再生する。"""
    sys.path.insert(0, str(HERE))
    import anim

    if name not in anim.ANIMATIONS:
        sys.exit(f"{name!r} はありません: {' '.join(anim.ANIMATIONS)}")
    table = load_palette()
    steps = []
    for item in anim.ANIMATIONS[name]:
        grid = [line for line in (HERE / f"{item[0]}.txt").read_text(
            encoding="utf-8").splitlines() if line]
        steps.append((render(grid, table), item[1] / 100))
    lines = steps[0][0].count("\n") + 1
    print("\x1b[?25l", end="")                      # カーソルを隠す
    try:
        first = True
        while True:
            for art, delay in steps:
                if not first:
                    print(f"\x1b[{lines}A", end="")
                print(art)
                first = False
                time.sleep(delay)
    except KeyboardInterrupt:
        pass
    finally:
        print("\x1b[?25h", end="", flush=True)      # カーソルを戻す


def main():
    ap = argparse.ArgumentParser(description="ロウをターミナルに表示する")
    ap.add_argument("expression", nargs="?", default="normal")
    ap.add_argument("--list", action="store_true", help="表情の一覧を出す")
    ap.add_argument("--anim", help="アニメーションを再生する（Ctrl-C で止める）")
    ap.add_argument("--force", action="store_true", help="端末でなくても表示する")
    args = ap.parse_args()

    known = expressions()
    if args.list:
        print(" ".join(sorted(known)))
        return
    if os.environ.get("NO_COLOR") or not (args.force or sys.stdout.isatty()):
        return
    if args.anim:
        play(args.anim)
        return
    path = known.get(args.expression)
    if path is None:
        sys.exit(f"表情 {args.expression!r} はありません: {' '.join(sorted(known))}")
    grid = trim([line for line in path.read_text(encoding="utf-8").splitlines() if line])
    print(render(grid, load_palette()))


if __name__ == "__main__":
    main()
