# config.py
# 直播源URL列表（支持GitHub RAW/普通HTTP链接）
LIVE_SOURCE_URLS = [
    "https://raw.githubusercontent.com/develop202/migu_video/main/interface.txt",
]

# 字符串相似度阈值（0-1），越高越严格（仅用于URL不同时的字段近似判断）
SIMILARITY_THRESHOLD = 0.85

# 输出M3U文件名
OUTPUT_FILE = "self_use/output/merged_clean.m3u"

# 请求超时时间（秒）
REQUEST_TIMEOUT = 20

# GitHub RAW镜像域名列表
GITHUB_MIRRORS = [
    "raw.githubusercontent.com",
    "raw.kkgithub.com",
    "raw.githubusercontents.com",
    "raw.fgit.cf",
    "raw.fgithub.de"
]

# GitHub 代理前缀列表
PROXY_PREFIXES = [
    "https://ghproxy.com/",
    "https://mirror.ghproxy.com/",
    "https://gh.api.99988866.xyz/"
]
