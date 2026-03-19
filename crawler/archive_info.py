import json
import os
from collections import Counter
from datetime import datetime

# ================= 配置区域 =================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_FILE = os.path.join(SCRIPT_DIR, "wechat_data_archive.json")
# ===========================================

def show_archive_info():
    if not os.path.exists(ARCHIVE_FILE):
        print(f"错误: 存档文件 {ARCHIVE_FILE} 不存在。请先运行 scraper.py")
        return

    with open(ARCHIVE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total_count = len(data)
    if total_count == 0:
        print("存档为空。")
        return

    # 按作者统计
    authors = [item.get('author') or "未知" for item in data]
    author_counts = Counter(authors)

    # 排序：按文章数量倒序
    sorted_authors = author_counts.most_common()

    # 获取最近更新时间 (archive_time)
    last_archive = max([item.get('archive_time', '') for item in data])
    
    print("=" * 40)
    print("微信文章存档 概况汇报")
    print("-" * 40)
    print(f"总计归档文章: {total_count} 篇")
    print(f"最近抓取时间: {last_archive}")
    print("-" * 40)
    print("文章来源分布:")
    for author, count in sorted_authors:
        print(f"  - {author}: {count} 篇")
    print("=" * 40)

if __name__ == "__main__":
    show_archive_info()
