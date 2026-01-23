# config.py
# 源配置
source_urls = [
    "https://gh-proxy.com/raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
    "http://rihou.cc:555/gggg.nzk",
    "https://github.com/plsy1/iptv/blob/main/multicast/multicast-jinan.m3u",
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


"""""
# config.py
from pathlib import Path

# ===================== 基础路径配置 =====================
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
PIC_DIR = BASE_DIR / "pic"
LOG_FILE = OUTPUT_DIR / "speed_test.log"
TEMPLATE_FILE = BASE_DIR / "demo.txt"

# ===================== 源配置 =====================
# 可添加多个直播源URL（M3U/TXT格式）
SOURCE_URLS = [
    "https://gh-proxy.com/raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
    "http://rihou.cc:555/gggg.nzk",
    "https://github.com/plsy1/iptv/blob/main/multicast/multicast-jinan.m3u",
    # 可添加更多源地址
    
]

URL_BLACKLIST = ["example.com", "invalid.url"]  # URL黑名单
IP_VERSION_PRIORITY = "ipv4"  # IP优先级：ipv4/ipv6

# ===================== 测速配置 =====================
CONCURRENT_LIMIT = 20  # 并发测速限制
TIMEOUT = 10  # 超时时间（秒）
RETRY_TIMES = 2  # 重试次数
LATENCY_THRESHOLD = 550  # 延迟阈值（毫秒）
MAX_URLS_PER_CHANNEL = 10  # 每个频道保留的最大URL数量

# ===================== 扩展配置 =====================
EPG_URLS = []  # EPG地址
ANNOUNCEMENTS = []  # 公告频道
MATCH_CUTOFF = 0.4  # 频道名模糊匹配阈值（调低提高匹配率）
LOGO_BASE_URL = ""  # LOGO网络基础地址
"""""""
