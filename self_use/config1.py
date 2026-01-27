# config1.py - IPTV直播源配置文件

# 直播源URL列表（核心配置）
SOURCE_URLS = [
    
     "https://raw.githubusercontent.com/develop202/migu_video/main/interface.txt",
    # 可以添加更多源URL
]

# 抓取超时时间（秒）
FETCH_TIMEOUT = 15

# 日志级别：DEBUG, INFO, WARNING, ERROR
LOG_LEVEL = "INFO"

# 可选：添加更多自定义配置
# MAX_CANDIDATE_URLS = 5  # GitHub候选URL最大数量
# BLACKLIST_KEYWORDS = ["badcdn.com", "广告"]  # URL黑名单关键词
