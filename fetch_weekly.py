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
        "你是一个技术博主，专门把 GitHub 上的英文开源项目用通俗易懂的中文"
        "介绍给普通用户。对每个项目用 1 句话说清楚："
        "它是干什么的，能解决什么问题，为什么值得关注。\n\n"
        + "\n".join(repo_texts)
        + "\n\n请严格按照以下 JSON 格式返回，不要有任何额外解释：\n"
        + "{\"项目名\": \"一句话中文介绍\", ...}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是开源项目中文介绍助手，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 2000,
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
        print(f"[INFO] AI raw response preview: {content[:500]!r}")

        summaries = {}
        # 尝试提取 JSON 代码块
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if code_block:
            try:
                summaries = json.loads(code_block.group(1).strip())
                print("[INFO] parsed JSON from code block")
            except Exception as e:
                print(f"[WARN] code block JSON parse failed: {e}")

        # 尝试直接提取 JSON 对象
        if not summaries:
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                try:
                    summaries = json.loads(json_match.group())
                    print("[INFO] parsed JSON from object")
                except Exception as e:
                    print(f"[WARN] object JSON parse failed: {e}")

        # 保证每个项目都有值，没有的话使用英文 description 回退
        result = {}
        print(f"[INFO] parsed summaries keys: {list(summaries.keys())}")
        for r in repos:
            name = r["name"]
            summary = summaries.get(name, "")
            print(f"[DEBUG] lookup '{name}' -> found={bool(summary)}")
            if not summary or not isinstance(summary, str):
                summary = r.get("description") or "暂无介绍"
            result[name] = summary
        return result
    except Exception as e:
        print(f"[WARN] AI summary failed: {e}")
        return {r["name"]: (r.get("description") or "（AI 摘要失败）") for r in repos}


def format_message(rows, summaries, week_date):
    lines = [f"## GitHub 每周飙升榜 Top20 ({week_date})", ""]
    for r in rows[:20]:
        intro = summaries.get(r["name"], "暂无介绍")
        lines.append(f"{r['rank']}. [{r['name']}]({r['url']})")
        lines.append(f"   ⭐ {r['stars']} | {r['growth']}")
        lines.append(f"   💡 {intro}")
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
    print(f"[INFO] message preview (first 1500 chars):\n{msg[:1500]}")
    title = f"GitHub 每周飙升榜 ({week_date})"
    push_to_pushplus(token, title, msg)
    print("[INFO] 推送完成")


if __name__ == "__main__":
    main()
