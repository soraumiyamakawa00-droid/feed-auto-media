#!/usr/bin/env python3
"""ロウの効果音を合成して WAV で書き出す。

    python3 character/pixel/sound.py             # 全部を書き出す
    python3 character/pixel/sound.py bark        # 1つだけ
    python3 character/pixel/sound.py bark --play # 書き出して再生（afplay/aplay があれば）
    python3 character/pixel/sound.py --list

矩形波・三角波・ノイズだけで作るチップチューン風。外部ライブラリは使いません。
"""
import argparse
import math
import pathlib
import random
import shutil
import struct
import subprocess
import wave

HERE = pathlib.Path(__file__).resolve().parent
RATE = 22050


def tone(shape, f0, f1, seconds, volume=0.5, attack=0.004, release=0.35):
    """f0 から f1 へ滑らせながら 1 音鳴らす。release は後半の減衰の割合。"""
    total = int(RATE * seconds)
    out = [0.0] * total
    phase = 0.0
    for i in range(total):
        pos = i / total
        freq = f0 + (f1 - f0) * pos
        phase += freq / RATE
        phase %= 1.0
        if shape == "square":
            value = 1.0 if phase < 0.5 else -1.0
        elif shape == "pulse":
            # 直流が乗るとクリックノイズになるので、平均が 0 になる高さにする
            value = 0.75 if phase < 0.25 else -0.25
        elif shape == "triangle":
            value = 4 * abs(phase - 0.5) - 1
        else:                                   # noise
            value = random.uniform(-1, 1)
        env = min(1.0, i / max(1, int(RATE * attack)))
        if pos > 1 - release:
            env *= (1 - pos) / release
        out[i] = value * volume * env
    return out


def silence(seconds):
    return [0.0] * int(RATE * seconds)


def mix(*layers):
    length = max(len(layer) for layer in layers)
    out = [0.0] * length
    for layer in layers:
        for i, value in enumerate(layer):
            out[i] += value
    return out


def chain(*parts):
    out = []
    for part in parts:
        out.extend(part)
    return out


SOUNDS = {
    # 吠える：短く2回。ひと吠えめを高く、ふた吠えめを低く長く
    "bark": lambda: chain(
        mix(tone("square", 620, 260, 0.07, 0.45),
            tone("noise", 0, 0, 0.07, 0.06)),
        silence(0.035),
        mix(tone("square", 500, 170, 0.11, 0.42, release=0.5),
            tone("noise", 0, 0, 0.11, 0.05)),
    ),
    # 跳ねる：上がって、てっぺんで軽く鳴らす
    "hop": lambda: chain(
        tone("pulse", 380, 880, 0.10, 0.46),
        tone("pulse", 1170, 1170, 0.07, 0.36, release=0.7),
    ),
    # エラー：低い2音が下りる
    "error": lambda: chain(
        mix(tone("square", 233, 233, 0.11, 0.34),
            tone("noise", 0, 0, 0.11, 0.05)),
        silence(0.02),
        mix(tone("square", 165, 148, 0.22, 0.34, release=0.5),
            tone("noise", 0, 0, 0.22, 0.04)),
    ),
    # 寝息：低くゆっくり、吸って吐く
    "sleep": lambda: chain(
        tone("triangle", 108, 128, 0.55, 0.16, attack=0.2, release=0.45),
        silence(0.12),
        tone("triangle", 120, 96, 0.60, 0.12, attack=0.25, release=0.5),
    ),
    # 起動：C-E-G の3音
    "wake": lambda: chain(
        tone("triangle", 523, 523, 0.075, 0.32, release=0.45),
        tone("triangle", 659, 659, 0.075, 0.32, release=0.45),
        tone("triangle", 784, 784, 0.16, 0.34, release=0.6),
    ),
}


# 音ごとの狙いの大きさ。寝息などは控えめにしたいので下げる。
LEVELS = {"sleep": 0.45, "whine": 0.62, "wake": 0.80}


def write_wav(path, samples, level=None):
    """ピークを level に合わせて書き出す。

    合成したままだと最大でも 5 割ほどの音量にしかならず、
    ブラウザや端末のスピーカーでは「鳴っていない」ように聞こえます。
    """
    if level is None:
        stem = pathlib.Path(path).stem
        level = next((v for k, v in LEVELS.items() if k in stem), 0.92)
    peak = max(abs(v) for v in samples) or 1.0
    gain = level / peak
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, v * gain)) * 32767)) for v in samples)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(RATE)
        fh.writeframes(frames)


def play(path):
    for player in (["afplay"], ["aplay", "-q"], ["paplay"], ["play", "-q"]):
        if shutil.which(player[0]):
            subprocess.run(player + [str(path)], check=False)
            return True
    print("再生コマンドが見つかりません（afplay / aplay / paplay / play）")
    return False


def shown(path):
    """リポジトリの外に書き出したときも壊れないようにする。"""
    try:
        return path.relative_to(pathlib.Path.cwd())
    except ValueError:
        return path


def main():
    ap = argparse.ArgumentParser(description="ロウの効果音を書き出す")
    ap.add_argument("name", nargs="?", help="書き出す音（省略時は全部）")
    ap.add_argument("--play", action="store_true", help="書き出したあと再生する")
    ap.add_argument("-o", "--out", default=str(HERE / "sound"))
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        print(" ".join(SOUNDS))
        return
    if args.name and args.name not in SOUNDS:
        raise SystemExit(f"{args.name!r} はありません: {' '.join(SOUNDS)}")

    random.seed(20)                              # ノイズを毎回同じにする
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ([args.name] if args.name else SOUNDS):
        samples = SOUNDS[name]()
        path = out_dir / f"rou_{name}.wav"
        write_wav(path, samples)
        print(f"{shown(path)}  {len(samples) / RATE:.2f}秒")
        if args.play:
            play(path)


if __name__ == "__main__":
    main()
