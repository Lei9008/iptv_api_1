import os

# 1. 获取当前config.py文件的目录（即脚本所在目录，与speed_test.py同目录）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 全局配置项
class Config:
    # 并发与请求配置
    CONCURRENT_LIMIT = 20
    TIMEOUT = 10
    RETRY_TIMES = 2
    
    # 2. 输出文件夹：与脚本（speed_test.py）同目录下的output文件夹
    OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
    # 日志文件：output文件夹下的function.log
    LOG_FILE = os.path.join(OUTPUT_DIR, "function.log")
    
    # 远程直播源URL列表
    SOURCE_URLS = [
        "https://raw.githubusercontent.com/Lei9008/iptv_api_1/main/self_use/IPTV_Update/output/live_ipv4_source.m3u",


        
    ]