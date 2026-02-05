# config.py
# 全局配置项
class Config:
    # 并发与请求配置
    CONCURRENT_LIMIT = 20  # 并发限制
    TIMEOUT = 10  # 超时时间（秒）
    RETRY_TIMES = 2  # 重试次数
    
    # 目录与文件配置
    OUTPUT_DIR = "output"  # 日志/报告输出目录
    LOG_FILE = "output/speed_test.log"  # 日志文件路径
    
    # 关键修改：远程直播源URL列表（支持GitHub RAW / 普通HTTP链接）
    # 示例：GitHub RAW链接、普通HTTP链接均可
    SOURCE_URLS = [
         "https://raw.githubusercontent.com/alantang1977/IPTV/main/live_ipv4.txt",
    ]