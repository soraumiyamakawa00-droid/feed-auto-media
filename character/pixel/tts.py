#!/usr/bin/env python3
"""ロウのセリフを、手元にある読み上げエンジンで音声にする。

    python3 character/pixel/tts.py "とうこうしたよ"              # 使えるものを自動で選ぶ
    python3 character/pixel/tts.py "こんにちは" --backend say     # エンジンを指定
    python3 character/pixel/tts.py --check                       # 何が使えるか調べる
    python3 character/pixel/tts.py --all --backend say           # セリフ集をまとめて生成
    python3 character/pixel/tts.py --voices --backend say        # 選べる声の一覧
    python3 character/pixel/tts.py "やあ" --voicevox-speaker 3    # VOICEVOX の話者を選ぶ

自前の合成（speak.py）はフォルマント合成なので、どれだけ調整しても
「よくできた合成音声」止まりです。人の声に聞こえるものは、実際に人が喋った音を
使っています（録音をつなぐか、録音から学習したモデル）。
このスクリプトは、その「人の声」を持っているエンジンに橋渡しします。

    say       macOS 内蔵。インストール不要。日本語は Kyoko。
              システム設定 → アクセシビリティ → 読み上げコンテンツ から
              高品質版（Kyoko 拡張／プレミアム）を入れるとかなり自然になります。
    voicevox  VOICEVOX。無料・日本語・ローカル。キャラクターらしい声ならこれ。
              アプリを起動しておくと http://127.0.0.1:50021 で待ち受けます。
    piper     オフラインのニューラル音声。モデル(.onnx)を1つ落とすだけで動きます。
    openjtalk 日本語専用。`pip install pyopenjtalk` だけで声が付いてきます
              （初回に辞書を自動で落とします）。ネットワークが制限された環境でも
              入れやすいのが利点。
    builtin   speak.py。エンジンが何も無いときの保険。
"""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
VOICEVOX = "http://127.0.0.1:50021"


def has_say():
    return sys.platform == "darwin" and shutil.which("say") is not None


def has_piper():
    return shutil.which("piper") is not None


def has_openjtalk():
    try:
        import pyopenjtalk  # noqa: F401
        return True
    except Exception:
        return False


def has_voicevox(timeout=1.0):
    try:
        with urllib.request.urlopen(f"{VOICEVOX}/version", timeout=timeout) as res:
            return res.status == 200
    except (urllib.error.URLError, OSError):
        return False


def run_say(text, path, voice="Kyoko", rate=None):
    aiff = path.with_suffix(".aiff")
    cmd = ["say", "-v", voice, "-o", str(aiff)]
    if rate:
        cmd += ["-r", str(rate)]
    subprocess.run(cmd + [text], check=True)
    # macOS 標準の afconvert で WAV に変換する
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@22050",
                    str(aiff), str(path)], check=True)
    aiff.unlink(missing_ok=True)


def run_voicevox(text, path, speaker=3, speed=1.0, pitch=0.0, intonation=1.0):
    query_url = f"{VOICEVOX}/audio_query?" + urllib.parse.urlencode(
        {"text": text, "speaker": speaker})
    request = urllib.request.Request(query_url, data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=20) as res:
        query = json.loads(res.read())
    query["speedScale"] = speed
    query["pitchScale"] = pitch
    query["intonationScale"] = intonation
    synth_url = f"{VOICEVOX}/synthesis?" + urllib.parse.urlencode({"speaker": speaker})
    request = urllib.request.Request(
        synth_url, data=json.dumps(query).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as res:
        path.write_bytes(res.read())


def run_piper(text, path, model):
    if not model:
        raise SystemExit("piper はモデルの指定が要ります: --piper-model path/to/voice.onnx")
    subprocess.run(["piper", "--model", model, "--output_file", str(path)],
                   input=text.encode(), check=True)


def run_openjtalk(text, path, speed=1.0):
    import struct
    import wave

    import pyopenjtalk
    samples, rate = pyopenjtalk.tts(text, speed=speed)
    peak = max((abs(float(v)) for v in samples), default=1.0) or 1.0
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, float(v) / peak * 0.92)) * 32767))
        for v in samples)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(int(rate))
        fh.writeframes(frames)


def run_builtin(text, path, voice="normal"):
    sys.path.insert(0, str(HERE))
    import sound
    import speak as builtin
    sound.write_wav(path, builtin.speak(text, **builtin.VOICE_PRESETS[voice]))


