# wewe-rss 订阅源接口文档

本接口用于获取所有或特定公众号的文章列表。支持多种格式输出（RSS/JSON/Atom），并提供分页、关键词过滤及内容模式控制。

## 1. 基础信息

- **访问路径**: `/feeds/all.json` (对应 JSON Feed 格式)
- **支持格式**: `.json`, `.rss`, `.atom` (通过修改后缀切换)
- **请求方法**: `GET`

## 2. 查询参数 (Query Parameters)

以下参数可附加在 URL 后（如 `?limit=100&mode=fulltext`）：

| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `limit` | Integer | `30` | **返回条数**。控制单次请求返回的文章数量。 |
| `page` | Integer | `1` | **分页页码**。用于跳过前面的文章，加载更多历史。 |
| `mode` | String | `undefined` | **内容模式**。传 `fulltext` 则强制返回全文，否则遵循系统全局设置。 |
| `title_include`| String | `undefined` | **包含关键词**。仅返回标题包含此关键字的文章，支持 `|` 分隔（如 `AI|工具`）。 |
| `title_exclude`| String | `undefined` | **排除关键词**。过滤掉标题包含此关键字的文章，支持 `|` 分隔。 |

## 3. 字段说明 (以 JSON 格式为例)

接口返回的标准 JSON Feed 结构包含 `items` 数组，每个 item 的关键字段如下：

- `title`: 文章标题。
- `url`: 文章微信原始链接。
- `author`: 公众号名称。
- `date_published`: 发布时间 (ISO 8601)。
- `content_html`: 文章 HTML 全文（需开启全文模式）。
- `summary`: 文章摘要。
- `image`: 文章封面图链接。

## 4. 示例用法

- **获取最新的 100 篇 JSON 数据**:
  `GET /feeds/all.json?limit=100`

- **搜索标题包含 "DeepSeek" 的 RSS 订阅**:
  `GET /feeds/all.rss?title_include=DeepSeek`

- **获取第二页的 50 篇文章 (全文模式)**:
  `GET /feeds/all.json?limit=50&page=2&mode=fulltext`

---

> [!TIP]
> **关于数据源**: 接口返回的数据基于 `wewe-rss` 内部数据库中的已爬取文章。如果找不到历史文章，请先在管理后台点击该公众号的“获取历史文章”按钮。
