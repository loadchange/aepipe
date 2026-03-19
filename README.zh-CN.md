# aepipe

一个轻量级 Cloudflare Worker，通过 HTTP 接收结构化事件并写入 [Workers Analytics Engine](https://developers.cloudflare.com/analytics/analytics-engine/)。

从任意后端发送 JSON，用 SQL 查询 —— 无需搭建日志聚合架构。

## 工作原理

```
你的应用 ──POST JSON──▶ aepipe (CF Worker) ──writeDataPoint()──▶ Analytics Engine
                                                                        │
                                                                   SQL API ◀── 你
```

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
dataset = "your-dataset-name"  # 改成你的
```

### 3. 设置鉴权 token

```bash
npx wrangler secret put INGEST_TOKEN
```

共享密钥，防止未授权写入。

### 4. 部署

```bash
npm run deploy
```

## 使用方式

### 写入数据点

```bash
curl -X POST https://aepipe.<your-subdomain>.workers.dev \
  -H "Authorization: Bearer <INGEST_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "points": [
      {
        "event": "order_placed",
        "level": "info",
        "index": "session-abc",
        "blobs": ["user-42", "us-east"],
        "doubles": [99.95, 3]
      }
    ]
  }'
```

**响应：**

```json
{ "ok": true, "written": 1 }
```

### SQL 查询

创建一个具有 **Account Analytics Read** 权限的 [API token](https://dash.cloudflare.com/profile/api-tokens)，然后：

```bash
curl "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/analytics_engine/sql" \
  -H "Authorization: Bearer <CF_API_TOKEN>" \
  -d "SELECT timestamp, blob1 AS event, blob2 AS level, double1
      FROM your-dataset-name
      WHERE blob2 = 'error'
      AND timestamp >= NOW() - INTERVAL '1' HOUR
      ORDER BY timestamp DESC
      LIMIT 50"
```

## 数据点结构

| 字段 | 类型 | 必填 | 映射到 |
|------|------|------|--------|
| `event` | string | **是** | `blob1` |
| `level` | string | 否（默认 `"info"`） | `blob2` |
| `index` | string | 否 | `index1`（采样键） |
| `blobs` | string[] | 否 | `blob3`, `blob4`, ... |
| `doubles` | number[] | 否 | `double1`, `double2`, ... |

**Analytics Engine 限制：** 最多 20 个 blob（每个 ≤ 16 KB）、20 个 double、1 个 index（≤ 96 字节）。

## API 参考

### `POST /`

将数据点写入 Analytics Engine。

**请求头：**
- `Authorization: Bearer <INGEST_TOKEN>`（必填）
- `Content-Type: application/json`

**请求体：**

```json
{
  "points": [
    {
      "event": "string（必填）",
      "level": "string",
      "index": "string",
      "blobs": ["string"],
      "doubles": [0.0]
    }
  ]
}
```

**约束：**
- `points` 必须是非空数组
- 每次请求最多 250 个数据点
- `event` 缺失或为空的数据点会被静默跳过

**响应：**

| 状态码 | 响应体 |
|--------|--------|
| 200 | `{ "ok": true, "written": N }` |
| 400 | `{ "error": "invalid json" }` / `{ "error": "points must be a non-empty array" }` / `{ "error": "max 250 points per request" }` |
| 401 | `{ "error": "unauthorized" }` |
| 405 | `{ "error": "method not allowed" }` |

## 本地开发

```bash
npm run dev      # 本地开发服务器 (wrangler dev)
npm run deploy   # 部署到 Cloudflare
npm run tail     # 实时查看日志流
```

## 许可证

MIT
