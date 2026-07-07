# GitHub Weekly Rank Push

自动抓取 [OpenGithubs/github-weekly-rank](https://github.com/OpenGithubs/github-weekly-rank) 的每周飙升榜，通过 AI 生成通俗中文介绍，再通过 [PushPlus](https://www.pushplus.plus) 推送到微信。

## 定时规则

- GitHub Actions 每周二上午 9:00 （北京时间）自动执行
- 源仓库每周一早上 8:00 更新，选择周二推送确保有最新数据

## 必填 Secret

在本仓库 Settings -> Secrets and variables -> Actions 中添加：

- `PUSHPLUS_TOKEN`：PushPlus 的 Token
- `AI_API_KEY`：AI 接口的 API Key

## 可选 Secret

- `AI_BASE_URL`：AI 接口基础地址，默认 `https://api.deepseek.com`
  - OpenRouter 用户填 `https://openrouter.ai/api/v1`
- `AI_MODEL`：模型名称，默认 `deepseek-chat`
  - OpenRouter 示例：`google/gemini-flash-1.5`
- `GH_TOKEN` / `GITHUB_TOKEN`：用于获取仓库 README，可以使用 GitHub 自动生成的 `GITHUB_TOKEN`，也可以不填

## AI 平台推荐

| 平台 | 推荐理由 | 配置示例 |
|---|---|---|
| DeepSeek | 国内、便宜、效果好 | `AI_BASE_URL=https://api.deepseek.com` `AI_MODEL=deepseek-chat` |
| OpenRouter | 模型多、支持支付宝 | `AI_BASE_URL=https://openrouter.ai/api/v1` `AI_MODEL=google/gemini-flash-1.5` |

## 手动触发

进入 Actions 选项卡 -> GitHub Weekly Rank Push -> Run workflow

## 本地运行

```bash
export PUSHPLUS_TOKEN="your_token"
export AI_API_KEY="your_ai_key"
# 可送
export AI_BASE_URL="https://api.deepseek.com"
export AI_MODEL="deepseek-chat"
python fetch_weekly.py
```

## 推送效果

每个项目包含：
- 排名 + 项目名 + 链接
- ⭐ Star 数 + 周增长
- 💡 一句话中文介绍（AI 生成）