def list_voices(backend):
    if backend == "say":
        subprocess.run(["say", "-v", "?"], check=False)
    elif backend == "voicevox":
        with urllib.request.urlopen(f"{VOICEVOX}/speakers", timeout=10) as res:
            for speaker in json.loads(res.read()):
                for style in speaker["styles"]:
                    print(f'{style["id"]:4}  {speaker["name"]}（{style["name"]}）')
    else:
        print(f"{backend} は声の一覧を持っていません")


def load_lines():
    data = json.loads((HERE / "lines.json").read_text(encoding="utf-8"))
    return data["lines"]


def detect():
    if has_voicevox():
        return "voicevox"
    if has_say():
        return "say"
    if has_openjtalk():
        return "openjtalk"
    if has_piper():
        return "piper"          # モデルの指定が要るので最後に回す
    return "builtin"


def main():
    ap = argparse.ArgumentParser(description="ロウのセリフを読み上げエンジンで音声にする")
    ap.add_argument("text", nargs="?")
    ap.add_argument("--backend", default="auto",
                    choices=["auto", "say", "voicevox", "piper", "openjtalk", "builtin"])
    ap.add_argument("--check", action="store_true", help="使えるエンジンを調べる")
    ap.add_argument("--all", action="store_true", help="lines.json のセリフを全部生成する")
    ap.add_argument("--voices", action="store_true", help="選べる声の一覧を出す")
    ap.add_argument("--say-voice", default="Kyoko")
    ap.add_argument("--voicevox-speaker", type=int, default=3)
    ap.add_argument("--piper-model")
    ap.add_argument("--builtin-voice", default="normal")
    ap.add_argument("--speed", type=float, default=1.0, help="openjtalk の話速")
    ap.add_argument("--play", action="store_true")
    ap.add_argument("-o", "--out", default=str(HERE / "sound"))
    ap.add_argument("--name", default="rou_tts")
    args = ap.parse_args()

    if args.check:
        rows = [("voicevox", has_voicevox(), "VOICEVOX を起動しておく（:50021）"),
                ("say", has_say(), "macOS 内蔵。インストール不要"),
                ("piper", has_piper(), "piper をインストールしてモデルを1つ落とす"),
                ("openjtalk", has_openjtalk(), "pip install pyopenjtalk（声が同梱）"),
                ("builtin", True, "speak.py（自前の合成）")]
        for name, ok, note in rows:
            print(f'{"使える" if ok else "  ---"}  {name:9} {note}')
        print(f"\n自動で選ぶと: {detect()}")
        return

    backend = detect() if args.backend == "auto" else args.backend
    if args.voices:
        list_voices(backend)
        return
    if not args.text and not args.all:
        raise SystemExit("セリフを渡してください（--check で使えるエンジンを確認できます）")
    missing = {"say": (has_say, "macOS でのみ使えます"),
               "voicevox": (has_voicevox, "VOICEVOX を起動してください（http://127.0.0.1:50021）"),
               "piper": (has_piper, "piper が見つかりません"),
               "openjtalk": (has_openjtalk, "pip install pyopenjtalk で入ります")}
    if backend in missing and not missing[backend][0]():
        raise SystemExit(f"{backend} は使えません。{missing[backend][1]}\n"
                         f"--check で使えるエンジンを確認できます。")
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    def render(text, path):
        if backend == "say":
            run_say(text, path, args.say_voice)
        elif backend == "voicevox":
            run_voicevox(text, path, args.voicevox_speaker)
        elif backend == "piper":
            run_piper(text, path, args.piper_model)
        elif backend == "openjtalk":
            run_openjtalk(text, path, args.speed)
        else:
            run_builtin(text, path, args.builtin_voice)

    if args.all:
        voice_dir = out_dir / "voice"
        voice_dir.mkdir(parents=True, exist_ok=True)
        for state, line in load_lines().items():
            path = voice_dir / f"rou_{state}.wav"
            render(line["text"], path)
            print(f'{path}  ({backend})  {state:10} 「{line["text"]}」')
        return

    path = out_dir / f"{args.name}.wav"

    if backend == "say":
        run_say(args.text, path, args.say_voice)
    elif backend == "voicevox":
        run_voicevox(args.text, path, args.voicevox_speaker)
    elif backend == "piper":
        run_piper(args.text, path, args.piper_model)
    elif backend == "openjtalk":
        run_openjtalk(args.text, path, args.speed)
    else:
        run_builtin(args.text, path, args.builtin_voice)

    print(f"{path}  ({backend})  「{args.text}」")
    if args.play:
        sys.path.insert(0, str(HERE))
        import sound
        sound.play(path)


if __name__ == "__main__":
    main()
