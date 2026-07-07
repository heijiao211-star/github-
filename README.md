# GitHub Weekly Rank Push

自动抓取 [OpenGithubs/github-weekly-rank](https://github.com/OpenGithubs/github-weekly-rank) 的每周飙升榜，并通过 [PushPlus](https://www.pushplus.plus) 推送到微信。

## 定时规则

- GitHub Actions 每周二上午 9:00 （北京时间）自动执行
- 源仓库每周一早上 8:00 更新，选择周二推送确保有最新数据

## 环境变量

在本仓库 Settings -> Secrets and variables -> Actions 中添加：

- `PUSHPLUS_TOKEN`：PushPlus 的 Token

## 手动触发

进入 Actions 选项卡 -> GitHub Weekly Rank Push -> Run workflow

## 本地运行

```bash
export PUSHPLUS_TOKEN="your_token"
python fetch_weekly.py
```
