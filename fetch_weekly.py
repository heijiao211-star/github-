#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 每周飙升榜 -> AI 生成中文简介 -> PushPlus 推送
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

# AI 配置（OpenAI 兼容接口）
DEFAULT_AI_BASE_URL = "https://api.deepseek.com"
DEFAULT_AI_MODEL = "deepseek-chat"


def http_get(url, headers=None, timeout=30):
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/vnd.github+json",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def http_get_json(url, headers=None, timeout=30):
    return json.loads(http_get(url, headers, timeout))


def get_github_token():
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def github_api_headers():
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = get_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_latest_weekly_file():
    """找到 OpenGithubs/github-weekly-rank 中最新的周榜 Markdown 文件路径."""
    now = datetime.datetime.now()
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


def fetch_repo_details(full_name):
    """获取单个仓库的基本信息 + README 摘要."""
    parts = full_name.split("/")
    if len(parts) != 2:
        return None
    owner, repo = parts
    try:
        info = http_get_json(f"https://api.github.com/repos/{owner}/{repo}", headers=github_api_headers())
        desc = info.get("description") or ""
        topics = ", ".join(info.get("topics", [])) or ""
        language = info.get("language") or ""
        readme = ""
        try:
            readme_data = http_get_json(f"https://api.github.com/repos/{owner}/{repo}/readme", headers=github_api_headers())
            readme_text = base64.b64decode(readme_data["content"]).decode("utf-8", errors="ignore")
            # 去除 markdown 链接和图片，保留纯文本摘要
            readme = readme_text[:4000]
            readme = re.sub(r"!\[.*?\]\(.*?\)", "", readme)
            readme = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", readme)
            readme = re.sub(r"[#*`>-]", "", readme)
            readme = re.sub(r"\n+", "\n", readme).strip()[:1500]
        except urllib.error.HTTPError as e:
            if e.code != 404:
                print(f"[WARN] readme fetch error for {full_name}: {e}")
        return {
            "name": full_name,
            "url": f"https://github.com/{full_name}",
            "description": desc,
            "topics": topics,
            "language": language,
            "readme": readme,
        }
    except Exception as e:
        print(f"[WARN] repo detail error for {full_name}: {e}")
        return None


def summarize_with_ai(repos):
    """用 AI 批量生成中文一句话简介."""
    api_key = os.environ.get("AI_API_KEY")
    if not api_key:
        return {r["name"]: "（未配置 AI 接口）" for r in repos}

    base_url = os.environ.get("AI_BASE_URL", DEFAULT_AI_BASE_URL).rstrip("/")
    model = os.environ.get("AI_MODEL", DEFAULT_AI_MODEL)

    # 构建提示词
    repo_texts = []
    for idx, r in enumerate(repos, 1):
        text = f"{idx}. 项目名: {r['name']}\n"
        text += f"   英文描述: {r['description'] or '无'}\n"
        if r.get("topics"):
            text += f"   标签: {r['topics']}\n"
        if r.get("language"):
            text += f"   主要语言: {r['language']}\n"
        if r.get("readme"):
            text += f"   README 摘要: {r['readme'][:400]}\n"
        repo_texts.append(text)

    prompt = (
        "你是一个专门给中国小白用户介绍 GitHub 开源项目的中文技术博主。\n\n"
        "任务：根据下面每个项目的英文名、描述和 README 摘要，写一段地道的中文介绍。\n\n"
        "严格要求（必须遵守）：\n"
        "1. 必须用纯中文输出，不允许出现任何英文单词、英文句子、英文缩写。\n"
        "2. 每个项目写 2-3 句话，40-60 个汉字。\n"
        "3. 介绍要自然多样，不能每句都以‘就像’‘好比’‘相当于’开头。\n"
        "4. 可以换着这样开头：直接说功能、讲一个使用场景、用‘简单来说’‘说白了就是’‘它能帮你’等。\n"
        "5. 第一句说它是干什么的，第二句说它能解决什么问题或适合谁用。\n"
        "6. 不要专业术语，不要‘赋能’‘抓手’‘闭环’这类空话。\n"
        "7. 输出格式必须是 JSON，键是项目全名，值是中文介绍。\n\n"
        + "\n".join(repo_texts)
        + "\n\n请严格按照以下 JSON 格式返回，不要有任何额外解释，键必须是项目全名：\n"
        + "{\"owner/repo\": \"40-60字的地道中文介绍\", ...}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是中文开源项目介绍助手，只输出纯中文 JSON，绝对不允许出现英文。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 3000,
    }

    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode("utf-8", errors="ignore"))
        content = resp["choices"][0]["message"]["content"]
        print(f"[DEBUG] AI raw response preview: {content[:800]}")

        summaries = {}
        # 尝试提取 JSON 代码块
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if code_block:
            try:
                summaries = json.loads(code_block.group(1).strip())
            except Exception:
                pass

        # 尝试直接提取 JSON 对象
        if not summaries:
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                try:
                    summaries = json.loads(json_match.group())
                except Exception:
                    pass

        print(f"[DEBUG] parsed {len(summaries)} summaries, keys: {list(summaries.keys())[:10]}")

        # 保证每个项目都有值，支持模糊匹配
        result = {}
        for r in repos:
            name = r["name"]
            summary = summaries.get(name, "")
            # 模糊匹配: 后半部分名称
            if not summary:
                short_name = name.split("/")[-1]
                for k in summaries:
                    if k == short_name or k.endswith(f"/{short_name}"):
                        summary = summaries[k]
                        break
            # 如果仍然没有，用中文通用允底
            if not summary or not isinstance(summary, str):
                summary = "这个项目本周升幅不错，可以点击名字看看是不是你想要的工具。"
            result[name] = summary
        return result
    except Exception as e:
        print(f"[WARN] AI summary failed: {e}")
        return {r["name"]: "本周热门开源项目，点击名字查看详情。" for r in repos}


