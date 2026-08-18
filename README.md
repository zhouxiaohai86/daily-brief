# daily-brief-actions — 每日情报简报生成与发布

每日情报简报：单文件 HTML（密码保护 + 历史翻阅），内容为人工/Agent 精编版，部署到 Cloudflare Pages。CI 已停用自动构建（仅 workflow_dispatch 手动触发），部署以本地磁盘 `public/index.html` 为准，用 wrangler 直发。

## 仓库结构

```
.
├── .github/workflows/deploy.yml   # 仅 workflow_dispatch 手动触发（防自动覆盖精编版）
├── scripts/build_brief.py         # 自动聚合版构建（仅作参考，禁止覆盖精编版；有 is_protected_target 熔断）
├── scripts/check_briefs.py        # 自检脚本（本地 + 线上，防历史翻阅失效/精编版被覆盖）
├── scripts/publish_daily.py       # ★ 一键发布：插入当日内容 → 自检 → 部署 → 复检
└── public/index.html              # 构建产物（部署目录，.gitignore 忽略，以磁盘为准）
```

## 每日发布流程（一键）

生成当日精编版内容 HTML（五板块正文 body）后，执行：

```powershell
$env:CLOUDFLARE_API_TOKEN = "<token>"
$env:CLOUDFLARE_ACCOUNT_ID = "<account_id>"
python scripts/publish_daily.py --content <当日内容.html> [--date 2026-08-18] [--label "2026年8月18日 · 星期二"]
```

脚本自动完成四步，任一步失败即中止：

1. 插入：替换 `mainContent` 为当日内容；BRIEFS 追加/更新当日条目；默认展示期切到当日
2. 本地自检：`check_briefs.py` 校验 renderBrief、各期内容、默认期标记、无自动聚合特征
3. 部署：后台运行 `npx wrangler pages deploy public --project-name=daily-brief --branch=main`（API Token 认证，防交互挂起），轮询输出
4. 复检：再次运行自检（本地 + 线上）

`--date` 默认当天（UTC+8），`--label` 默认自动生成中文日期。`--skip-deploy` 只做插入+自检。

## 自检脚本

```powershell
python scripts/check_briefs.py                          # 默认校验本地 public/index.html + 线上 daily-brief-7gf.pages.dev
python scripts/check_briefs.py --url <线上域名>          # 指定线上地址
```

## 首次配置

1. 创建 GitHub 仓库并推送本目录代码。
2. Cloudflare 部署凭证（不写入仓库/README）：
   - `CLOUDFLARE_API_TOKEN`：Cloudflare API Token（权限须含 Account · Cloudflare Pages · Edit）
   - `CLOUDFLARE_ACCOUNT_ID`：Cloudflare 账户 ID
3. Workflow 已改为仅手动触发（防自动版覆盖精编版）。

## 说明

- 简报页面固定密码 `123567`。
- 板块：科技速览 / TikTok 趋势 / 电商动态 / 加密货币 / 副业机会。
- 页面内置 BRIEFS 数组实现历史翻阅；默认展示最新精编期。
*（内容由AI生成，仅供参考）*
