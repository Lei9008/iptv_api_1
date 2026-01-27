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
]

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
