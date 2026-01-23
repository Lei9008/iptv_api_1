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
 "https://example.com/iptv.m3u",
 "https://example.com/iptv.txt",
 "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv6.m3u",
 "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E7%A7%BB%E5%8A%A8IPV6IPTV%E7%9B%B4%E6%92%AD%E6%BA%90.m3u",
    "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%9B%BD%E5%86%85%E7%94%B5%E8%A7%86%E5%8F%B0202509.m3u",
    "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%B1%B1%E4%B8%9C%E7%94%B5%E4%BF%A12025.m3u",
    "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%B1%B1%E4%B8%9C%E8%81%94%E9%80%9A.m3u",
    "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%B1%B1%E4%B8%9C%E8%81%94%E9%80%9A%E7%BB%84%E6%92%AD.m3u",
    "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E6%B1%9F%E8%8B%8F%E7%94%B5%E4%BF%A1%E7%BB%84%E6%92%AD.m3u",
    "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E7%99%BE%E8%A7%86TV.m3u",
    "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/CCTV+%E5%8D%AB%E8%A7%86+%E5%8C%97%E4%BA%AC+%E5%87%A4%E5%87%B0+%E6%8E%A2%E7%B4%A2+%E6%98%9F%E7%A9%BA%E5%8D%AB%E8%A7%86-%E5%8C%97%E4%BA%AC%E9%82%AE%E7%94%B5%E5%A4%A7%E5%AD%A6%E6%A0%A1%E5%9B%AD%E7%BD%91.m3u",
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






