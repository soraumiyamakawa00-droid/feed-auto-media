#!/usr/bin/env python3
"""ロウにしゃべらせる（子音つき）。

    python3 character/pixel/speak.py "とうこうしたよ"
    python3 character/pixel/speak.py "えらーになった" --voice flat --play
    python3 character/pixel/speak.py "こんにちは" -o /tmp

母音だけだと喃語にしかなりません。人の言葉に近づける要は次の2つです。

1. **子音そのもの** — 破裂音（か行・た行・ぱ行）は「閉鎖の無音 → 雑音の破裂」、
   摩擦音（さ行・は行）は帯域を絞った雑音、鼻音（な行・ま行）は低く曇った声。
2. **子音から母音への渡り** — 子音は舌や唇の位置で決まり、その位置が
   直後の母音の第2フォルマントの出発点（ローカス）になります。
   唇なら低く、舌先なら中ほど、奥舌なら高いところから母音へ滑らせます。
   この渡りがないと、子音を足しても「聞き取れる言葉」になりません。
"""
import argparse
import math
import pathlib
import random

import sound

RATE = sound.RATE

# 母音：F1 / F2 / F3 / 口の開き
VOWELS = {
    "a": (780, 1250, 2800, 1.00),
    "i": (300, 2300, 3100, 0.78),
    "u": (360, 1150, 2600, 0.74),   # 日本語のウは唇を丸めないので F2 が高め
    "e": (520, 1900, 2750, 0.88),
    "o": (500, 940, 2700, 0.92),
}
NASAL = (280, 1300, 2500, 0.42)

# 子音：種類・有声か・閉鎖の長さ・雑音の中心と長さ・第2フォルマントのローカス
C = {
    "":   ("none",  True,  0.000, None,       0.00, 1450),
    "k":  ("stop",  False, 0.055, (1900, 0.9), 0.022, 1950),
    "g":  ("stop",  True,  0.035, (1700, 0.5), 0.016, 1900),
    "t":  ("stop",  False, 0.055, (3600, 0.9), 0.016, 1750),
    "d":  ("stop",  True,  0.035, (3200, 0.5), 0.012, 1700),
    "p":  ("stop",  False, 0.055, (800, 0.8),  0.014, 750),
    "b":  ("stop",  True,  0.035, (700, 0.5),  0.012, 700),
    "s":  ("fric",  False, 0.000, (5200, 1.0), 0.085, 1750),
    "z":  ("fric",  True,  0.000, (4600, 0.6), 0.055, 1750),
    "sh": ("fric",  False, 0.000, (2600, 1.0), 0.090, 2300),
    "j":  ("affr",  True,  0.030, (2500, 0.7), 0.050, 2300),
    "ch": ("affr",  False, 0.045, (2600, 1.0), 0.060, 2300),
    "ts": ("affr",  False, 0.045, (5000, 1.0), 0.060, 1750),
    "h":  ("fric",  False, 0.000, (1400, 0.5), 0.065, 1450),
    "f":  ("fric",  False, 0.000, (1600, 0.5), 0.070, 900),
    "n":  ("nasal", True,  0.048, None,       0.00, 1700),
    "m":  ("nasal", True,  0.050, None,       0.00, 850),
    "r":  ("tap",   True,  0.016, None,       0.00, 1700),
    "w":  ("glide", True,  0.000, None,       0.00, 700),
    "y":  ("glide", True,  0.000, None,       0.00, 2300),
}

BASE = {"あ": ("", "a"), "い": ("", "i"), "う": ("", "u"), "え": ("", "e"), "お": ("", "o")}
ROWS = [("k", "かきくけこ"), ("g", "がぎぐげご"), ("s", "さすせそ"), ("z", "ざずぜぞ"),
        ("t", "たてと"), ("d", "だでど"), ("n", "なにぬねの"), ("h", "はひへほ"),
        ("b", "ばびぶべぼ"), ("p", "ぱぴぷぺぽ"), ("m", "まみむめも"),
        ("y", "やゆよ"), ("r", "らりるれろ"), ("w", "わ")]
