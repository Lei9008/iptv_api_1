
# 配置文件，包含直播源URL、黑名单URL、公告信息、EPG URL、测速超时时间和线程池最大工作线程数

# 优先使用的IP版本，这里设置为ipv4
ip_version_priority = "ipv4"

# 直播源URL列表
source_urls = [
    "https://raw.githubusercontent.com/alantang1977/iptv8/main/bbxx.txt",
    "https://raw.githubusercontent.com/alantang1977/IPTV-CCSH/main/live.txt",
    "https://ghproxy.it/https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt",
    

]

# 直播源黑名单URL列表，去除了重复项
url_blacklist = [
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
    "[2409:8087:2001:20:2800:0:df6e:eb25]:80",  
    "stream1.freetv.fun",
    "chinamobile",
    "gaoma",
    "audio",
    "[2409:8087:2001:20:2800:0:df6e:eb27]",
    "http://ygbh.site/php/bfgd.php?",
    "http://23.237.228.134/live8",
    "https://smt.858.qzz.io/Smart.php",
    "http://23.237.228.134/live6",
    "http://23.237.228.134/live6/dongnan.m3u8",
    "http://player.cntv.cn/standard/",
    "https://player.cntv.cn/standard/live",
    "http://38.75.136.137:98/gslb/dsdqbv/dfwshd.m3u8"
]

# 公告信息
announcements = [
    {
        "channel": "更新日期",
        "entries": [
            {
                "name": None,
                "url": "https://raw.githubusercontent.com/Lei9008/iptv_api_1/main/pic/Updatetime.mp4",
                "logo": "https://raw.githubusercontent.com/Lei9008/iptv_api_1/main/pic/Updatetime.png"
            }
        ]
    }
]

# EPG（电子节目指南）URL列表
epg_urls = [
    "https://epg.v1.mk/fy.xml",
    "http://epg.51zmt.top:8000/e.xml",
    "https://raw.githubusercontent.com/springs/epg/main/pp.xml",
    "https://live.fanmingming.com/e.xml",
    "https://raw.githubusercontent.com/fanmingming/live/main/e.xml",
]
# 测速超时时间（秒）
TEST_TIMEOUT = 10

# 测速线程池最大工作线程数
MAX_WORKERS = 20
