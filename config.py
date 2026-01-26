# config.py - IPTV直播源处理配置文件

# 模板文件路径（相对路径）
TEMPLATE_FILE = "demo.txt"

# ===================== 测速配置 =====================
# 延迟阈值（ms），超过该值仍保留但标注延迟
LATENCY_THRESHOLD = 500
# 异步并发数（根据服务器性能调整）
CONCURRENT_LIMIT = 20
# 超时时间（s）
TIMEOUT = 20
# 重试次数
RETRY_TIMES = 2
#频道匹配阈值（默认 0.4）
MATCH_CUTOFF=0.6
# IP版本优先级（ipv4/ipv6）
IP_VERSION_PRIORITY = "ipv4"


# ===================== 核心源配置 =====================
# 直播源URL列表（支持GitHub RAW/普通HTTP链接）
SOURCE_URLS = [
    # 替换为你自己的直播源链接

    

    "https://github.com/develop202/migu_video/blob/main/interface.txt",
    "https://github.com/cyh92/iptv-api-weishi/blob/master/output/weishi.m3u",
    "https://github.com/cyh92/iptv-api-cctv/blob/master/output/cctv.m3u",
   "https://github.com/8080713/iptv-api666/blob/main/output/result.m3u",
   "https://raw.githubusercontent.com/iptv-org/iptv/gh-pages/countries/cn.m3u",
   "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
    "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
    "https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/others_output.txt",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv6.txt",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt",
    "https://live.hacks.tools/tv/iptv4.txt",
   "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv6.m3u",
    # 其他源链接...
]
source_urls = [
    # 替换为你自己的直播源链接

    

    "https://github.com/develop202/migu_video/blob/main/interface.txt",
    "https://github.com/cyh92/iptv-api-weishi/blob/master/output/weishi.m3u",
    "https://github.com/cyh92/iptv-api-cctv/blob/master/output/cctv.m3u",
   "https://github.com/8080713/iptv-api666/blob/main/output/result.m3u",
   "https://raw.githubusercontent.com/iptv-org/iptv/gh-pages/countries/cn.m3u",
   "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
    "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
    "https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/others_output.txt",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv6.txt",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt",
    "https://live.hacks.tools/tv/iptv4.txt",
   "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv6.m3u",
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
GITHUB_LOGO_BASE_URL = "https://raw.githubusercontent.com/fanmingming/live/main/tv"
# 备用台标URL（GHProxy）
BACKUP_LOGO_BASE_URL = "https://ghproxy.com/https://raw.githubusercontent.com/fanmingming/live/main/tv"
# GitHub API URL（获取台标列表）
GITHUB_LOGO_API_URLS = [
    "https://api.github.com/repos/fanmingming/live/contents/main/tv",
    "https://ghproxy.com/https://api.github.com/repos/fanmingming/live/contents/main/tv"
]








