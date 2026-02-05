# config.py
# 全局配置项
class Config:
    # 并发与请求配置（GitHub链接建议不超过30，避免被封禁）
    CONCURRENT_LIMIT = 20  # 并发限制
    TIMEOUT = 15  # 超时时间（适配海外链接，延长至15秒）
    RETRY_TIMES = 3  # 重试次数，提升下载/测速成功率

    # 目录与文件配置
    OUTPUT_DIR = "output"  # 日志/报告输出目录（自动创建）
    LOG_FILE = "output/speed_test.log"  # 日志文件路径

    # 目标GitHub远程链接（两个专属优化链接）
    SOURCE_URLS = [
        "https://raw.githubusercontent.com/alantang1977/IPTV/main/live_ipv4.txt",
        "https://raw.githubusercontent.com/alantang1977/iptv_api/main/output/live_ipv4.m3u"
    ]