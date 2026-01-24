# config.py
# 基础配置
TEMPLATE_FILE = "demo.txt"
LATENCY_THRESHOLD = 500  # 延迟阈值（毫秒）
CONCURRENT_LIMIT = 20    # 并发测速限制
TIMEOUT = 10             # 超时时间（秒）
RETRY_TIMES = 2          # 重试次数
IP_VERSION_PRIORITY = "ipv4"

# 源URL配置
source_urls = [
    "https://raw.kkgithub.com/develop202/migu_video/main/interface.txt",
    "https://github.com/cyh92/iptv-api-weishi/blob/master/output/weishi.m3u",
    "https://github.com/cyh92/iptv-api-cctv/blob/master/output/cctv.m3u",
    "https://github.com/8080713/iptv-api666/blob/main/output/result.m3u",
    "https://raw.githubusercontent.com/Guovin/iptv-database/master/result.txt",
    "https://raw.githubusercontent.com/iptv-org/iptv/gh-pages/countries/cn.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
    "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
    "https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/others_output.txt",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv6.txt",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt",
    "https://live.hacks.tools/tv/iptv6.txt",
    "https://live.hacks.tools/tv/iptv4.txt",
    "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv6.m3u",


 
]

# 黑名单配置
url_blacklist = ["example.com/bad", "192.168.0.1"]

# EPG配置
epg_urls = ["https://epg.51zmt.top:8000/e.xml"]

# 公告配置
announcements = [
    {
        "channel": "公告",
        "entries": [
            {
                "name": "测试公告",
                "url": "https://example.com/notice.m3u8",
                "logo": "https://example.com/logo.png"
            }
        ]
    }
]






