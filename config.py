# config.py - IPTV直播源处理配置文件
# ===================== 核心配置 =====================

# 模板文件路径（必填，需提前创建）
TEMPLATE_FILE = "demo.txt"

# 延迟阈值（ms）：超过该值标记为延迟过高
LATENCY_THRESHOLD = 1000

# 并发限制：同时测速的URL数量
CONCURRENT_LIMIT = 20

# 超时时间（s）：单个URL请求超时时间
TIMEOUT = 20

# 重试次数：URL抓取/测速失败后的重试次数
RETRY_TIMES = 2

# IP版本优先级："ipv4" 或 "ipv6"
IP_VERSION_PRIORITY = "ipv4"

# 直播源URL列表（必填，填写你的直播源地址）
SOURCE_URLS = [
    # 示例：
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


# ===================== 辅助配置 =====================
# URL黑名单：包含以下字符串的URL会被过滤
URL_BLACKLIST = [
    # "test-url",
    # "invalid-domain.com"
]

# EPG地址列表：生成M3U时添加x-tvg-url属性
EPG_URLS = [

   
    "https://epg.v1.mk/fy.xml",
    "http://epg.51zmt.top:8000/e.xml",
    "https://epg.pw/xmltv/epg_CN.xml",
    "https://epg.pw/xmltv/epg_HK.xml",
    "https://epg.pw/xmltv/epg_TW.xml",
    "https://raw.githubusercontent.com/plsy1/epg/main/e/seven-days.xml.gz",
    "https://live.fanmingming.cn/e.xml",


   
]

# 公告频道配置：会添加到M3U文件开头
ANNOUNCEMENTS = [
    # {
    #     "channel": "公告频道",
    #     "entries": [
    #         {
    #             "name": "直播源更新公告",
    #             "url": "https://example.com/announcement.txt",
    #             "logo": "https://example.com/logo.png"
    #         }
    #     ]
    # }
]

# ===================== Logo配置 =====================
# GitHub Logo仓库基础地址
GITHUB_LOGO_BASE_URL = "https://raw.githubusercontent.com/fanmingming/live/main/tv"
BACKUP_LOGO_BASE_URL = "https://ghproxy.com/https://raw.githubusercontent.com/fanmingming/live/main/tv"

# GitHub Logo API地址（用于获取logo文件列表）
GITHUB_LOGO_API_URLS = [
    "https://api.github.com/repos/fanmingming/live/contents/main/tv",
    "https://ghproxy.com/https://api.github.com/repos/fanmingming/live/contents/main/tv"
]



