# config.py
# 全局配置项
class Config:
    # 并发与请求配置
    CONCURRENT_LIMIT = 20  # 并发限制
    TIMEOUT = 10  # 超时时间（秒）
    RETRY_TIMES = 2  # 重试次数
    
    # 目录与文件配置
    OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")  # 输出文件夹绝对路径
    LOG_FILE = os.path.join(OUTPUT_DIR, "function.log")  # 日志文件绝对路径
   
    
    # 关键修改：远程直播源URL列表（支持GitHub RAW / 普通HTTP链接）
    # 示例：GitHub RAW链接、普通HTTP链接均可
    SOURCE_URLS = [
         "https://raw.githubusercontent.com/alantang1977/IPTV/main/live_ipv4.txt",
         "https://raw.githubusercontent.com/alantang1977/iptv_api/main/output/live_ipv4.m3u"
    ]