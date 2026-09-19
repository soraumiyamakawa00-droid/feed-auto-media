#!/usr/bin/env python3
"""ロウの声を合成する。

    python3 character/pixel/voice.py                    # 鳴き声を全部書き出す
    python3 character/pixel/voice.py howl --play        # 遠吠えを鳴らす
    python3 character/pixel/voice.py --say とうこうしたよ  # しゃべらせる
    python3 character/pixel/voice.py --list

母音は **フォルマント合成** で作っています。声帯のかわりにのこぎり波を鳴らし、
口の共鳴にあたる帯域を2つ持ち上げると、あ・い・う・え・お に聞こえます。
外部ライブラリは使いません。
"""
import argparse
import math
import pathlib
import random

import sound

HERE = pathlib.Path(__file__).resolve().parent
RATE = sound.RATE

# 母音ごとの F1 / F2（第1・第2フォルマント）と口の開き（音量）
VOWELS = {
    "a": (780, 1250, 1.00),
    "i": (300, 2300, 0.80),
    "u": (360, 850, 0.75),
    "e": (520, 1900, 0.88),
    "o": (500, 940, 0.92),
    "n": (280, 1100, 0.55),      # 鼻に抜ける音
    "_": (0, 0, 0.0),            # 無音
}

KANA_ROWS = {
    "a": "あかさたなはまやらわがざだばぱぁゃゎ",
    "i": "いきしちにひみりぎじぢびぴぃ",
    "u": "うくすつぬふむゆるぐずづぶぷぅゅっ",
    "e": "えけせてねへめれげぜでべぺぇ",
    "o": "おこそとのほもよろをごぞどぼぽぉょ",
    "n": "ん",
}
VOWEL_OF = {ch: v for v, chars in KANA_ROWS.items() for ch in chars}


def resonator(samples, freq, bandwidth=90):
    """2極の共鳴フィルタ。freq のまわりだけを持ち上げる。"""
    if freq <= 0:
        return [0.0] * len(samples)
    r = math.exp(-math.pi * bandwidth / RATE)
    b1 = -2 * r * math.cos(2 * math.pi * freq / RATE)
    b2 = r * r
    gain = (1 - r) * math.sqrt(1 - 2 * r * math.cos(2 * 2 * math.pi * freq / RATE) + r * r)
    out = [0.0] * len(samples)
    y1 = y2 = 0.0
    for i, x in enumerate(samples):
        y = gain * x - b1 * y1 - b2 * y2
        out[i] = y
        y2, y1 = y1, y
    return out


def glottis(seconds, f0, f1, breath=0.03, width=0.16):
    """声帯のかわり。細いパルス列に少しだけ息（ノイズ）を混ぜる。

    のこぎり波だと低い倍音が強すぎて、第2フォルマントが埋もれて母音が読めません。
    パルスを細くするほど高い倍音が増えて、母音がはっきりします。
    """
    total = int(RATE * seconds)
    out = [0.0] * total
    phase = 0.0
    for i in range(total):
        pos = i / max(1, total)
        freq = f0 + (f1 - f0) * pos
        phase = (phase + freq / RATE) % 1.0
        if phase < width:
            pulse = 0.5 - 0.5 * math.cos(2 * math.pi * phase / width)
        else:
            pulse = 0.0
        out[i] = (pulse - width / 2) * (1 - breath) + random.uniform(-1, 1) * breath
    return out


# 声質。(声の高さの倍率, フォルマントの倍率, 息の量, 第2フォルマントの強さ)
VOICES = {
    "normal": (1.00, 1.00, 0.03, 1.5),
    "deep":   (0.62, 0.86, 0.04, 1.3),   # 体の大きい狼
    "puppy":  (1.45, 1.22, 0.03, 1.8),   # 子犬
    "husky":  (0.88, 0.98, 0.16, 1.6),   # かすれ声
    "flat":   (0.80, 0.94, 0.02, 1.2),   # ぶっきらぼう
}
VOICE = "normal"


def mora(vowel, seconds, f0, f1, attack=0.012, release=0.25, opening=None):
    """母音を1つ鳴らす。opening を渡すと口の開き方を途中で変えられる。"""
    pitch_k, formant_k, breath, f2_gain = VOICES[VOICE]
    f0, f1 = f0 * pitch_k, f1 * pitch_k
    src = glottis(seconds, f0, f1, breath=breath)
    total = len(src)
    a1, a2, level = VOWELS[vowel]
    a1, a2 = a1 * formant_k, a2 * formant_k
    if level == 0:
        return [0.0] * total
    voiced = resonator(src, a1, 80)
    upper = resonator(src, a2, 130)
    third = resonator(src, 2750 * formant_k, 200)
    out = [0.0] * total
    attack_n = max(1, int(RATE * attack))
    for i in range(total):
        pos = i / total
        env = min(1.0, i / attack_n)
        if pos > 1 - release:
            env *= (1 - pos) / release
        if opening:
            env *= opening(pos)
        out[i] = (voiced[i] + upper[i] * f2_gain + third[i] * 0.35) * level * env
    return out