VOWEL_ORDER = {"かきくけこ": "aiueo", "がぎぐげご": "aiueo", "さすせそ": "aueo",
               "ざずぜぞ": "aueo", "たてと": "aeo", "だでど": "aeo",
               "なにぬねの": "aiueo", "はひへほ": "aieo", "ばびぶべぼ": "aiueo",
               "ぱぴぷぺぽ": "aiueo", "まみむめも": "aiueo", "やゆよ": "auo",
               "らりるれろ": "aiueo", "わ": "a"}
KANA = dict(BASE)
for cons, chars in ROWS:
    for ch, vowel in zip(chars, VOWEL_ORDER[chars]):
        KANA[ch] = (cons, vowel)
KANA.update({"し": ("sh", "i"), "ち": ("ch", "i"), "つ": ("ts", "u"), "ふ": ("f", "u"),
             "じ": ("j", "i"), "ぢ": ("j", "i"), "づ": ("z", "u"), "を": ("", "o")})
SMALL = {"ゃ": "a", "ゅ": "u", "ょ": "o", "ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o"}


class Reson:
    """状態を持つ2極共鳴。区間をまたいでも滑らかに繋がる。"""

    def __init__(self):
        self.y1 = self.y2 = 0.0

    def block(self, samples, freq, bandwidth):
        if freq <= 0:
            return [0.0] * len(samples)
        r = math.exp(-math.pi * bandwidth / RATE)
        b1 = -2 * r * math.cos(2 * math.pi * freq / RATE)
        b2 = r * r
        # 直列につなぐので、各段は「共鳴点で概ね等倍」に正規化する。
        # ここを間違えると、段を重ねるたびに音が消えていく。
        gain = 1 + b1 + b2
        out = []
        for x in samples:
            y = gain * x - b1 * self.y1 - b2 * self.y2
            self.y2, self.y1 = self.y1, y
            out.append(y)
        return out


class Cascade:
    """共鳴を直列につなぐ。

    並列にして足し合わせると、フォルマント同士の音量比を手で決めることになり、
    いかにも合成らしいブザー音になります。直列なら比は自然に決まります。
    """

    BANDWIDTHS = (70, 100, 160, 260)

    def __init__(self):
        self.stages = [Reson() for _ in range(4)]

    def block(self, samples, freqs):
        for stage, freq, bw in zip(self.stages, freqs, self.BANDWIDTHS):
            samples = stage.block(samples, freq, bw)
        return samples


def glottal(f0s, jitter=0.014, shimmer=0.045, aspiration=0.012):
    """声帯の波形（の微分）を作る。

    左右対称のパルスだと電子音になります。実際の声帯は
    「ゆっくり開いて、すばやく閉じる」ので、そのかたちを作って微分します
    （微分は唇から音が放射されるときの特性でもあります）。
    ゆらぎ（周期のジッタ・振幅のシマー）も人の声らしさに効きます。
    """
    n = len(f0s)
    flow = [0.0] * n
    i = 0
    while i < n:
        period = RATE / max(60.0, f0s[i]) * (1 + random.uniform(-jitter, jitter))
        amp = 1.0 + random.uniform(-shimmer, shimmer)
        opening = period * 0.42
        closing = period * 0.16
        length = int(period)
        for k in range(length):
            if i + k >= n:
                break
            if k < opening:
                value = 0.5 - 0.5 * math.cos(math.pi * k / opening)
            elif k < opening + closing:
                value = math.cos(math.pi * (k - opening) / (2 * closing))
            else:
                value = 0.0
            flow[i + k] = value * amp
        i += max(1, length)
    out = [0.0] * n
    for k in range(1, n):
        out[k] = (flow[k] - flow[k - 1]) * 30 + random.uniform(-1, 1) * aspiration
    return out


def band_noise(n, center, level, spread=0.55):
    if n <= 0:
        return []
    src = [random.uniform(-1, 1) for _ in range(n)]
    out = Reson().block(src, center, center * spread)
    out = Reson().block(out, center, center * spread)
    peak = max((abs(v) for v in out), default=1.0) or 1.0
    out = [v / peak * level for v in out]
    edge = max(1, int(RATE * 0.006))
    for k in range(n):
        out[k] *= min(1.0, min(k, n - 1 - k) / edge)
    return out


