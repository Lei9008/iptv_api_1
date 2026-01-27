# config.py - IPTV直播源处理配置文件
# 修复语法错误 + 规范变量定义

# 模板文件路径（相对路径）
TEMPLATE_FILE = "demo.txt"

# ===================== 测速配置 =====================
# 延迟阈值（ms），超过该值仍保留但标注延迟
LATENCY_THRESHOLD = 450
# 异步并发数（根据服务器性能调整）
CONCURRENT_LIMIT = 10
# 超时时间（s）
TIMEOUT = 8
# 重试次数
RETRY_TIMES = 2
# 频道匹配阈值（默认 0.4）
MATCH_CUTOFF = 0.8
# IP版本优先级（ipv4/ipv6）
IP_VERSION_PRIORITY = "ipv4"

# ===================== 核心源配置 =====================
# 直播源URL列表（支持GitHub RAW/普通HTTP链接）
SOURCE_URLS = [
    # 替换为你自己的直播源链接
    "https://github.com/develop202/migu_video/blob/main/interface.txt",
    

 
    
    # 其他源链接...
]

# ===================== 过滤配置 =====================
# URL黑名单（包含以下关键词的URL会被过滤）
URL_BLACKLIST = [
    "https://iptv.catvod.com/",
    "http://38.75.136.137:98/gslb/dsdqca",
    "https://migu.188766.xyz",
    "https://epg.pw/stream/",
    "http://38.75.136.137:98/gslb/dsdqpub/scwshd",
    "https://www.freetv.top",
    "https://stream1.freetv.fun",
    "epg.pw/stream/",
    "103.40.13.71:12390",
    "[2409:8087:1a01:df::4077]/PLTV/",
    "http://[2409:8087:1a01:df::7005]:80/ottrrs.hl.chinamobile.com/PLTV/88888888/224/3221226419/index.m3u8",
    "http://[2409:8087:5e00:24::1e]:6060/000000001000/1000000006000233001/1.m3u8",
    "8.210.140.75:68",
    "154.12.50.54",
    "yinhe.live_hls.zte.com",
    "8.137.59.151",
    "[2409:8087:7000:20:1000::22]:6060",
    "histar.zapi.us.kg",
    "www.tfiplaytv.vip",
    "dp.sxtv.top",
    "111.230.30.193",
    "148.135.93.213:81",
    "live.goodiptv.club",
    "iptv.luas.edu.cn",
    "[2409:8087:2001:20:2800:0:df6e:eb22]:80",
    "[2409:8087:2001:20:2800:0:df6e:eb23]:80",
    "[2409:8087:2001:20:2800:0:df6e:eb1d]/ott.mobaibox.com/",
    "[2409:8087:2001:20:2800:0:df6e:eb1d]:80",
    "[2409:8087:2001:20:2800:0:df6e:eb24]",
    "2409:8087:2001:20:2800:0:df6e:eb25]:80",
    "stream1.freetv.fun",
    "chinamobile",
    "gaoma",
    "[2409:8087:2001:20:2800:0:df6e:eb27]"
]

# ===================== EPG配置 =====================
# 电子节目指南URL
EPG_URLS = [
    "https://epg.v1.mk/fy.xml",
    "http://epg.51zmt.top:8000/e.xml",
    "https://epg.pw/xmltv/epg_CN.xml",
    "https://epg.pw/xmltv/epg_HK.xml",
    "https://epg.pw/xmltv/epg_TW.xml",
    "https://raw.githubusercontent.com/plsy1/epg/main/e/seven-days.xml.gz",
    "https://live.fanmingming.cn/e.xml",
]

# ===================== 公告配置 =====================
ANNOUNCEMENTS = [
    {
        "channel": "公告栏",
        "entries": [
            {
                "name": "直播源更新时间",
                "url": "",
                "logo": "https://raw.githubusercontent.com/fanmingming/live/main/tv/公告.png"
            },
            {
                "name": "使用说明",
                "url": "",
                "logo": "https://raw.githubusercontent.com/fanmingming/live/main/tv/说明.png"
            }
        ]
    }
]

# ===================== 台标配置 =====================
# GitHub台标仓库基础URL
GITHUB_LOGO_BASE_URL = "https://live.fanmingming.cn/tv/{name}.png"
# 备用台标URL（GHProxy）
BACKUP_LOGO_BASE_URL = "https://live.fanmingming.cn/tv/{name}.png"
# GitHub API URL（获取台标列表）
GITHUB_LOGO_API_URLS = [
    "https://live.fanmingming.cn/tv/{name}.png",
    "https://live.fanmingming.cn/tv/{name}.png"
]

# ===================== 其他配置 =====================
# 进度打印间隔（每处理N个URL打印一次进度）
PROGRESS_INTERVAL = 100