def glide(v0, v1, seconds, f0, f1, steps=7, **kw):
    """母音から母音へ滑らかに移る。短い区間に割って母音を混ぜる。"""
    out = []
    for k in range(steps):
        t = k / max(1, steps - 1)
        a1 = VOWELS[v0][0] + (VOWELS[v1][0] - VOWELS[v0][0]) * t
        a2 = VOWELS[v0][1] + (VOWELS[v1][1] - VOWELS[v0][1]) * t
        level = VOWELS[v0][2] + (VOWELS[v1][2] - VOWELS[v0][2]) * t
        VOWELS["~"] = (a1, a2, level)
        p0 = f0 + (f1 - f0) * (k / steps)
        p1 = f0 + (f1 - f0) * ((k + 1) / steps)
        out.extend(mora("~", seconds / steps, p0, p1,
                        attack=0.004 if k else kw.get("attack", 0.012),
                        release=0.2 if k == steps - 1 else 0.02))
    return out


CALLS = {
    # ワゥ：ウ→ア→ウ と動かすと犬科の吠え方になる
    "bark": lambda: sound.chain(
        glide("u", "a", 0.06, 330, 300),
        glide("a", "u", 0.16, 300, 165),
    ),
    # キャン：高く短く
    "yip": lambda: sound.chain(
        glide("i", "a", 0.05, 520, 470),
        glide("a", "n", 0.13, 470, 330),
    ),
    # アオーーン：遠吠え
    "howl": lambda: sound.chain(
        glide("a", "o", 0.22, 250, 300, steps=9),
        glide("o", "o", 0.75, 300, 288, steps=11),
        glide("o", "n", 0.40, 288, 210, steps=9),
    ),
    # くぅーん：甘える
    "whine": lambda: sound.chain(
        glide("u", "u", 0.30, 380, 440, steps=9),
        glide("u", "n", 0.28, 440, 330, steps=9),
    ),
}


def say(text, base=300):
    """かなの母音をたどってしゃべらせる。子音は作らないので喃語になる。"""
    moras = []
    previous = "a"
    for ch in text:
        if "ァ" <= ch <= "ヶ":                 # カタカナをひらがなに
            ch = chr(ord(ch) - 0x60)
        if ch in "ー〜":
            moras.append((previous, 0.16))
            continue
        if ch in "、。 　,.!?！？":
            moras.append(("_", 0.12))
            continue
        vowel = VOWEL_OF.get(ch)
        if vowel is None:
            continue
        moras.append((vowel, 0.105 if vowel != "n" else 0.14))
        previous = vowel
    if not moras:
        return []
    out = []
    count = len(moras)
    for i, (vowel, seconds) in enumerate(moras):
        pos = i / max(1, count - 1)
        arc = math.sin(math.pi * pos) * 26          # 文の途中を少し高く
        drop = -38 * pos                            # 終わりに向かって下げる
        wobble = random.uniform(-7, 7)
        f0 = base + arc + drop + wobble
        out.extend(mora(vowel, seconds, f0, f0 - 12, release=0.3))
    return out


def shown(path):
    """リポジトリの外に書き出したときも壊れないようにする。"""
    try:
        return path.relative_to(pathlib.Path.cwd())
    except ValueError:
        return path


def main():
    ap = argparse.ArgumentParser(description="ロウの声を合成する")
    ap.add_argument("name", nargs="?", help="鳴き声（省略時は全部）")
    ap.add_argument("--say", help="かなでしゃべらせる")
    ap.add_argument("--play", action="store_true")
    ap.add_argument("-o", "--out", default=str(HERE / "sound"))
    ap.add_argument("--voice", default="normal", choices=sorted(VOICES), help="声質")
    ap.add_argument("--suffix", default="", help="出力ファイル名の後ろに付ける文字")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    global VOICE
    VOICE = args.voice

    if args.list:
        print(" ".join(CALLS))
        return

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    random.seed(7)

    if args.say:
        samples = say(args.say)
        if not samples:
            raise SystemExit("かなが1文字もありません")
        path = out_dir / f"rou_say{args.suffix}.wav"
        sound.write_wav(path, samples)
        print(f"{shown(path)}  {len(samples) / RATE:.2f}秒  「{args.say}」")
        if args.play:
            sound.play(path)
        return

    if args.name and args.name not in CALLS:
        raise SystemExit(f"{args.name!r} はありません: {' '.join(CALLS)}")
    for name in ([args.name] if args.name else CALLS):
        samples = CALLS[name]()
        path = out_dir / f"rou_voice_{name}{args.suffix}.wav"
        sound.write_wav(path, samples)
        print(f"{shown(path)}  {len(samples) / RATE:.2f}秒")
        if args.play:
            sound.play(path)


if __name__ == "__main__":
    main()