def smooth(values, width):
    """移動平均。音程を段々ではなく滑らかに動かすために使う。"""
    if width < 2:
        return values
    half = width // 2
    out = [0.0] * len(values)
    total = sum(values[:half]) if values else 0.0
    count = half
    for i in range(len(values)):
        if i + half < len(values):
            total += values[i + half]
            count += 1
        if i - half - 1 >= 0:
            total -= values[i - half - 1]
            count -= 1
        out[i] = total / max(1, count)
    return out


def parse(text):
    """かなを（子音, 母音, 促音か, 長音の伸ばし）の並びにする。"""
    moras, geminate, i = [], False, 0
    text = "".join(chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch for ch in text)
    while i < len(text):
        ch = text[i]
        if ch == "っ":
            geminate = True
            i += 1
            continue
        if ch in "ー〜" and moras:
            moras[-1] = moras[-1][:3] + (moras[-1][3] + 0.13,)
            i += 1
            continue
        if ch == "ん":
            moras.append(("N", "", False, 0.0))
            i += 1
            continue
        if ch in "、。 　,.!?！？\n":
            moras.append(("_", "", False, 0.10))
            i += 1
            continue
        if ch not in KANA:
            i += 1
            continue
        cons, vowel = KANA[ch]
        if i + 1 < len(text) and text[i + 1] in SMALL:
            small = SMALL[text[i + 1]]
            if text[i + 1] in "ゃゅょ":
                cons = cons + "y" if cons and not cons.endswith("y") else cons
                if cons in ("shy", "chy", "jy"):
                    cons = cons[:-1]
                vowel = small
            else:
                vowel = small
            i += 1
        moras.append((cons, vowel, geminate, 0.0))
        geminate = False
        i += 1
    return moras


