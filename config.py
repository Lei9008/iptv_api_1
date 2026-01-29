# config.py - IPTV直播源处理配置文件
# 修复语法错误 + 规范变量定义

# 模板文件路径（相对路径）
TEMPLATE_FILE = "demo.txt"

# ===================== 测速配置 =====================
# 延迟阈值（ms），超过该值仍保留但标注延迟
LATENCY_THRESHOLD = 500
# 异步并发数（根据服务器性能调整）
CONCURRENT_LIMIT = 20
# 超时时间（s）
TIMEOUT = 12
# 重试次数
RETRY_TIMES = 2
# 频道匹配阈值（默认 0.4）
MATCH_CUTOFF = 0.5
# IP版本优先级（ipv4/ipv6）
IP_VERSION_PRIORITY = "ipv4"

# ===================== 核心源配置 =====================
# 直播源URL列表（支持GitHub RAW/普通HTTP链接）
SOURCE_URLS = [
    # 替换为你自己的直播源链接
   
    "https://ghfast.top/https://raw.githubusercontent.com/plsy1/iptv/main/unicast/unicast-ku9.m3u",
    "https://github.com/plsy1/iqilu/blob/main/iqilu-generic.m3u",
    "https://ghfast.top/https://raw.githubusercontent.com/plsy1/iptv/main/multicast/multicast-jining.m3u",
    "https://github.com/develop202/migu_video/blob/main/interface.txt",
    "https://github.com/cyh92/iptv-api-weishi/blob/master/output/weishi.m3u",
    "https://github.com/cyh92/iptv-api-cctv/blob/master/output/cctv.m3u",
    "https://github.com/8080713/iptv-api666/blob/main/output/result.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/gh-pages/countries/cn.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
    "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
    "https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/others_output.txt",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt",
    "https://live.hacks.tools/tv/iptv4.txt",
    "https://raw.kkgithub.com/sumingyd/Telecom-Shandong-IPTV-List/main/Telecom-Shandong-Multicast.m3u",
    "https://github.com/kakaxi-1/IPTV/blob/main/ipv4.txt",
    "https://github.com/zilong7728/Collect-IPTV/blob/main/best_sorted.m3u",
    "https://github.com/skddyj/iptv/blob/main/IPTV.m3u",
    "https://github.com/best-fan/iptv-sources/blob/main/cn_all_status.m3u8",
    "https://raw.githubusercontent.com/fuxinyi0505/Ku9-IPTV-source/refs/heads/main/Ku9-IPTV-source.txt",
    "https://github.com/0610840119/iptv-api/blob/master/output/xp_result.m3u",
    
    
    "https://bc.188766.xyz/?url=https://live.iill.top&mishitong=true&mima=mianfeibuhuaqian",
    "https://raw.githubusercontent.com/zxmlxw520/5566/refs/heads/main/cjdszb.txt",
    "https://raw.githubusercontent.com/mymsnn/DailyIPTV/main/outputs/full_validated.m3u",
    "https://cloud.7so.top/f/xv80ux/天浪.txt",
    "https://cloud.7so.top/f/yr7BHL/HKTV.txt",
    "https://gitee.com/main-stream/tv/raw/master/BOSS.json",
    "https://raw.githubusercontent.com/alantang1977/iptv-auto/refs/heads/main/my.txt",
    "http://gg.7749.org//i/ds.txt",
    "https://gitee.com/alexkw/app/raw/master/kgk.txt",
    "https://d.kstore.dev/download/15114/HKTV.txt",
    "http://gg.7749.org/z/i/gdss.txt",
    "https://raw.githubusercontent.com/iodata999/frxz751113-IPTVzb1/refs/heads/main/结果.m3u",
    "https://raw.githubusercontent.com/alantang1977/jtv/refs/heads/main/网络收集.txt",
    "https://bc.188766.xyz/?url=http://tv123.top:35455&mishitong=true&mima=bingchawusifengxian",
    "https://raw.githubusercontent.com/zxmlxw520/5566/refs/heads/main/gqds+.txt",
    "https://raw.githubusercontent.com/develop202/migu_video/main/interface.txt", 
    "https://live.izbds.com/tv/iptv4.txt",
    "http://rihou.cc:555/gggg.nzk",
    "http://1.94.31.214/live/livelite.txt",
    "http://lisha521.dynv6.net.fh4u.org/tv.txt",
    "https://iptv.catvod.com/tv.m3u",
    "https://live.zbds.top/tv/iptv4.txt",
    "https://gitee.com/xxy002/zhiboyuan/raw/master/dsy",

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
   "https://3043.kstore.space/bhvip/bhzb.txt",
   "https://tv.iill.top/m3u/Gather",
   "https://m.iill.top/Live.m3u",
   "https://tv.iill.top/m3u/Sport",
   "https://live.freetv.top/huyayqk.m3u",
   "https://live.freetv.top/douyuyqk.m3u",
   "https://live.zhoujie218.top/tv/iptv4.txt",
   "https://iptv.zsdc.eu.org/home/iptv.m3u8",
   "https://t.freetv.fun/m3u/playlist.txt",
   "https://t.freetv.fun/m3u/taiwan.txt",
   "https://t.freetv.fun/m3u/hong_kong.txt",
   "https://t.freetv.fun/m3u/macao.txt",
   "https://t.freetv.fun/m3u/japan.txt",
   "https://live.hacks.tools/tv/ipv4/categories/地方频道.m3u",
   "https://live.hacks.tools/tv/ipv4/categories/电影频道.m3u",
   "https://live.hacks.tools/tv/ipv4/categories/儿童频道.m3u",
   "https://live.hacks.tools/tv/ipv4/categories/纪录频道.m3u",
   "https://live.hacks.tools/tv/ipv4/categories/其他频道.m3u",
   "https://live.hacks.tools/tv/ipv4/categories/数字频道.m3u",
   "https://live.hacks.tools/tv/ipv4/categories/体育频道.m3u",
   "https://live.hacks.tools/tv/ipv4/categories/卫视频道.m3u",
   "https://live.hacks.tools/tv/ipv4/categories/戏曲频道.m3u",
   "https://live.hacks.tools/tv/ipv4/categories/央视频道.m3u",
   "https://live.hacks.tools/tv/ipv4/categories/音乐频道.m3u",
   "https://live.hacks.tools/tv/ipv4/categories/游戏频道.m3u",
   "https://live.hacks.tools/tv/ipv4/categories/直播中国.m3u",
   "https://live.hacks.tools/tv/ipv4/categories/综艺频道.m3u",
   "https://live.hacks.tools/tv/ipv4/categories/解说频道.m3u",
   "https://tv.850930.xyz/kdsb.txt",
   "https://tv.850930.xyz/pix.m3u",
   "https://live.zbds.org/tv/iptv6.txt",
   "https://live.zbds.org/tv/iptv4.txt",
   "https://freetv.fun/test_channels_original_new.txt",
   "https://jihulab.com/-/snippets/5265/raw/main/.txt",
   "https://live.zbds.org/tv/iptv6.m3u",
   "https://live.zbds.org/tv/iptv4.m3u",
   "https://m3u.ibert.me/fmml_ipv6.m3u",
   "https://raw.githubusercontent.com/YueChan/Live/refs/heads/main/IPTV.m3u",
   "https://raw.githubusercontent.com/zwc456baby/iptv_alive/refs/heads/master/live.m3u",
   "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/cnTV_AutoUpdate.m3u8",
   "https://raw.githubusercontent.com/suxuang/myIPTV/refs/heads/main/ipv4.m3u",
   "https://raw.githubusercontent.com/suxuang/myIPTV/refs/heads/main/ipv6.m3u",
   "https://raw.githubusercontent.com/cyalias/mytvs-github/refs/heads/main/mytv.txt",
   "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
   "https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",
   "https://raw.githubusercontent.com/fanmingming/live/refs/heads/main/tv/m3u/ipv6.m3u",
   "https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/refs/heads/main/merged_output.txt",
   "https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/refs/heads/main/others_output.txt",
   "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/refs/heads/main/cnTV_AutoUpdate.m3u8",
   "https://raw.githubusercontent.com/jiangnan1224/iptv_ipv4_live/refs/heads/main/live_ipv4.txt",
   "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt",
   "https://raw.githubusercontent.com/wwb521/live/refs/heads/main/tv.txt",
   "https://raw.githubusercontent.com/BurningC4/Chinese-IPTV/master/TV-IPV4.m3u",
   "https://raw.githubusercontent.com/xzw832/cmys/refs/heads/main/S_CCTV.txt",
   "https://raw.githubusercontent.com/xzw832/cmys/refs/heads/main/S_weishi.txt",
   "https://raw.githubusercontent.com/MemoryCollection/IPTV/refs/heads/main/hotel.txt",
   "https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u",
   "https://raw.githubusercontent.com/mlzlzj/hnyuan/refs/heads/main/iptv_list.txt",
   "https://raw.githubusercontent.com/altn2025/iptv/main/iptv.m3u",
   "https://raw.githubusercontent.com/BP3388/BP001.github.io/main/tivi.list",
   "https://raw.githubusercontent.com/Supprise0901/TVBox_live/main/live.txt",
   "https://raw.githubusercontent.com/gaotianliuyun/gao/master/list.txt",
   "https://raw.githubusercontent.com/zwc456baby/iptv_alive/master/live.txt",
   "https://raw.githubusercontent.com/junge3333/juds6/main/yszb1.txt",
   "https://raw.githubusercontent.com/zzmaze/iptv/main/itvlist.txt",
   "https://raw.githubusercontent.com/maitel2020/iptv-self-use/main/iptv.txt",
   "https://raw.githubusercontent.com/n3rddd/CTVLive/refs/heads/main/live.txt",
   "https://raw.githubusercontent.com/xiongjian83/TvBox/refs/heads/main/live.txt",
   "https://raw.githubusercontent.com/yoursmile66/TVBox/refs/heads/main/live.txt",
   "https://raw.githubusercontent.com/alienlu/iptv/refs/heads/master/iptv.txt",
   "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv6.m3u",
   "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%8F%B0%E6%B9%BE%E9%A6%99%E6%B8%AF%E6%BE%B3%E9%97%A82023.m3u",
   "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%9B%BD%E5%86%85%E7%94%B5%E8%A7%86%E5%8F%B02023.m3u8",
   "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E8%BD%AE%E6%92%AD_%E5%8D%8E%E6%95%B0.%E9%BB%91%E8%8E%93.NewTV.SiTV.CIBN.m3u",
   "https://raw.githubusercontent.com/yuanzl77/IPTV/refs/heads/main/live.txt",
   "https://iptv-org.github.io/iptv/languages/zho.m3u",
   "https://iptv-org.github.io/iptv/countries/us.m3u",
   "https://iptv-org.github.io/iptv/countries/tw.m3u",
   "https://cc-im-kefu-cos.7moor-fs2.com/im/2768a390-5474-11ea-afc9-7b323e3e16c0/d4fe44c5-107c-4511-af02-aa08fb10dff7/2024-04-25/2024-04-25_17:22:21/1714036941087/98644330/wexiptv.txt",
   "https://fm1077.serv00.net/SmartTV.m3u",
   "https://live.zbds.top/tv/iptv6.txt",
   "https://gitlab.com/p2v5/wangtv/-/raw/main/lunbo.txt",
   "https://m3u.ibert.me/txt/fmml_ipv6.txt",
   "https://m3u.ibert.me/txt/ycl_iptv.txt",
   "https://m3u.ibert.me/txt/y_g.txt",
   "https://gitee.com/tushaoyong/live/raw/master/%E6%8E%A5%E5%8F%A3/IPV6.txt",
   "http://tot.totalh.net/tttt.txt",




 
    
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
    "[2409:8087:2001:20:2800:0:df6e:eb27]",
    
    "http://ygbh.site/php/bfgd.php?",
    "http://23.237.228.134/live8",
    "https://smt.858.qzz.io/Smart.php",
    "http://23.237.228.134/live6",
    "http://23.237.228.134/live6/dongnan.m3u8",
    "http://player.cntv.cn/standard/",
    "https://player.cntv.cn/standard/live",
    "http://38.75.136.137:98/gslb/dsdqbv/dfwshd.m3u8",





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

# 格式：{目标名称: [需要映射的原始名称列表]}
group_title_mapping = {
    # 地区频道
    '安徽频道': ['安徽地区'],
    '北京频道': ['北京地区'],
    '福建频道': ['福建地区'],
    '甘肃频道': ['甘肃地区'],
    '广东频道': ['广东地区'],
    '广西频道': ['广西地区'],
    '贵州频道': ['贵州地区'],
    '海南频道': ['海南地区'],
    '河北频道': ['河北地区'],
    '河南频道': ['河南地区'],
    '黑龙江频道': ['黑龙江地区'],
    '湖北频道': ['湖北地区'],
    '湖南频道': ['湖南地区'],
    '吉林频道': ['吉林地区'],
    '江苏频道': ['江苏地区'],
    '江西频道': ['江西地区'],
    '辽宁频道': ['辽宁地区'],
    '内蒙古频道': ['内蒙古地区'],
    '宁夏频道': ['宁夏地区'],
    '青海频道': ['青海地区'],
    '山东频道': ['山东地区', '山东省级'],  # 新增：山东省级→山东频道
    '山西频道': ['山西地区'],
    '陕西频道': ['陕西地区'],
    '上海频道': ['上海地区'],
    '四川频道': ['四川地区'],
    '天津频道': ['天津地区'],
    '新疆频道': ['新疆地区'],
    '云南频道': ['云南地区'],
    '浙江频道': ['浙江地区'],
    '重庆频道': ['重庆地区'],
    
    # 特殊分类
    '港澳台频道': ['港澳台', '港澳代理', '湾区频道'],  # 港澳台/港澳代理→港澳台频道
    '央视频道': ['央视台'],              # 央视台→央视频道
    '卫视频道': ['卫视台'],              # 卫视台→卫视频道
    '4K超高清': ['超清频道', '4K频道'],  # 超清频道/4K频道→4K超高清
    '央视高清': ['央视高清频道'],        # 央视高清频道→央视高清（单独分类）
    '动漫频道': ['动画频道'],
}

# 兼容旧映射：快速查找原始名称对应的目标名称（供代码调用）
group_title_reverse_mapping = {}
for target, originals in group_title_mapping.items():
    for original in originals:
        group_title_reverse_mapping[original] = target







