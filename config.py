# config.py - IPTV直播源处理配置文件
# 修复语法错误 + 规范变量定义

# 模板文件路径（相对路径）
TEMPLATE_FILE = "demo.txt"

# ===================== 测速配置 =====================
# 延迟阈值（ms），超过该值仍保留但标注延迟
LATENCY_THRESHOLD = 1000
# 异步并发数（根据服务器性能调整）
CONCURRENT_LIMIT = 20
# 超时时间（s）
TIMEOUT = 15
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







