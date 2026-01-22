
# 配置文件，包含直播源URL、黑名单URL、公告信息、EPG URL、测速超时时间和线程池最大工作线程数

# 优先使用的IP版本，这里设置为ipv4
ip_version_priority = "ipv4"

# 直播源URL列表
source_urls = [
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
    "https://ghproxy.cc/https://raw.githubusercontent.com/iptv-org/iptv/gh-pages/countries/cn.m3u",
    "https://ghproxy.cc/https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
    "https://ghproxy.cc/https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv6.m3u",
    "https://ghproxy.cc/https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/merged_output.txt",
    "https://ghproxy.cc/https://raw.githubusercontent.com/xzw832/cmys/main/S_CCTV.txt",
    "https://ghproxy.cc/https://raw.githubusercontent.com/xzw832/cmys/main/S_weishi.txt",
    "https://ghproxy.cc/https://raw.githubusercontent.com/asdjkl6/tv/tv/.m3u/整套直播源/测试/整套直播源/l.txt",
    "https://ghproxy.cc/https://raw.githubusercontent.com/asdjkl6/tv/tv/.m3u/整套直播源/测试/整套直播源/kk.txt",
    "https://ghproxy.cc/https://raw.githubusercontent.com/yuanzl77/IPTV/master/live.txt",
    "https://ghproxy.cc/https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u",
    "https://ghproxy.cc/https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv6.txt",
    "https://ghproxy.cc/https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt",
    "https://ghproxy.cc/https://raw.githubusercontent.com/YueChan/Live/main/APTV.m3u",
    "https://ghproxy.cc/https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",



    
    "https://gh-proxy.com/raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
    "https://fastly.jsdelivr.net/gh/plsy1/iptv@master/unicast/unicast-ku9.m3u",
    "https://fastly.jsdelivr.net/gh/plsy1/iqilu@master/iqilu-ku9.m3u",
    "http://rihou.cc:555/gggg.nzk",
    "https://github.com/plsy1/iptv/blob/main/multicast/multicast-jinan.m3u",
    "https://github.com/liuchuang0321/K-TV/blob/master/output/user_result.txt",
    "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.m3u",
    
    "https://zb.pl10000.top/list.txt",
    "https://raw.githubusercontent.com/mymsnn/DailyIPTV/main/outputs/full_validated.m3u",
    "https://115.190.105.236/vip/qwt.m3u",
    "https://115.190.105.236/vip/vip.m3u",
    "https://cloud.7so.top/f/xv80ux/天浪.txt",
    "https://gitee.com/main-stream/tv/raw/master/BOSS.json",
    "https://raw.githubusercontent.com/alantang1977/iptv-auto/refs/heads/main/my.txt",
    "https://gitee.com/alexkw/app/raw/master/kgk.txt",
    "https://d.kstore.dev/download/15114/HKTV.txt",
    "http://go8.myartsonline.com/zx/0/TVBTV28.txt",
    "https://raw.githubusercontent.com/iodata999/frxz751113-IPTVzb1/refs/heads/main/结果.m3u",
    "https://raw.githubusercontent.com/alantang1977/jtv/refs/heads/main/网络收集.txt",
    "https://raw.githubusercontent.com/zxmlxw520/5566/refs/heads/main/cjdszb.txt",
    "https://raw.githubusercontent.com/zxmlxw520/5566/refs/heads/main/gqds+.txt",
    "https://raw.githubusercontent.com/develop202/migu_video/main/interface.txt",
    "https://www.iyouhun.com/tv/myIPTV/ipv6.m3u",
    "https://www.iyouhun.com/tv/myIPTV/ipv4.m3u",
    "https://live.izbds.com/tv/iptv4.txt",
    "http://1.94.31.214/live/livelite.txt",
    "https://iptv.catvod.com/tv.m3u",
    "https://live.zbds.top/tv/iptv4.txt",
    "https://gitee.com/xxy002/zhiboyuan/raw/master/dsy",
    "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv6.m3u",
    
    

    
       
 

]

# 直播源黑名单URL列表，去除了重复项
url_blacklist = [
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

# 公告信息
announcements = [
    {
        "channel": "更新日期",
        "entries": [
            {
                "name": None,
                "url": "https://cnb.cool/junchao.tang/jtv/-/git/raw/main/Pictures/Robot.mp4",
                "logo": "https://cnb.cool/junchao.tang/jtv/-/git/raw/main/Pictures/Chao.png"
            }
        ]
    }
]

# EPG（电子节目指南）URL列表
epg_urls = [
    "https://epg.v1.mk/fy.xml",
    "http://epg.51zmt.top:8000/e.xml",
    "https://epg.pw/xmltv/epg_CN.xml",
    "https://epg.pw/xmltv/epg_HK.xml",
    "https://epg.pw/xmltv/epg_TW.xml",
    "https://raw.githubusercontent.com/plsy1/epg/main/e/seven-days.xml.gz",
    "https://live.fanmingming.cn/e.xml",
]
# 测速超时时间（秒）
TEST_TIMEOUT = 8

# 测速线程池最大工作线程数
MAX_WORKERS = 20
