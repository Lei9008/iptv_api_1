# config.py
# ===================== 直播源配置（核心） =====================
# 源URL列表（请替换为你自己的直播源链接）
SOURCE_URLS = [
    # 示例链接，替换为实际的直播源URL
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

]

# demo.txt分类映射文件路径（可修改为你的实际路径，相对/绝对路径均可）
DEMO_TXT_PATH = "demo.txt"

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

# 修正后的 group-title 标准化映射（解决重复键问题，多对一）
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
    '港澳台频道': ['港澳台','港澳代理'],  # 港澳台/港澳代理→港澳台频道
    '央视频道': ['央视台'],              # 央视台→央视频道
    '卫视频道': ['卫视台'],              # 卫视台→卫视频道
    '4K超高清': ['超清频道', '4K频道'],  # 超清频道/4K频道→4K超高清
    '央视高清': ['央视高清频道'],        # 央视高清频道→央视高清（单独分类）
}

# 兼容旧映射：快速查找原始名称对应的目标名称（供代码调用）
group_title_reverse_mapping = {}
for target, originals in group_title_mapping.items():
    for original in originals:
        group_title_reverse_mapping[original] = target






