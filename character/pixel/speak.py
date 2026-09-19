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
        gain = (1 - r) * math.sqrt(
            1 - 2 * r * math.cos(4 * math.pi * freq / RATE) + r * r)
        out = []
        for x in samples:
            y = gain * x - b1 * self.y1 - b2 * self.y2
            self.y2, self.y1 = self.y1, y
            out.append(y)
        return out


def pulse_train(n, f0_start, f0_end, phase, breath, width=0.16):
    out = []
    for i in range(n):
        t = i / max(1, n)
        freq = f0_start + (f0_end - f0_start) * t
        phase = (phase + freq / RATE) % 1.0
        value = (0.5 - 0.5 * math.cos(2 * math.pi * phase / width)) if phase < width else 0.0
        out.append((value - width / 2) * (1 - breath) + random.uniform(-1, 1) * breath)
    return out, phase


class Voicer:
    """声帯と3本のフォルマントをまとめて持つ。区間ごとに周波数を変えて鳴らす。"""

    def __init__(self, breath, f2_gain):
        self.phase = 0.0
        self.breath = breath
        self.f2_gain = f2_gain
        self.r1, self.r2, self.r3 = Reson(), Reson(), Reson()

    def run(self, seconds, f0a, f0b, fa, fb, level_a, level_b, voiced=True, block=0.005):
        total = int(RATE * seconds)
        if total <= 0:
            return []
        out = []
        done = 0
        step = max(1, int(RATE * block))
        while done < total:
            n = min(step, total - done)
            t0, t1 = done / total, (done + n) / total
            mid = (t0 + t1) / 2
            f1 = fa[0] + (fb[0] - fa[0]) * mid
            f2 = fa[1] + (fb[1] - fa[1]) * mid
            f3 = fa[2] + (fb[2] - fa[2]) * mid
            level = level_a + (level_b - level_a) * mid
            if voiced:
                src, self.phase = pulse_train(
                    n, f0a + (f0b - f0a) * t0, f0a + (f0b - f0a) * t1,
                    self.phase, self.breath)
            else:                                   # 無声：ささやき
                src = [random.uniform(-1, 1) * 0.35 for _ in range(n)]
            a = self.r1.block(src, f1, 80)
            b = self.r2.block(src, f2, 130)
            c = self.r3.block(src, f3, 200)
            out.extend((a[i] + b[i] * self.f2_gain + c[i] * 0.3) * level for i in range(n))
            done += n
        return out


def band_noise(seconds, center, level, voiced_f0=None, breath=1.0):
    n = int(RATE * seconds)
    if n <= 0:
        return []
    src = [random.uniform(-1, 1) for _ in range(n)]
    out = Reson().block(src, center, center * 0.55)
    out = Reson().block(out, center, center * 0.55)
    peak = max((abs(v) for v in out), default=1.0) or 1.0
    out = [v / peak * level for v in out]
    if voiced_f0:                                   # 有声摩擦：声も混ぜる
        buzz, _ = pulse_train(n, voiced_f0, voiced_f0, 0.0, 0.0)
        out = [out[i] * 0.7 + buzz[i] * 0.5 for i in range(n)]
    for i in range(n):                              # 端をなだらかに
        edge = min(i, n - 1 - i) / max(1, int(RATE * 0.008))
        out[i] *= min(1.0, edge)
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


def speak(text, base=300, pitch_k=1.0, formant_k=1.0, breath=0.035, f2_gain=1.5, seed=3):
    random.seed(seed)
    moras = parse(text)
    if not moras:
        return []
    voicer = Voicer(breath, f2_gain)
    out = []
    count = len(moras)

    def formants(vowel, level_scale=1.0):
        f1, f2, f3, level = VOWELS[vowel]
        return (f1 * formant_k, f2 * formant_k, f3 * formant_k), level * level_scale

    for index, (cons, vowel, geminate, extra) in enumerate(moras):
        pos = index / max(1, count - 1)
        f0 = (base + math.sin(math.pi * pos) * 22 - 42 * pos
              + random.uniform(-5, 5)) * pitch_k
        if cons == "_":
            out.extend([0.0] * int(RATE * (0.10 + extra)))
            continue
        if cons == "N":                              # 「ん」
            f1, f2, f3, level = NASAL
            target = ((f1 * formant_k, f2 * formant_k, f3 * formant_k), level)
            out.extend(voicer.run(0.13 + extra, f0, f0 * 0.93, target[0], target[0],
                                  target[1], target[1] * 0.4))
            continue

        kind, voiced, closure, burst, burst_len, locus = C[cons.rstrip("y")]
        palatal = cons.endswith("y") and cons != "y"
        if palatal:
            locus = 2350
        if geminate:
            closure = max(closure, 0.055) + 0.055

        # 1) 閉鎖・摩擦
        if kind in ("stop", "affr") and closure:
            out.extend([0.0] * int(RATE * closure))
        if burst and burst_len:
            out.extend(band_noise(burst_len, burst[0] * formant_k, burst[1] * 0.5,
                                  voiced_f0=f0 if voiced else None))
        if kind == "nasal":
            f1, f2, f3, level = NASAL
            nasal = (f1 * formant_k, min(f2, locus) * formant_k, f3 * formant_k)
            out.extend(voicer.run(closure, f0, f0, nasal, nasal, level, level))
        if kind == "tap":
            out.extend([0.0] * int(RATE * closure))

        # 2) 子音から母音への渡り → 母音本体
        target, level = formants(vowel)
        start = (target[0] * 0.75, locus * formant_k, target[2])
        devoiced = (vowel in "iu" and not voiced
                    and (index + 1 >= count or not C[moras[index + 1][0].rstrip("y")][1]
                         if index + 1 < count and moras[index + 1][0] not in ("N", "_")
                         else index + 1 >= count))
        glide_len = 0.045 if kind in ("stop", "affr", "nasal", "tap") else 0.035
        if kind == "glide":
            glide_len = 0.065
        body = max(0.03, 0.085 + extra - glide_len * 0.5)
        if devoiced:
            body *= 0.5
        out.extend(voicer.run(glide_len, f0, f0 * 0.99, start, target,
                              level * 0.55, level, voiced=not devoiced))
        out.extend(voicer.run(body, f0 * 0.99, f0 * 0.95, target, target,
                              level, level * 0.85, voiced=not devoiced))

    # 語尾を落とす
    tail = int(RATE * 0.05)
    for i in range(min(tail, len(out))):
        out[len(out) - 1 - i] *= i / tail
    return out


VOICE_PRESETS = {
    "normal": dict(base=300, pitch_k=1.00, formant_k=1.00, breath=0.035, f2_gain=1.5),
    "deep":   dict(base=300, pitch_k=0.62, formant_k=0.86, breath=0.045, f2_gain=1.3),
    "puppy":  dict(base=300, pitch_k=1.45, formant_k=1.22, breath=0.035, f2_gain=1.8),
    "husky":  dict(base=300, pitch_k=0.88, formant_k=0.98, breath=0.150, f2_gain=1.6),
    "flat":   dict(base=270, pitch_k=0.80, formant_k=0.94, breath=0.025, f2_gain=1.2),
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
