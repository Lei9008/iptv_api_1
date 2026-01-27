# config1.py - IPTV直播源处理程序 优化配置文件
# 版本：v2.0 优化版

import os
from pathlib import Path

# ===================== 基础配置 =====================
PROGRAM_NAME = "IPTV源处理工具"
LOG_LEVEL = "INFO"  # DEBUG/INFO/WARNING/ERROR
ENCODING = "utf-8"

# ===================== 路径配置 =====================
OUTPUT_DIR = Path("output")
OUTPUT_FILE_PREFIX = "iptv"
LOG_FILE_NAME = "iptv_process.log"

# ===================== 网络请求配置 =====================
FETCH_TIMEOUT = 15  # 超时时间（秒）
RETRY_TIMES = 3     # 重试次数
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
SSL_VERIFY = False  # 关闭SSL验证避免证书问题

# ===================== GitHub 相关配置 =====================
GITHUB_MIRRORS = [
    "raw.githubusercontent.com",
    "raw.kkgithub.com",
    "raw.githubusercontents.com",
    "raw.fgit.cf",
    "raw.fgithub.de",
    "raw.gitmirror.com",
]

GITHUB_PROXIES = [
    "https://ghproxy.com/",
    "https://mirror.ghproxy.com/",
    "https://gh.api.99988866.xyz/",
    "https://raw.fgit.cf/",
]

# ===================== M3U处理配置 =====================
KEEP_RAW_EXTINF = True  # 保留原始EXTINF行
URL_NORMALIZE_RULES = {
    "remove_params": True,    # 移除URL参数
    "remove_anchor": True,    # 移除锚点
    "remove_suffix": True,    # 移除自定义后缀
    "to_lowercase": True,     # 转为小写
}

# 智能分类关键词配置
CATEGORY_KEYWORDS = {
    "央视频道": ["CCTV", "央视", "中央", "CCTV1", "CCTV5+"],
    "卫视频道": ["卫视", "江苏", "浙江", "湖南", "东方", "北京", "广东"],
    "电影频道": ["电影", "影视", "影院", "MOVIE"],
    "体育频道": ["体育", "CCTV5", "NBA", "足球", "篮球"],
    "少儿频道": ["少儿", "卡通", "动画", "儿童", "CCTV14"],
    "新闻频道": ["新闻", "CCTV13", "财经", "资讯"],
    "地方频道": ["上海", "重庆", "四川", "山东", "河南", "河北"],
    "港澳台频道": ["TVB", "翡翠", "凤凰", "香港", "台湾", "澳门"],
}
DEFAULT_CATEGORY = "未分类频道"

# ===================== 去重配置 =====================
GLOBAL_DEDUPLICATION = True  # 全局URL去重
SORT_BY_CATEGORY = True      # 按分类排序输出

# ===================== 直播源配置（核心） =====================
SOURCE_URLS = [
    # 示例源（替换为你的源URL）
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/iptv.m3u",
    "https://ghproxy.com/https://raw.githubusercontent.com/iptv-org/iptv/master/channels/cn.m3u",
    # 本地文件支持
    # "file:///home/user/iptv/local.m3u",
    # "./local_iptv.txt",
]

# 源URL黑名单
SOURCE_BLACKLIST = [
    # "https://bad-source.com/iptv.m3u",
]

# ===================== 高级配置 =====================
GENERATE_DETAILED_REPORT = True  # 生成详细报告
GENERATE_TXT_BACKUP = True       # 生成TXT备份
MAX_CHANNELS = 0                 # 最大频道数（0=无限制）

# 频道名称清洗规则
CHANNEL_NAME_CLEAN_PATTERNS = {
    "remove_special_chars": r'[$「」()（）\s-]',
    "normalize_numbers": r'(\D*)(\d+)(\D*)',
    "keep_special_marks": r'CCTV-?5\+',
}

# ===================== 配置验证与辅助函数 =====================
def get_config(key, default=None):
    """安全获取配置项"""
    return globals().get(key, default)

def validate_config():
    """验证配置有效性"""
    # 检查日志级别
    valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if LOG_LEVEL not in valid_log_levels:
        print(f"警告：日志级别 {LOG_LEVEL} 无效，使用 INFO")
        globals()["LOG_LEVEL"] = "INFO"
    
    # 确保输出目录存在
    if OUTPUT_DIR and not OUTPUT_DIR.exists():
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        print(f"创建输出目录：{OUTPUT_DIR.absolute()}")
    
    # 过滤黑名单URL
    if SOURCE_URLS and SOURCE_BLACKLIST:
        original_count = len(SOURCE_URLS)
        SOURCE_URLS[:] = [url for url in SOURCE_URLS if url not in SOURCE_BLACKLIST]
        if len(SOURCE_URLS) < original_count:
            print(f"已过滤 {original_count - len(SOURCE_URLS)} 个黑名单URL")
    
    # 去重SOURCE_URLS
    original_count = len(SOURCE_URLS)
    SOURCE_URLS[:] = list(dict.fromkeys(SOURCE_URLS))
    if len(SOURCE_URLS) < original_count:
        print(f"已去重 {original_count - len(SOURCE_URLS)} 个重复源URL")
    
    return True

# 配置验证
if __name__ == "__main__":
    print("=== IPTV配置文件验证 ===")
    if validate_config():
        print(f"✅ 配置验证通过！")
        print(f"📝 日志级别：{LOG_LEVEL}")
        print(f"📁 输出目录：{OUTPUT_DIR.absolute()}")
        print(f"🔗 源URL数量：{len(SOURCE_URLS)}")
        print(f"📊 分类规则数量：{len(CATEGORY_KEYWORDS)}")
    else:
        print("❌ 配置验证失败！")
