import os

# 1. 获取当前主脚本（speed_test.py）的目录路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 全局配置项
class Config:
    # 2. 并发与请求配置
    CONCURRENT_LIMIT = 20
    TIMEOUT = 10
    RETRY_TIMES = 2
    
    # 3. 目录与文件配置（output文件夹与主脚本同目录）
    OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
    # 日志文件：output文件夹下的function.log
    LOG_FILE = os.path.join(OUTPUT_DIR, "function.log")
    
    # 4. 远程直播源URL列表
    SOURCE_URLS = [
        "https://raw.githubusercontent.com/Lei9008/iptv_api_1/main/self_use/IPTV_Update/output/live_ipv4_source.m3u",



    ]