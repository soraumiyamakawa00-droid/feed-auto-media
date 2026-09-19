#!/usr/bin/env python3
"""手元でロウを一覧するページを作る。

    python3 character/pixel/sheet.py
    open character/sheet.html      # Windows は start、Linux は xdg-open

`character/sheet.html` を書き出します。画像も音もリポジトリのファイルを
相対パスで指しているだけなので、ページ自体は小さく、
グリッドを描き換えて render.py を流し直せば、開き直すだけで最新になります。
ブラウザだけで完結するので、サーバーは要りません。
"""
import html
import json
import pathlib
import wave

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "sheet.html"

EXPRESSIONS = [
    ("rou", "ふだん"), ("rou_happy", "うれしい"), ("rou_bark", "ほえる"),
    ("rou_smug", "どや"), ("rou_wink", "ウインク"), ("rou_surprise", "おどろき"),
    ("rou_sad", "しょんぼり"), ("rou_angry", "おこ"), ("rou_sleep", "ねむい"),
]
ANIMATIONS = [
    ("rou_idle.gif", "待機", "まばたきするだけ。置きっぱなしにする用。"),
    ("rou_hop.gif", "跳ねる", "投稿できたとき。"),
    ("rou_bark.gif", "ほえる", "呼びかけ・注意。"),
    ("rou_sleep.gif", "ねむる", "やることがないとき。"),
]
SOUNDS = [
    ("rou_wake.wav", "起きた"), ("rou_bark.wav", "ほえる"), ("rou_hop.wav", "跳ねた"),
    ("rou_error.wav", "しくじった"), ("rou_sleep.wav", "ねむる"),
]
# post.py --dry-run を1回流したときに出る順番
RUN = ["hello", "posted", "daily_plain", "empty"]


def lines():
    return json.loads((HERE / "lines.json").read_text(encoding="utf-8"))["lines"]


def filled(entry):
    return entry["text"].format(**entry.get("example", {}))


def seconds(path):
    if not path.exists():
        return None
    with wave.open(str(path)) as f:
        return f.getnframes() / f.getframerate()


def rel(path):
    """sheet.html（character/ 直下）から見た相対パス。"""
    return path.relative_to(HERE.parent).as_posix()


def palette_rows():
    raw = json.loads((HERE / "palette.json").read_text(encoding="utf-8"))
    out = []
    for key, value in raw.items():
        if key.startswith("_"):
            continue
        swatch = value or "transparent"
        out.append(
            f'<li><span class="chip" style="background:{swatch}"></span>'
            f'<code>{html.escape(key)}</code><span class="hex">{value or "透明"}</span></li>'
        )
    return "".join(out)


def face_rows():
    out = []
    for stem, label in EXPRESSIONS:
        png = HERE / f"{stem}_x8.png"
        if not png.exists():
            continue
        src = rel(png)
        out.append(
            f'<figure><img src="{src}" alt="{label}" width="320" height="320">'
            f'<figcaption>{label}<span class="sub">{stem}.txt</span></figcaption></figure>'
        )
    return "".join(out)


def anim_rows():
    out = []
    for name, label, note in ANIMATIONS:
        path = HERE / "anim" / name
        if not path.exists():
            continue
        out.append(
            f'<figure><img src="{rel(path)}" alt="{label}" width="160" height="160">'
            f'<figcaption>{label}<span class="sub">{note}</span></figcaption></figure>'
        )
    return "".join(out)


def sound_rows():
    out = []
    for name, label in SOUNDS:
        path = HERE / "sound" / name
        if not path.exists():
            continue
        out.append(
            f'<li><span class="who">{label}</span>'
            f'<audio controls preload="none" src="{rel(path)}"></audio></li>'
        )
    return "".join(out)


def line_rows():
    out = []
    for state, entry in lines().items():
        voice = HERE / "sound" / "voice" / f"rou_{state}.wav"
        length = seconds(voice)
        player = (f'<audio controls preload="none" src="{rel(voice)}"></audio>'
                  if length else '<span class="sub">音声なし</span>')
        mark = ' class="inrun"' if state in RUN else ""
        out.append(
            f'<tr{mark}><td><code>{state}</code></td>'
            f'<td>{html.escape(filled(entry))}</td>'
            f'<td>{player}</td></tr>'
        )
    return "".join(out)


