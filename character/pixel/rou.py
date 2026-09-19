#!/usr/bin/env python3
"""投稿スクリプトからロウを呼び出すための入口。

    import rou
    rou.speak("posted", title="before と after の比較")
    rou.speak("daily", count=5, best="朝いちばん")
    print(rou.line("error", reason="接続切れ"))

`speak()` は端末にロウの絵とセリフを出し、音があれば鳴らします。
絵が邪魔なときは `rou.speak(..., face=False)`、
音を止めたいときは `ROU_SILENT=1` か `rou.speak(..., sound=False)`。
出力先が端末でないとき（ログへのリダイレクトなど）は、絵と音は自動で止まります。
"""
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
VOICE_DIR = HERE / "sound" / "voice"
SOUND_DIR = HERE / "sound"
_LINES = None


def lines():
    global _LINES
    if _LINES is None:
        _LINES = json.loads((HERE / "lines.json").read_text(encoding="utf-8"))["lines"]
    return _LINES


def line(state, **values):
    """セリフを文字列で返す。値を渡さなければ見本で埋める。"""
    entry = lines()[state]
    return entry["text"].format(**(values or entry.get("expression_example", entry.get("example", {}))))


def face_art(state):
    """端末用の絵を文字列で返す。色が使えないときは空文字。"""
    entry = lines()[state]
    sys.path.insert(0, str(HERE))
    import show
    grid = show.trim([ln for ln in (HERE / f'{entry["face"]}.txt').read_text(
        encoding="utf-8").splitlines() if ln])
    return show.render(grid, show.load_palette())


def _playable():
    return not os.environ.get("ROU_SILENT") and sys.stdout.isatty()


def play(path):
    for player in (["afplay"], ["aplay", "-q"], ["paplay"], ["play", "-q"]):
        if path.exists() and _which(player[0]):
            subprocess.run(player + [str(path)], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    return False


def _which(name):
    from shutil import which
    return which(name)


def speak(state, face=True, sound=True, voice=True, **values):
    """ロウにひとこと言わせる。絵・セリフ・音をまとめて出す。"""
    text = line(state, **values)
    if face and sys.stdout.isatty() and not os.environ.get("NO_COLOR"):
        print(face_art(state))
    print(f"  ロウ: {text}")
    if _playable():
        entry = lines()[state]
        if voice and (VOICE_DIR / f"rou_{state}.wav").exists():
            play(VOICE_DIR / f"rou_{state}.wav")
        elif sound and entry.get("sound"):
            play(SOUND_DIR / f'{entry["sound"]}.wav')
    return text


if __name__ == "__main__":
    state = sys.argv[1] if len(sys.argv) > 1 else "hello"
    speak(state)
