# daily-brief-actions — 每日情报简报自动构建与部署

GitHub Actions 每天 08:00（北京时间）自动抓取 RSS 资讯、生成五板块单文件 HTML 简报（密码保护 + 历史翻阅），并部署到 Cloudflare Pages。

## 仓库结构

```
.
├── .github/workflows/deploy.yml   # cron 定时 + 手动 + push 触发
├── scripts/build_brief.py         # 采集 + 分类 + 生成 HTML（单脚本）
├── data/briefs.json               # 历史日期数组（运行时生成，自动 commit）
└── public/index.html              # 构建产物（部署目录）
```

## 首次配置

1. 创建 GitHub 仓库并推送本目录代码。
2. 在仓库 Settings → Secrets and variables → Actions 中添加两个 secret：
   - `CLOUDFLARE_API_TOKEN`：Cloudflare API Token（权限须含 Account · Cloudflare Pages · Edit）
   - `CLOUDFLARE_ACCOUNT_ID`：Cloudflare 账户 ID
3. Workflow 已配置 cron `0 0 * * *`（北京时间 08:00）；也可在 Actions 页面手动 Run workflow，或 push 触发部署。

## 本地试运行

```bash
cd scripts
pip install feedparser
python build_brief.py --date 20260814 --out ../public/index.html --briefs-json ../data/briefs.json
```

## 说明

- 简报页面固定密码 `123567`（build_brief.py 顶部 PASSWORD 变量可改）。
- 板块：科技速览 / TikTok 趋势 / 电商动态 / 加密货币 / 副业机会。
- 采集源均为公开 RSS（IT之家 / 36氪 / 少数派 / 阮一峰 / Odaily / CoinDesk），国内网络可直连。
- 每次运行将当日日期写入 `data/briefs.json` 并自动提交，页面内置 BRIEFS 数组实现历史翻阅。