STYLE = """
  :root { color-scheme: light dark;
    --bg:#F7F4EC; --text:#16213E; --muted:#6B7280; --line:#DED7C6; --tile:#EFE9DA; --accent:#4A90D9; }
  @media (prefers-color-scheme: dark) { :root {
    --bg:#11141F; --text:#E9E6DD; --muted:#9AA1B0; --line:#2A2F40; --tile:#1A1E2C; } }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); padding:0 16px 80px;
    font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif; line-height:1.8; }
  main { max-width:900px; margin:0 auto; }
  h1 { font-size:1.6rem; margin:2.4rem 0 .3rem; }
  h2 { font-size:1.05rem; margin:3rem 0 .3rem; padding-top:1.6rem; border-top:1px solid var(--line); }
  p.lead, p.sub { color:var(--muted); font-size:.88rem; margin:.2rem 0 1.2rem; }
  img { max-width:100%; image-rendering:pixelated; }
  figure { margin:0; }
  figcaption { font-size:.82rem; margin-top:.4rem; display:flex; flex-direction:column; }
  .sub { color:var(--muted); font-size:.78rem; }
  .grid { display:grid; gap:1.2rem; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); }
  .grid img { width:100%; height:auto; background:var(--tile); border-radius:6px; padding:6px; }
  ul.plain { list-style:none; margin:0; padding:0; display:grid; gap:.5rem; }
  ul.plain li { display:flex; align-items:center; gap:.8rem; flex-wrap:wrap;
    border-bottom:1px solid var(--line); padding:.5rem 0; }
  .who { min-width:6rem; font-size:.9rem; }
  .chip { width:1.3rem; height:1.3rem; border-radius:4px; border:1px solid var(--line); flex:none; }
  .hex { color:var(--muted); font-size:.8rem; font-family:ui-monospace,monospace; }
  code { font-family:ui-monospace,SFMono-Regular,monospace; font-size:.85em; }
  table { width:100%; border-collapse:collapse; font-size:.9rem; }
  td { border-bottom:1px solid var(--line); padding:.6rem .5rem; vertical-align:middle; }
  td:first-child { width:9rem; color:var(--muted); }
  tr.inrun td:first-child code { color:var(--accent); font-weight:700; }
  audio { height:32px; max-width:230px; }
  pre { background:var(--tile); border:1px solid var(--line); border-radius:6px;
    padding:1rem; overflow-x:auto; font-size:.8rem; line-height:1.5; }
"""


def build():
    icon = HERE / "icons" / "rou_icon_256.png"
    body = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ロウ</title>
<style>{STYLE}</style>
</head>
<body>
<main>
  <h1>ロウ</h1>
  <p class="lead">このページは <code>character/pixel/sheet.py</code> が書き出したものです。
  画像と音はリポジトリのファイルを指しているだけなので、
  グリッドを描き換えて <code>render.py</code> を流し直せば、開き直すだけで最新になります。</p>
  <img src="{rel(icon)}" alt="ロウ" width="256" height="256">

  <h2>表情</h2>
  <p class="sub">体と毛は共通。顔と耳の角度だけ差し替えています。原本は <code>.txt</code> です。</p>
  <div class="grid">{face_rows()}</div>

  <h2>動き</h2>
  <p class="sub">絵を描き足さず、同じ絵を数 px ずらして作っています。</p>
  <div class="grid">{anim_rows()}</div>

  <h2>セリフと声</h2>
  <p class="sub">青い状態名が <code>post.py</code> を1回流したときに出るぶんです。
  <code>{{}}</code> は実際の値で埋まります（下は見本の値）。</p>
  <table><tbody>{line_rows()}</tbody></table>

  <h2>効果音</h2>
  <ul class="plain">{sound_rows()}</ul>

  <h2>色</h2>
  <p class="sub">グリッドの1文字がそのまま1色。<code>palette.json</code> を書き換えると全部に効きます。</p>
  <ul class="plain">{palette_rows()}</ul>

  <h2>手元で動かす</h2>
<pre>python3 character/pixel/render.py            # グリッド → PNG
python3 character/pixel/anim.py             # GIF
python3 character/pixel/icon.py             # アイコン
python3 character/pixel/tts.py --all        # セリフの声をまとめて作る
python3 character/pixel/show.py             # ターミナルに出す
python3 post.py --dry-run                   # ロウが喋る投稿スクリプト
python3 character/pixel/sheet.py            # このページを作り直す</pre>
</main>
</body>
</html>
"""
    OUT.write_text(body, encoding="utf-8")
    print(f"{OUT.relative_to(HERE.parent.parent)} を書き出しました（{OUT.stat().st_size // 1024} KB）")


if __name__ == "__main__":
    build()
