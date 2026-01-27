# config1.py
# 直播源URL列表（支持GitHub RAW/普通HTTP链接）
LIVE_SOURCE_URLS = [
    # 替换为你的实际直播源链接
    "https://github.com/develop202/migu_video/blob/main/interface.txt",

  
]

# 字符串相似度阈值（0-1），越高越严格（仅用于URL不同时的字段近似判断）
SIMILARITY_THRESHOLD = 0.85

# 输出M3U文件名
OUTPUT_FILE = "merged_clean.m3u"

# 请求超时时间（秒）
REQUEST_TIMEOUT = 20
