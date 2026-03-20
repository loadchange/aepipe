# aepipe

**部署在边缘的日志管道，人人可用。**

基于 Cloudflare Workers + Analytics Engine 构建的高性能日志网关 —— 你的**免费版 SLS**，以 **$0 成本**彻底终结阿里云、AWS、GCP 的高昂日志账单。

## 为什么选 aepipe？

在 2026 年，日志服务不该成为你月度账单里的"刺客"。aepipe 重新定义了日志采集与分析的性价比。

### 降维打击：对比云巨头

| | 阿里云 SLS | AWS CloudWatch | GCP Cloud Logging | **aepipe** |
|---|---|---|---|---|
| **计费逻辑** | 索引费 + 流量费 + 存储费 | 写入费 ($0.50/GB) + 查询费 | 注入费 ($0.50/GB) | **$0**（基于 CF 免费额度） |
| **查询语法** | SQL（需开启索引） | 专用 Insights 语法 | 专用 LQL 语法 | **原生 SQL**（AE 驱动） |
| **部署成本** | 需安装/配置 Logtail | 需配置 CloudWatch Agent | 需配置日志路由器 | **Serverless 零部署，一键即开** |
| **全球接入** | 受限于物理 Region | 受限于物理 Region | 受限于物理 Region | **全球 300+ 边缘节点就近写入** |
| **数据主权** | 厂商托管 | 厂商托管 | 厂商托管 | **100% 归你**（你的 CF 账号） |
| **多租户** | 按项目计费 | 按日志组计费 | 按项目计费 | **无限项目，$0** |

### 核心价值

**1. 真正的"免费版 SLS"** —— 利用 Cloudflare Analytics Engine 的底层能力，绕过传统云厂商按"扫描量"或"索引量"收割用户的套路。在 Cloudflare 免费层级内，享受极高并发的日志注入与实时分析。

**2. 极致简单的"日志漏斗"** —— 不再需要配置复杂的正则表达式和字段映射。动态 Schema 映射：JSON 往管道里一扔，自动变成可供 SQL 查询的结构化数据。

**3. 跨云兼容的日志桥梁** —— 不管你的应用跑在 AWS EC2、阿里云函数计算，还是家里的树莓派上，只需一个 HTTP POST，日志瞬间飞往全球边缘节点，化为可查询的结构化指标。

**4. 拒绝"账单焦虑"** —— 代码完全开源，部署在你自己的 Cloudflare 账号下。没有隐藏计费，没有闭源黑盒，一切数据主权归你。

## 工作原理

```
你的应用 ──POST JSON──▶ aepipe (CF Worker) ──writeDataPoint()──▶ Analytics Engine
                                                                        │
                                                                   SQL API ◀── 你
```

事件按 **Project** 和 **LogStore** 隔离 —— 一次部署服务多个团队/应用：

```
aepipe 实例
  └── Project（顶层租户）
        └── LogStore（项目内的日志分类）
```

无需外部数据库。Project 和 LogStore 是隐式的，首次写入即创建，通过 SQL 查询发现。

## 部署步骤

### 1. 安装依赖

```bash
npm install
```

### 2. 配置

编辑 `wrangler.toml`，自定义 dataset 名称：

```toml
name = "aepipe"
main = "src/index.ts"
compatibility_date = "2025-04-01"

[[analytics_engine_datasets]]
binding = "LOGS"
dataset = "aepipe"
```

### 3. 设置密钥

```bash
npx wrangler secret put ADMIN_TOKEN       # 所有 API 操作的鉴权 token
npx wrangler secret put CF_ACCOUNT_ID     # Cloudflare 账户 ID（查询 API 使用）
npx wrangler secret put CF_API_TOKEN      # CF API token，需有 Analytics Engine 读取权限
```

### 4. 部署

```bash
npm run deploy
```

## API

所有接口需要 `Authorization: Bearer <ADMIN_TOKEN>` 请求头。

Project 和 LogStore 名称须匹配 `^[a-zA-Z0-9_-]{1,64}$`。

### 写入 — `POST /v1/{project}/{logstore}/ingest`

```bash
curl -X POST https://aepipe.<subdomain>.workers.dev/v1/my-app/access-log/ingest \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "points": [
      {
        "event": "GET /api/users",
        "level": "info",
        "blobs": ["200", "us-east"],
        "doubles": [42.5]
      }
    ]
  }'
```

**响应：** `{ "ok": true, "written": 1 }`

**约束：**
- `points` 必须是非空数组，每次请求最多 250 个
- `event` 缺失或为空的数据点会被静默跳过

### 查询 — `POST /v1/{project}/{logstore}/query`

```bash
curl -X POST https://aepipe.<subdomain>.workers.dev/v1/my-app/access-log/query \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT blob3 AS event, blob4 AS level FROM aepipe WHERE timestamp > NOW() - INTERVAL '\''1'\'' HOUR ORDER BY timestamp DESC LIMIT 100"
  }'
```

Worker 会自动注入 `blob1 = '{project}' AND blob2 = '{logstore}'` 到 WHERE 子句，防止跨租户读取。

### 列出项目 — `GET /v1/projects`

```bash
curl https://aepipe.<subdomain>.workers.dev/v1/projects \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

**响应：** `{ "projects": ["my-app", "backend-svc"] }`

### 列出 LogStore — `GET /v1/{project}/logstores`

```bash
curl https://aepipe.<subdomain>.workers.dev/v1/my-app/logstores \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

**响应：** `{ "logstores": ["access-log", "error-log"] }`

## 数据点映射

| AE 字段 | 内容 | 说明 |
|----------|------|------|
| `index1` | `{project}/{logstore}` | 采样键 |
| `blob1` | 项目名称 | 租户过滤 |
| `blob2` | LogStore 名称 | 子租户过滤 |
| `blob3` | event（必填） | 用户的事件字符串 |
| `blob4` | level | 默认 "info" |
| `blob5`–`blob20` | 用户 `blobs[0..15]` | 最多 16 个额外 blob，每个 <=16KB |
| `double1`–`double20` | 用户 `doubles[0..19]` | 最多 20 个 double |

## 错误响应

| 状态码 | 响应体 |
|--------|--------|
| 400 | `{ "error": "..." }` — JSON 无效、名称不合法、数据点为空等 |
| 401 | `{ "error": "unauthorized" }` |
| 404 | `{ "error": "not found" }` |
| 502 | `{ "error": "CF API ..." }` — 上游查询失败 |

## 本地开发

```bash
npm run dev      # 本地开发服务器 (wrangler dev)
npm run deploy   # 部署到 Cloudflare
npm run tail     # 实时查看日志流
```

## 许可证

MIT
