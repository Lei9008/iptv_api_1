import os

class Config:
    """IPTV测速工具配置类，确保output文件夹与主脚本同目录"""
    # 1. 获取主脚本（speed_test.py）所在目录
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # 2. 并发与请求配置（可根据网络情况调整）
    CONCURRENT_LIMIT = 20    # 最大并发数（建议10-30）
    TIMEOUT = 10             # 单次请求超时时间（秒）
    RETRY_TIMES = 2          # 测速重试次数
    
    # 3. 延迟阈值配置（新增）：仅保留延迟≤该值的直播源（单位：毫秒）
    LATENCY_THRESHOLD = 1000  # 示例：1000ms，可根据需求修改（如1000=1秒）
    
    # 4. 目录与文件配置（output文件夹与主脚本同目录）
    OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")  # 输出目录
    LOG_FILE = os.path.join(OUTPUT_DIR, "function.log")  # 日志文件路径
    
    # 5. 远程IPTV源URL列表（可自行添加/修改）
    SOURCE_URLS = [
        "https://raw.githubusercontent.com/Lei9008/iptv_api_1/main/self_use/IPTV_Update/output/live_ipv4_source.m3u",
        "https://gh-proxy.com/https://raw.githubusercontent.com/Jsnzkpg/Jsnzkpg/Jsnzkpg/Jsnzkpg1.m3u",
        "https://wget.la/https://raw.githubusercontent.com/qingtingjjjjjjj/iptv-auto/main/output/tv.m3u",
        # 可添加更多源链接
    ]
   
