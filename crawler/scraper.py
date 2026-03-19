import requests
import json
import os
import re
from datetime import datetime, timedelta

# ================= 配置区域 =================
# 获取脚本所在目录，确保 crontab 运行时路径正确
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", SCRIPT_DIR)

# wewe-rss 服务的地址（Docker 中通过 WEWE_RSS_URL 配置）
BASE_URL = os.environ.get("WEWE_RSS_URL", "http://localhost:4000")
# 获取所有订阅源的 JSON Feed 接口 (增加 limit 参数以获取更多历史文章)
FEED_URL = f"{BASE_URL}/feeds/all.json?limit=500"
# 结果存储文件
OUTPUT_FILE = os.path.join(DATA_DIR, "wechat_data_archive.json")
# 日志文件
LOG_FILE = os.path.join(DATA_DIR, "scraper.log")

# 过滤配置：仅获取最近多久的文章 (单位：小时)
# 设置为 24 代表仅获取过去 24 小时发布的内容；设置为 None 则不限制
FETCH_SINCE_HOURS = 48 
# ===========================================

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{timestamp}] {message}"
    print(full_msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(full_msg + "\n")

def clean_html(html_content):
    if not html_content:
        return ""
    # 去除脚本和样式
    clean = re.sub(r'<(script|style).*?>.*?</\1>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    # 去除所有标签
    clean = re.sub(r'<.*?>', '', clean)
    # 处理实体字符 (简单处理)
    clean = clean.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    # 去除多余换行
    clean = re.sub(r'\n\s*\n', '\n', clean).strip()
    return clean

def fetch_wechat_articles():
    log(f"开始抓取任务 (过滤范围: 最近 {FETCH_SINCE_HOURS if FETCH_SINCE_HOURS else '所有'} 小时)")
    
    # 计算时间阈值
    since_threshold = None
    if FETCH_SINCE_HOURS:
        since_threshold = datetime.now() - timedelta(hours=FETCH_SINCE_HOURS)

    try:
        response = requests.get(FEED_URL, timeout=60)
        response.raise_for_status()
        feed_data = response.json()
    except Exception as e:
        log(f"错误: 无法获取数据 - {e}")
        return

    items = feed_data.get('items', [])
    log(f"接口返回文章总数: {len(items)}")

    # 加载已有的数据
    existing_data = []
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        except Exception as e:
            log(f"警告: 读取现有数据失败 - {e}")
            existing_data = []

    # 使用 URL 作为唯一标识进行去重
    existing_urls = {article['url'] for article in existing_data if 'url' in article}
    
    new_count = 0
    filtered_count = 0
    for item in items:
        url = item.get('url')
        if not url: continue
        
        # 检查发布时间
        publish_time_str = item.get('date_published') or item.get('date_modified')
        is_recent = True
        
        if since_threshold and publish_time_str:
            try:
                # 处理 ISO 格式 (兼容 Z 结尾或 +08:00 结尾)
                p_time = datetime.fromisoformat(publish_time_str.replace('Z', '+00:00'))
                # 统一转为无时区进行比较或转为当前系统时区
                if p_time.tzinfo:
                    p_time = p_time.replace(tzinfo=None) # 这里简化处理，视具体环境而定
                
                if p_time < since_threshold:
                    is_recent = False
            except:
                pass # 时间解析失败则默认不过滤

        if not is_recent:
            filtered_count += 1
            continue

        if url not in existing_urls:
            content_html = item.get('content_html', '')
            
            # 提取关心的字段
            article = {
                "title": item.get('title'),
                "author": item.get('author', {}).get('name') if isinstance(item.get('author'), dict) else item.get('author'),
                "publish_time": publish_time_str,
                "url": url,
                "cover_image": item.get('image') or item.get('banner_image'),
                "content_text": clean_html(content_html),
                "summary": item.get('summary'),
                "archive_time": datetime.now().isoformat()
            }
            existing_data.append(article)
            new_count += 1
            existing_urls.add(url)

    msg = f"处理完成。新增: {new_count} 篇"
    if filtered_count > 0:
        msg += f"，因时间范围过滤: {filtered_count} 篇"
    log(msg)

    if new_count > 0:
        # 按发布时间倒序排列
        existing_data.sort(key=lambda x: x.get('publish_time') or '', reverse=True)
        
        try:
            temp_file = OUTPUT_FILE + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, OUTPUT_FILE)
            log(f"总计归档文章: {len(existing_data)} 篇。")
        except Exception as e:
            log(f"错误: 保存数据工作失败 - {e}")

if __name__ == "__main__":
    fetch_wechat_articles()
