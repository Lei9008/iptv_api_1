
# 配置文件，包含直播源URL、黑名单URL、公告信息、EPG URL、测速超时时间和线程池最大工作线程数

# 优先使用的IP版本，这里设置为ipv4
ip_version_priority = "ipv4"

# 直播源URL列表
source_urls = [
    "https://raw.githubusercontent.com/Lei9008/iptv_api_1/main/self_use/IPTV1/Ku9-IPTV-source.txt",
    "https://raw.githubusercontent.com/Lei9008/iptv_selfuse/master/output/user_result.txt",
    "https://gh-proxy.com/https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt",
    "https://raw.githubusercontent.com/alantang1977/IPTV/main/live_ipv4.txt",
    "https://raw.githubusercontent.com/alantang1977/iptv_api/main/output/live_ipv4.m3u",
    "https://raw.githubusercontent.com/alantang1977/IPTV_SuperA/main/output/result.m3u",
    "https://raw.githubusercontent.com/alantang1977/IPTV_SuperB/main/output/live_ipv4.m3u",
    "https://raw.githubusercontent.com/alantang1977/iptv8/main/bbxx_lite.txt",
    "https://raw.githubusercontent.com/alantang1977/IPTV-CCSH/main/live_lite.txt",
    "https://raw.githubusercontent.com/alantang1977/IPTV-m3u/main/m3u/IPTV.m3u",
    "https://raw.githubusercontent.com/alantang1977/IPTV-m3u/main/m3u/Live.m3u",
    "https://raw.githubusercontent.com/alantang1977/JunTV/main/output/result.m3u",
    "https://raw.githubusercontent.com/alantang1977/Ku9-IPTV-source/main/webview.txt",
    "https://raw.githubusercontent.com/alantang1977/pg/main/live_lite.txt",
    "https://raw.githubusercontent.com/alantang1977/TV_live/main/live.txt",
    "https://raw.githubusercontent.com/alantang1977/TV_video/main/interface.txt",
    "https://raw.githubusercontent.com/alantang1977/X/main/live/live_ipv4.m3u",
    "https://raw.githubusercontent.com/alantang1977/yuanzl77/main/live.m3u",
    "https://raw.githubusercontent.com/alantang1977/iptv_SuperD/dist/live.m3u",
    "https://raw.githubusercontent.com/alantang1977/jtv/refs/heads/main/网络收集.txt",
    # 其他源链接...
    "https://ghfast.top/https://raw.githubusercontent.com/plsy1/iptv/main/multicast/multicast-jining.m3u",
    "https://ghfast.top/https://raw.githubusercontent.com/plsy1/iptv/main/unicast/unicast-ku9.m3u",
    "https://ghproxy.cc/https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u",
    "https://ghproxy.cc/https://raw.githubusercontent.com/iptv-org/iptv/gh-pages/countries/cn.m3u",
    "https://ghproxy.cc/https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
    "https://ghproxy.cc/https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv6.m3u",
    "https://ghproxy.cc/https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt",
    "https://raw.githubusercontent.com/alantang1977/iptv-auto/refs/heads/main/my.txt",
    "https://raw.githubusercontent.com/alantang1977/TVsmile/refs/heads/main/%E7%BD%91%E7%BB%9C%E6%94%B6%E9%9B%86.txt",
    "https://raw.githubusercontent.com/develop202/migu_video/main/interface.txt",
    "https://raw.githubusercontent.com/fuxinyi0505/Ku9-IPTV-source/refs/heads/main/Ku9-IPTV-source.txt",
    "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%8F%B0%E6%B9%BE%E9%A6%99%E6%B8%AF%E6%BE%B3%E9%97%A82023.m3u",
    "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%9B%BD%E5%86%85%E7%94%B5%E8%A7%86%E5%8F%B02023.m3u8",
    

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
                "url": "https://txmov2.a.kwimgs.com/upic/2023/06/18/23/BMjAyMzA2MTgyMzE1MjBfMzQ4MzI0MjA1OF8xMDU4Nzc4MzAzNjZfMF8z_b_B386baa1bb2c0c48626a830ff69393771.mp4",
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


# 基础频道名称映射
cntvNamesReverse = {
    # 基础频道
    "CCTV1综合": "CCTV1",
    "CCTV2财经": "CCTV2",
    "CCTV3综艺": "CCTV3",
    "CCTV4中文国际": "CCTV4",
    "CCTV5体育": "CCTV5",
    "CCTV5+体育赛事": "CCTV5+",
    "CCTV6电影": "CCTV6",
    "CCTV7国防军事": "CCTV7",
    "CCTV8电视剧": "CCTV8",
    "CCTV9纪录": "CCTV9",
    "CCTV10科教": "CCTV10",
    "CCTV11戏曲": "CCTV11",
    "CCTV12社会与法": "CCTV12",
    "CCTV13新闻": "CCTV13",
    "CCTV14少儿": "CCTV14",
    "CCTV15音乐": "CCTV15",
    "CCTV16奥林匹克": "CCTV16",
    "CCTV17农业农村": "CCTV17",
    # 海外频道
    "CCTV4中文国际(欧洲)": "CCTV4欧洲",
    "CCTV4中文国际(美洲)": "CCTV4美洲",
}

# 非规范名称的别名映射（增强模糊匹配）
cctv_alias = {
    "央视1套": "CCTV1",
    "中央1套": "CCTV1",
    "央视2套": "CCTV2",
    "中央2套": "CCTV2",
    "央视3套": "CCTV3",
    "中央3套": "CCTV3",
    "央视4套": "CCTV4",
    "中央4套": "CCTV4",
    "央视5套": "CCTV5",
    "中央5套": "CCTV5",
    "央视5+套": "CCTV5+",
    "中央5+套": "CCTV5+",
    "央视6套": "CCTV6",
    "中央6套": "CCTV6",
    "央视7套": "CCTV7",
    "中央7套": "CCTV7",
    "央视8套": "CCTV8",
    "中央8套": "CCTV8",
    "央视9套": "CCTV9",
    "中央9套": "CCTV9",
    "央视10套": "CCTV10",
    "中央10套": "CCTV10",
    "央视11套": "CCTV11",
    "中央11套": "CCTV11",
    "央视12套": "CCTV12",
    "中央12套": "CCTV12",
    "央视13套": "CCTV13",
    "中央13套": "CCTV13",
    "央视14套": "CCTV14",
    "中央14套": "CCTV14",
    "央视15套": "CCTV15",
    "中央15套": "CCTV15",
    "央视16套": "CCTV16",
    "中央16套": "CCTV16",
    "央视17套": "CCTV17",
    "中央17套": "CCTV17",
    "CCTV9纪录片": "CCTV9",
}