def speak(text, base=300, pitch_k=1.0, formant_k=1.0, breath=0.035,
          bright=1.0, seed=3):
    """かなを音にする。

    まず「どの区間をどの音で鳴らすか」の台本を組み立て、そのあとで
    文全体の音程を一本の曲線として作ります。モーラごとに音程を決め直すと
    階段状になって、いかにもロボットの声になります。
    """
    random.seed(seed)
    moras = parse(text)
    if not moras:
        return []

    def formants(vowel):
        f1, f2, f3, level = VOWELS[vowel]
        return ((f1 * formant_k, f2 * formant_k, f3 * formant_k,
                 3600 * formant_k * bright), level)

    plan = []                      # (種類, 秒数, ...)
    count = len(moras)
    for index, (cons, vowel, geminate, extra) in enumerate(moras):
        pos = index / max(1, count - 1)
        f0 = (base + math.sin(math.pi * pos) * 20 - 40 * pos) * pitch_k
        if cons == "_":
            plan.append(("sil", 0.10 + extra, f0))
            continue
        if cons == "N":
            f1, f2, f3, level = NASAL
            nasal = (f1 * formant_k, f2 * formant_k, f3 * formant_k, 3600 * formant_k)
            plan.append(("voice", 0.13 + extra, nasal, nasal, level, level * 0.5, True, f0))
            continue

        kind, voiced, closure, burst, burst_len, locus = C[cons.rstrip("y")]
        if cons.endswith("y") and cons != "y":
            locus = 2350
        if geminate:
            closure = max(closure, 0.055) + 0.055

        if kind in ("stop", "affr") and closure:
            plan.append(("sil", closure, f0))
        if kind == "tap":
            plan.append(("sil", closure, f0))
        if burst and burst_len:
            plan.append(("noise", burst_len, burst[0] * formant_k, burst[1] * 0.45, f0))
        if kind == "nasal":
            f1, f2, f3, level = NASAL
            nasal = (f1 * formant_k, min(f2, locus) * formant_k, f3 * formant_k,
                     3600 * formant_k)
            plan.append(("voice", closure, nasal, nasal, level, level, True, f0))

        target, level = formants(vowel)
        onset = (target[0] * 0.78, locus * formant_k, target[2], target[3])
        following = moras[index + 1][0] if index + 1 < count else ""
        devoiced = (vowel in "iu" and not voiced
                    and (following in ("", "_")
                         or (following not in ("N",) and not C[following.rstrip("y")][1])))
        glide = 0.065 if kind == "glide" else 0.045
        body = max(0.035, 0.090 + extra - glide * 0.5)
        if devoiced:
            body *= 0.70
        # ささやきは声より小さく聞こえるので、無声化したモーラは持ち上げる。
        # そのままだと語の途中がぽっかり抜けて聞こえます。
        gain = 2.2 if devoiced else 1.0
        plan.append(("voice", glide, onset, target,
                     level * 0.5 * gain, level * gain, not devoiced, f0))
        plan.append(("voice", body, target, target,
                     level * gain, level * 0.88 * gain, not devoiced, f0))

    # --- 音程を文全体で一本の曲線にする ---------------------------------
    total = sum(int(RATE * item[1]) for item in plan)
    if total <= 0:
        return []
    f0s = [base * pitch_k] * total
    cursor = 0
    for item in plan:
        n = int(RATE * item[1])
        value = item[-1]
        for k in range(n):
            if cursor + k < total:
                f0s[cursor + k] = value
        cursor += n
    f0s = smooth(f0s, int(RATE * 0.045))
    for i in range(total):                      # ゆっくりした揺れ（人の声のふるえ）
        f0s[i] *= 1 + 0.004 * math.sin(2 * math.pi * 5.2 * i / RATE)

    source = glottal(f0s, aspiration=breath * 0.5)
    cascade = Cascade()
    out = [0.0] * total
    cursor = 0
    block = max(1, int(RATE * 0.005))
    for item in plan:
        n = int(RATE * item[1])
        if item[0] == "sil":
            cursor += n
            continue
        if item[0] == "noise":
            _, _, center, level, _ = item
            for k, value in enumerate(band_noise(n, center, level)):
                if cursor + k < total:
                    out[cursor + k] += value
            cursor += n
            continue
        _, _, fa, fb, la, lb, voiced, _ = item
        done = 0
        while done < n:
            width = min(block, n - done)
            mid = (done + width / 2) / max(1, n)
            freqs = [fa[j] + (fb[j] - fa[j]) * mid for j in range(4)]
            level = la + (lb - la) * mid
            if voiced:
                chunk = source[cursor + done:cursor + done + width]
            else:                                # 無声（ささやき）
                chunk = [random.uniform(-1, 1) * 0.4 for _ in range(width)]
            shaped = cascade.block(chunk, freqs)
            for k, value in enumerate(shaped):
                if cursor + done + k < total:
                    out[cursor + done + k] += value * level
            done += width
        cursor += n

    tail = int(RATE * 0.05)
    for i in range(min(tail, len(out))):
        out[len(out) - 1 - i] *= i / tail
    return out


VOICE_PRESETS = {
    "normal": dict(base=210, pitch_k=1.00, formant_k=1.00, breath=0.035, bright=1.00),
    "deep":   dict(base=210, pitch_k=0.62, formant_k=0.86, breath=0.050, bright=0.92),
    "puppy":  dict(base=210, pitch_k=1.45, formant_k=1.22, breath=0.035, bright=1.10),
    "husky":  dict(base=210, pitch_k=0.88, formant_k=0.98, breath=0.180, bright=1.00),
    "flat":   dict(base=195, pitch_k=0.82, formant_k=0.94, breath=0.030, bright=0.95),
}


def main():
    ap = argparse.ArgumentParser(description="ロウにしゃべらせる")
    ap.add_argument("text")
    ap.add_argument("--voice", default="normal", choices=sorted(VOICE_PRESETS))
    ap.add_argument("--play", action="store_true")
    ap.add_argument("-o", "--out", default=str(pathlib.Path(__file__).resolve().parent / "sound"))
    ap.add_argument("--name", default="rou_speak")
    args = ap.parse_args()

    samples = speak(args.text, **VOICE_PRESETS[args.voice])
    if not samples:
        raise SystemExit("かなが1文字もありません")
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.name}.wav"
    sound.write_wav(path, samples)
    print(f"{sound.shown(path)}  {len(samples) / RATE:.2f}秒  「{args.text}」")
    if args.play:
        sound.play(path)


if __name__ == "__main__":
    main()
