#!/usr/bin/env python3
"""media/ の画像を順に投稿し、ロウが経過を報告する。

    python3 post.py --dry-run          # 何をするか見るだけ
    python3 post.py --limit 2          # 2件だけ
    python3 post.py --quiet            # ロウを黙らせる（ログ向き）

実際の送信は post_one() の中だけです。投稿先が決まったらそこを差し替えれば、
ほかは触らずに動きます。どの画像を出したかは .feed-state.json に残ります。
"""
import argparse
import collections
import datetime
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
MEDIA = ROOT / "media"
STATE = ROOT / ".feed-state.json"
sys.path.insert(0, str(ROOT / "character" / "pixel"))
import rou  # noqa: E402

QUIET = False


def narrate(state, **values):
    if QUIET:
        print(f"  {rou.line(state, **values)}")
    else:
        rou.speak(state, **values)


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"posted": [], "history": []}


def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def title_of(path):
    """ファイル名から人が読める見出しを作る。頭の数字は投稿時刻なので落とす。"""
    stem = path.stem
    if "_" in stem and stem.split("_", 1)[0].isdigit():
        stem = stem.split("_", 1)[1]
    return stem.replace("_", " ").replace("-", " ")


def candidates(state):
    seen = {item["digest"] for item in state["posted"]}
    out = []
    for path in sorted(MEDIA.glob("*.jpg")) + sorted(MEDIA.glob("*.png")):
        fingerprint = digest(path)
        out.append((path, fingerprint, fingerprint in seen))
    return out


def post_one(path, dry_run):
    """ここが実際の送信。投稿先が決まったら中身を差し替える。"""
    if dry_run:
        return True
    raise NotImplementedError(
        "投稿先がまだつながっていません。post_one() に送信処理を書いてください。")


def best_hour(state):
    """反応がよかった時刻。

    まだ反応を集めていないので、いまは常に None を返します。
    投稿先の統計が取れるようになったら、ここで返すようにしてください。
    「いちばん伸びてた」は実際に伸びを見ていないと言ってはいけない台詞です。
    """
    return None


def main():
    global QUIET
    ap = argparse.ArgumentParser(description="media/ を投稿する")
    ap.add_argument("--dry-run", action="store_true", help="送信せずに流れだけ見る")
    ap.add_argument("--limit", type=int, default=3, help="1回に出す上限")
    ap.add_argument("--quiet", action="store_true", help="絵と音を出さない")
    args = ap.parse_args()
    QUIET = args.quiet

    state = load_state()
    if not state["posted"]:
        narrate("hello")

    items = candidates(state)
    if not items:
        print("  media/ に画像がありません。")
        return

    posted = 0
    for path, fingerprint, already in items:
        if posted >= args.limit:
            break
        if already:
            narrate("skipped", reason="前にも出した画像")
            continue
        if post_one(path, args.dry_run):
            state["posted"].append({
                "file": path.name, "digest": fingerprint,
                "at": datetime.datetime.now().isoformat(timespec="seconds"),
            })
            posted += 1
            narrate("posted", title=title_of(path))

    remaining = sum(1 for _, _, already in items if not already) - posted
    if posted:
        best = best_hour(state)
        if best:
            narrate("daily", count=str(posted), best=best)
        else:
            narrate("daily_plain", count=str(posted))
        streak = len({item["at"][:10] for item in state["posted"]})
        if streak >= 2:
            narrate("streak", days=str(streak))
    if remaining <= 0:
        narrate("empty")
    else:
        narrate("idle", time=f"{(datetime.datetime.now().hour + 3) % 24}時")

    if not args.dry_run:
        save_state(state)
    else:
        print("\n  （--dry-run なので .feed-state.json は書き換えていません）")


if __name__ == "__main__":
    main()
