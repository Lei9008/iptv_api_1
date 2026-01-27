# config.py - IPTV直播源处理配置文件
TEMPLATE_FILE = "demo.txt"

# ===================== 核心配置（高清优先） =====================
QUALITY_FIRST = True
HD_LATENCY_BONUS = 400
MIN_HD_CHANNELS = 80
MATCH_CUTOFF = 0.5

# ===================== 测速配置 =====================
LATENCY_THRESHOLD = 800
CONCURRENT_LIMIT = 40
TIMEOUT = 15
RETRY_TIMES = 2
IP_VERSION_PRIORITY = "ipv4"

# ===================== 核心源配置 =====================
SOURCE_URLS = [
    "https://raw.githubusercontent.com/develop202/migu_video/main/interface.txt",
    #"https://raw.githubusercontent.com/cyh92/iptv-api-cctv/master/output/cctv.m3u",
    #"https://raw.githubusercontent.com/cyh92/iptv-api-weishi/master/output/weishi.m3u"
]

# ===================== 过滤配置 =====================
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
    "8.210.140.75:68",
    "154.12.50.54",
    "yinhe.live_hls.zte.com",
    "8.137.59.151",
    "histar.zapi.us.kg",
    "www.tfiplaytv.vip",
    "dp.sxtv.top",
    "111.230.30.193",
    "148.135.93.213:81",
    "live.goodiptv.club",
    "iptv.luas.edu.cn",
    "stream1.freetv.fun",
    "gaoma"
]

# ===================== EPG配置 =====================
EPG_URLS = [
    "https://epg.v1.mk/fy.xml",
    "http://epg.51zmt.top:8000/e.xml",
    "https://epg.pw/xmltv/epg_CN.xml",
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
GITHUB_LOGO_BASE_URL = "https://raw.githubusercontent.com/fanmingming/live/main/tv"
BACKUP_LOGO_BASE_URL = "https://ghproxy.com/https://raw.githubusercontent.com/fanmingming/live/main/tv"
GITHUB_LOGO_API_URLS = [
    "https://api.github.com/repos/fanmingming/live/contents/main/tv",
    "https://ghproxy.com/https://api.github.com/repos/fanmingming/live/contents/main/tv"
]

# ===================== 其他配置 =====================
PROGRESS_INTERVAL = 50
