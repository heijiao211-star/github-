#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 每周飙升榜 -> PushPlus 推送
数据源: https://github.com/OpenGithubs/github-weekly-rank
推送: https://www.pushplus.plus
"""
import json
import re
import base64
import datetime
import urllib.request
import urllib.error
import os
import sys

SOURCE_OWNER = "OpenGithubs"
SOURCE_REPO = "github-weekly-rank"
PUSHPLUS_API = "https://www.pushplus.plus/send"


def http_get_json(url, timeout=30):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="ignore"))


def get_latest_weekly_file():
    """找到 OpenGithubs/github-weekly-rank 中最新的周榜 Markdown 文件路径."""
    now = datetime.datetime.now()
    # 周榜文件命名: YYYY/MM/YYYYMMDD.md, 周一早上 8 点更新
    # 最近 5 周(35天)的候选
    candidates = []
    for i in range(5):
        d = now - datetime.timedelta(days=7 * i)
        monday = d - datetime.timedelta(days=d.weekday())
        candidates.append(monday.strftime("%Y/%m/%Y%m%d.md"))

    for path in candidates:
        api = f"https://api.github.com/repos/{SOURCE_OWNER}/{SOURCE_REPO}/contents/{path}"
        try:
            data = http_get_json(api)
            content = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
            print(f"[INFO] found latest weekly file: {path}")
            return path, content
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"[INFO] not found {path}")
                continue
            raise
        except Exception as e:
            print(f"[WARN] error fetching {path}: {e}")
            continue
    raise RuntimeError("未找到最新的周榜文件")


def parse_rank_table(md):
    """解析周榜排行表格."""
    rows = []
    in_table = False
    for line in md.splitlines():
        if "周榜排行" in line:
            in_table = True
        if in_table and line.startswith("|") and "项目名" not in line and "---" not in line:
            parts = [p.strip() for p in line.split("|")][1:-1]
            if len(parts) >= 4:
                rank = parts[0]
                name_link = parts[1]
                m = re.search(r"\[([^\]]+)\]\(([^)]+)\)", name_link)
                name = m.group(1) if m else name_link
                url = m.group(2) if m else ""
                rows.append({
                    "rank": rank,
                    "name": name,
                    "url": url,
                    "stars": parts[2],
                    "growth": parts[3],
                })
    return rows


def format_message(rows, week_date):
    lines = [f"## GitHub 每周飙升榜 Top20 ({week_date})", ""]
    for r in rows[:20]:
        lines.append(f"{r['rank']}. [{r['name']}]({r['url']})")
        lines.append(f"   ⭐ {r['stars']} | {r['growth']}")
    lines.append("")
    lines.append(
        "来源: [OpenGithubs/github-weekly-rank]"
        "(https://github.com/OpenGithubs/github-weekly-rank)"
    )
    return "\n".join(lines)


def push_to_pushplus(token, title, content):
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": "markdown",
    }
    req = urllib.request.Request(
        PUSHPLUS_API,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = r.read().decode("utf-8", errors="ignore")
        print("[INFO] pushplus response:", resp)
        data = json.loads(resp)
        if data.get("code") != 200:
            raise RuntimeError(f"PushPlus 发送失败: {resp}")
        return data


def main():
    token = os.environ.get("PUSHPLUS_TOKEN")
    if not token:
        print("[ERROR] 环境变量 PUSHPLUS_TOKEN 未设置", file=sys.stderr)
        sys.exit(1)

    path, md = get_latest_weekly_file()
    week_date = path.split("/")[-1].replace(".md", "")
    rows = parse_rank_table(md)
    print(f"[INFO] parsed {len(rows)} rows")

    msg = format_message(rows, week_date)
    title = f"GitHub 每周飙升榜 ({week_date})"
    push_to_pushplus(token, title, msg)
    print("[INFO] 推送完成")


if __name__ == "__main__":
    main()
