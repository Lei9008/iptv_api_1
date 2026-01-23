# config.py
# 源配置
source_urls = [
    "https://gh-proxy.com/raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
    "https://github.com/liuchuang0321/K-TV/blob/master/output/user_result.txt",
    # 可添加更多源
]
url_blacklist = ["example.com", "invalid.url"]  # URL黑名单
ip_version_priority = "ipv4"  # IP优先级：ipv4/ipv6
TEMPLATE_FILE = "demo.txt"

# 测速配置
LATENCY_THRESHOLD = 500  # 延迟阈值（毫秒）
CONCURRENT_LIMIT = 20    # 并发测速限制
TIMEOUT = 10             # 超时时间（秒）
RETRY_TIMES = 2          # 重试次数

# 扩展配置
epg_urls = ["https://epg.51zmt.top:8000/e.xml"]  # EPG地址
announcements = [
    {
        "channel": "公告",
        "entries": [
            {"name": "更新时间", "url": "https://example.com/notice.m3u8", "logo": ""}
        ]
    }
]