def format_message(rows, summaries, week_date):
    """\u751f\u6210\u9ad8\u7ea7 HTML \u6d3e\u9001\u6392\u7248."""
    formatted_date = f"{week_date[:4]}.{week_date[4:6]}.{week_date[6:8]}"

    cards = []
    for r in rows[:20]:
        intro = summaries.get(r["name"], "\u6682\u65e0\u4ecb\u7ecd")
        # \u79fb\u9664\u53ef\u80fd\u7684 markdown \u94fe\u63a5\uff0c\u9632\u6b62 HTML \u6e32\u67d3\u95ee\u9898
        intro = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", intro)
        intro = intro.replace("\n", " ")
        growth_num = r["growth"].replace("\u2b07\ufe0f", "").replace("\u2b06\ufe0f", "").replace("\u2b07", "").replace("\u2b06", "").replace("\ufe0f", "")
        cards.append(
            f'  <div class="card">\n'
            f'    <div class="rank">{r["rank"]}</div>\n'
            f'    <div class="content">\n'
            f'      <a href="{r["url"]}" class="repo-name">{r["name"]}</a>\n'
            f'      <div class="meta">\n'
            f'        <span class="stars">{r["stars"]} stars</span>\n'
            f'        <span class="growth">{growth_num}</span>\n'
            f'      </div>\n'
            f'      <p class="desc">{intro}</p>\n'
            f'    </div>\n'
            f'  </div>'
        )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  body{{margin:0;padding:0;background:#0c0c0e;font-family:'Geist',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;-webkit-font-smoothing:antialiased;}}
  .wrap{{max-width:720px;margin:0 auto;padding:48px 24px;}}
  .hero{{position:relative;background:linear-gradient(160deg,#18181c 0%,#111114 60%,#0d0d0f 100%);border:1px solid rgba(255,255,255,0.06);border-radius:32px;padding:42px 36px;margin-bottom:32px;overflow:hidden;}}
  .hero::before{{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.12),transparent);}}
  .kicker{{font-size:11px;font-weight:700;letter-spacing:0.22em;color:#6b7280;text-transform:uppercase;margin-bottom:16px;}}
  .hero h1{{margin:0;font-size:42px;font-weight:800;color:#fafafa;letter-spacing:-0.04em;line-height:1.05;}}
  .hero p{{margin:14px 0 0 0;font-size:16px;color:#9ca3af;font-weight:500;max-width:480px;}}
  .card{{position:relative;background:#141417;border:1px solid rgba(255,255,255,0.05);border-radius:24px;padding:26px;margin-bottom:16px;display:flex;gap:20px;align-items:flex-start;}}
  .card::after{{content:'';position:absolute;top:0;left:24px;right:24px;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.06),transparent);}}
  .rank{{font-size:38px;font-weight:800;color:#10b981;line-height:1;min-width:48px;text-align:left;letter-spacing:-0.05em;}}
  .content{{flex:1;min-width:0;}}
  .repo-name{{font-size:18px;font-weight:700;color:#f3f4f6;margin-bottom:8px;text-decoration:none;display:block;letter-spacing:-0.01em;}}
  .meta{{display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap;}}
  .stars{{font-size:13px;font-weight:600;color:#6b7280;}}
  .growth{{font-size:12px;font-weight:700;color:#10b981;background:rgba(16,185,129,0.08);padding:5px 11px;border-radius:100px;border:1px solid rgba(16,185,129,0.14);}}
  .desc{{margin:0;font-size:15px;color:#d1d5db;line-height:1.75;}}
  .footer{{text-align:center;padding:32px 0 0 0;}}
  .footer a{{color:#52525b;font-size:13px;text-decoration:none;font-weight:500;letter-spacing:0.01em;}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div class="kicker">GitHub Weekly Rank</div>
    <h1>\u6bcf\u5468\u98d9\u5347\u699c Top20</h1>
    <p>{formatted_date} \u671f \u00b7 \u7cbe\u9009\u672c\u5468\u6700\u503c\u5f97\u5173\u6ce8\u7684\u5f00\u6e90\u9879\u76ee</p>
  </div>
\n{chr(10).join(cards)}
  <div class="footer">
    <a href="https://github.com/OpenGithubs/github-weekly-rank">\u6570\u636e\u6765\u6e90: OpenGithubs/github-weekly-rank</a>
  </div>
</div>
</body>
</html>"""
    return html


def push_to_pushplus(token, title, content):
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": "html",
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

    print("[INFO] fetching repo details...")
    repos = []
    for r in rows[:20]:
        detail = fetch_repo_details(r["name"])
        if detail:
            repos.append(detail)
        else:
            repos.append({"name": r["name"], "description": "", "topics": "", "language": "", "readme": ""})

    print("[INFO] generating AI summaries...")
    summaries = summarize_with_ai(repos)

    msg = format_message(rows, summaries, week_date)
    title = f"GitHub 每周飙升榜 ({week_date})"
    push_to_pushplus(token, title, msg)
    print("[INFO] 推送完成")


if __name__ == "__main__":
    main()
