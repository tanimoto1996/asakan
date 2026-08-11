#!/usr/bin/env python3
"""朝刊ジェネレーター
RSSフィードを巡回し、Gemini APIで日本語要約を付けて
docs/index.html (GitHub Pages) を生成する。
Geminiが使えない場合は要約なしで紙面を発行する(発行は止めない)。
"""
import calendar
import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import yaml

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ARCHIVE = DOCS / "archive"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


def strip_tags(text: str, limit: int = 300) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:limit]


def entry_datetime(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            # feedparser の *_parsed はUTCのstruct_time。mktimeはローカル解釈なので不可
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


def collect_articles(config):
    """フィードを巡回して window_hours 以内の新着を集める"""
    window = timedelta(hours=config.get("window_hours", 26))
    cutoff = datetime.now(timezone.utc) - window
    result = []
    for cat in config["categories"]:
        items = []
        for feed in cat["feeds"]:
            try:
                parsed = feedparser.parse(
                    feed["url"], agent="Mozilla/5.0 (MorningPaperBot)"
                )
                if parsed.bozo and not parsed.entries:
                    print(
                        f"[warn] feed unreadable: {feed['url']}: "
                        f"{getattr(parsed, 'bozo_exception', 'unknown')}",
                        file=sys.stderr,
                    )
                    continue
                for e in parsed.entries:
                    dt = entry_datetime(e)
                    if dt is None or dt < cutoff:
                        continue
                    items.append({
                        "ts": dt.timestamp(),
                        "source": feed["name"],
                        "title": strip_tags(e.get("title", "(no title)"), 200),
                        "url": e.get("link", ""),
                        "summary_src": strip_tags(
                            e.get("summary", "") or e.get("description", "")
                        ),
                        "published": dt.astimezone(JST).strftime("%m/%d %H:%M"),
                        "title_ja": "",
                        "summary_ja": "",
                        "importance": 0,
                    })
            except Exception as ex:  # フィード単位の失敗は握りつぶして続行
                print(f"[warn] feed failed: {feed['url']}: {ex}", file=sys.stderr)
        items.sort(key=lambda x: x["ts"], reverse=True)
        limit = config.get("max_items_per_category", 15)
        result.append({
            "name": cat["name"],
            "icon": cat.get("icon", ""),
            "items": items[:limit],
        })
    return result


def summarize_with_gemini(categories):
    """全記事を1リクエストにまとめてGeminiに投げ、日本語要約と注目度を得る"""
    articles = []
    for cat in categories:
        for it in cat["items"]:
            articles.append({
                "id": len(articles),
                "category": cat["name"],
                "source": it["source"],
                "title": it["title"],
                "summary": it["summary_src"],
            })
    if not articles:
        return
    if not GEMINI_API_KEY:
        print("[warn] GEMINI_API_KEY not set; skipping summaries", file=sys.stderr)
        return

    prompt = (
        "あなたは技術ニュースの編集者です。以下の記事リストについて、"
        "各記事に (1) タイトルの自然な日本語訳(元が日本語ならそのまま)、"
        "(2) 日本語要約(2文以内、体言止め可、です・ます不要)、"
        "(3) Webエンジニアにとっての注目度(1=参考程度, 2=読む価値あり, 3=必読)を付けてください。\n"
        "固有名詞・製品名・バージョン番号は翻訳せず原文のまま残すこと。\n"
        "出力はJSON配列のみ。マークダウンのコードブロックや前置きは一切不要。\n"
        '形式: [{"id": 0, "title_ja": "...", "summary_ja": "...", "importance": 2}, ...]\n\n'
        f"記事リスト:\n{json.dumps(articles, ensure_ascii=False)}"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            # gemini-2.5系はthinkingトークンもここから消費するため大きめに確保
            "maxOutputTokens": 65536,
            "responseMimeType": "application/json",
        },
    }).encode()
    req = urllib.request.Request(
        GEMINI_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
        summaries = {s["id"]: s for s in json.loads(text)}
    except Exception as ex:
        print(f"[warn] Gemini summarization failed: {ex}", file=sys.stderr)
        return

    idx = 0
    for cat in categories:
        for it in cat["items"]:
            s = summaries.get(idx, {})
            it["title_ja"] = s.get("title_ja", "")
            it["summary_ja"] = s.get("summary_ja", "")
            it["importance"] = int(s.get("importance", 0) or 0)
            idx += 1


CSS = """
:root { --ink:#1a1a1a; --paper:#faf7f0; --accent:#b5442d; --line:#d8d2c4; }
* { box-sizing:border-box; }
body { margin:0; background:var(--paper); color:var(--ink);
  font-family:'Hiragino Kaku Gothic ProN','Yu Gothic',Meiryo,sans-serif; line-height:1.7; }
.wrap { max-width:820px; margin:0 auto; padding:24px 16px 64px; }
header { text-align:center; border-bottom:3px double var(--ink); padding-bottom:12px; margin-bottom:8px; }
header h1 { font-family:Georgia,'Times New Roman','Yu Mincho',serif; font-size:2.2rem; margin:0; letter-spacing:.12em; }
header .date { color:#666; font-size:.9rem; margin-top:4px; }
.toolbar { text-align:right; font-size:.8rem; margin-bottom:20px; }
.toolbar a { color:#666; }
section { margin-bottom:36px; }
h2 { font-size:1.15rem; border-left:5px solid var(--accent); padding-left:10px;
  border-bottom:1px solid var(--line); padding-bottom:6px; }
article { padding:12px 4px; border-bottom:1px dotted var(--line); }
article h3 { margin:0 0 4px; font-size:1rem; }
article h3 a { color:var(--ink); text-decoration:none; }
article h3 a:hover { color:var(--accent); text-decoration:underline; }
.meta { font-size:.75rem; color:#888; }
.orig { font-size:.75rem; color:#999; margin-bottom:2px; }
.link { font-size:.72rem; margin-top:6px; word-break:break-all; }
.link a { color:#7a6f52; text-decoration:none; }
.link a:hover { text-decoration:underline; }
.sum { margin:6px 0 0; font-size:.9rem; color:#333; }
.badge { display:inline-block; font-size:.7rem; padding:1px 8px; border-radius:10px;
  margin-right:6px; vertical-align:middle; color:#fff; }
.imp3 { background:var(--accent); } .imp2 { background:#8a7d55; } .imp1 { background:#aaa; }
.empty { color:#999; font-size:.85rem; padding:8px 4px; }
footer { text-align:center; color:#999; font-size:.75rem; border-top:1px solid var(--line); padding-top:16px; }
@media (prefers-color-scheme: dark) {
  :root { --ink:#e8e4da; --paper:#191817; --line:#3a3630; }
  .sum { color:#c8c4ba; } article h3 a { color:var(--ink); }
}
"""

IMP_LABEL = {3: "必読", 2: "注目", 1: "参考"}


def render_html(categories, today):
    parts = [
        "<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>テック朝刊 {today.strftime('%Y-%m-%d')}</title>",
        f"<style>{CSS}</style></head><body><div class='wrap'>",
        "<header><h1>テック朝刊</h1>",
        f"<div class='date'>{today.strftime('%Y年%m月%d日')} "
        f"({'月火水木金土日'[today.weekday()]}) 発行</div></header>",
        "<div class='toolbar'><a href='./archive/'>バックナンバー</a></div>",
    ]
    total = 0
    for cat in categories:
        parts.append(f"<section><h2>{cat['icon']} {html.escape(cat['name'])}</h2>")
        if not cat["items"]:
            parts.append("<p class='empty'>本日の新着はありません</p>")
        for it in cat["items"]:
            total += 1
            badge = ""
            if it["importance"] in IMP_LABEL:
                badge = (f"<span class='badge imp{it['importance']}'>"
                         f"{IMP_LABEL[it['importance']]}</span>")
            summary = it["summary_ja"] or it["summary_src"][:120]
            url = html.escape(it["url"])
            # 見出しは日本語訳を優先。訳がある場合は原題を小さく併記
            headline = it["title_ja"] or it["title"]
            orig = ""
            if it["title_ja"] and it["title_ja"] != it["title"]:
                orig = f"<div class='orig'>原題: {html.escape(it['title'])}</div>"
            parts.append(
                "<article>"
                f"<h3>{badge}<a href='{url}' target='_blank' "
                f"rel='noopener'>{html.escape(headline)}</a></h3>"
                + orig +
                f"<div class='meta'>{html.escape(it['source'])} ・ {it['published']}</div>"
                + (f"<p class='sum'>{html.escape(summary)}</p>" if summary else "")
                + f"<div class='link'>🔗 <a href='{url}' target='_blank' "
                  f"rel='noopener'>{url}</a></div>"
                "</article>"
            )
        parts.append("</section>")
    parts.append(
        f"<footer>本日 {total} 件 ・ Generated by GitHub Actions + Gemini API</footer>"
        "</div></body></html>"
    )
    return "".join(parts)


def render_archive_index():
    files = sorted(
        (f for f in ARCHIVE.glob("*.html") if f.name != "index.html"),
        reverse=True,
    )
    links = "".join(
        f"<li><a href='./{f.name}'>{f.stem}</a></li>" for f in files
    )
    return (
        "<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>"
        f"<title>バックナンバー</title><style>{CSS}</style></head><body>"
        "<div class='wrap'><header><h1>バックナンバー</h1></header>"
        f"<ul>{links}</ul><p><a href='../'>← 最新号へ</a></p></div></body></html>"
    )


def main():
    config = yaml.safe_load((ROOT / "feeds.yml").read_text(encoding="utf-8"))
    categories = collect_articles(config)
    summarize_with_gemini(categories)

    today = datetime.now(JST)
    page = render_html(categories, today)

    DOCS.mkdir(exist_ok=True)
    ARCHIVE.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(page, encoding="utf-8")
    (ARCHIVE / f"{today.strftime('%Y-%m-%d')}.html").write_text(page, encoding="utf-8")
    (ARCHIVE / "index.html").write_text(render_archive_index(), encoding="utf-8")
    print(f"Generated: {sum(len(c['items']) for c in categories)} articles")


if __name__ == "__main__":
    main()
