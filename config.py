# config.py

# 其他原有配置...
LATENCY_THRESHOLD = 500 # 延迟阈值（毫秒）
CONCURRENT_LIMIT = 10   # 超时时间：20s
TIMEOUT = 10
RETRY_TIMES = 2
IP_VERSION_PRIORITY = "ipv4"
URL_BLACKLIST = []
TEMPLATE_FILE = "demo.txt"  # 模板文件


# 直播源链接配置
source_urls = [
   
    "https://github.com/develop202/migu_video/blob/main/interface.txt",
    "https://github.com/develop202/migu_video/blob/main/interface.txt",
   # "https://github.com/cyh92/iptv-api-weishi/blob/master/output/weishi.m3u",
   # "https://github.com/cyh92/iptv-api-cctv/blob/master/output/cctv.m3u",
   # "https://github.com/8080713/iptv-api666/blob/main/output/result.m3u",
   # "https://raw.githubusercontent.com/iptv-org/iptv/gh-pages/countries/cn.m3u",
   # "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
   # "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
   # "https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/others_output.txt",
    #"https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv6.txt",
    #"https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt",
    "https://live.hacks.tools/tv/iptv4.txt",
   # "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv6.m3u",
    # 其他源链接...
]

# GitHub Logo 远程仓库配置（新增）
GITHUB_LOGO_BASE_URL = "https://github.com/fanmingming/live/tree/main/tv"
BACKUP_LOGO_BASE_URL = "https://github.com/fanmingming/live/tree/main/tv"
GITHUB_LOGO_API_URLS = [
    "https://ghproxy.cc/https://raw.githubusercontent.com/fanmingming/live/main/tv/",
    "https://ghproxy.cc/https://raw.githubusercontent.com/fanmingming/live/main/tv/"
]


# EPG（电子节目指南）URL列表
EPG_URLS  = [
    "https://epg.v1.mk/fy.xml",
    "http://epg.51zmt.top:8000/e.xml",
    "https://epg.pw/xmltv/epg_CN.xml",
    "https://epg.pw/xmltv/epg_HK.xml",
    "https://epg.pw/xmltv/epg_TW.xml",
    "https://raw.githubusercontent.com/plsy1/epg/main/e/seven-days.xml.gz",
    "https://live.fanmingming.cn/e.xml",
]
ANNOUNCEMENTS = []
