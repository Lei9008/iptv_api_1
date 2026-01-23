import re
import requests
import logging
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
import difflib
# 假设config.py存在，若不存在需先创建
try:
    import config
except ImportError:
    raise ImportError("请确保config.py配置文件存在于当前目录！")

# ===================== 全局配置与初始化 =====================
# 使用Path类简化文件路径操作
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
LOG_FILE = BASE_DIR / "output" / "function.log"


# 日志配置（优化格式、添加文件名/行号、避免重复输出）
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.handlers.clear()  # 清除默认处理器，避免重复输出

# 日志格式：时间 - 级别 - 文件名:行号 - 信息
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 文件处理器（追加模式，避免每次运行清空）
file_handler = logging.FileHandler(LOG_FILE, "a", encoding="utf-8")
file_handler.setFormatter(formatter)

# 控制台处理器
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# ===================== 工具函数 =====================

def clean_channel_name(channel_name: str) -> str:
    """
    标准化清洗频道名称
    :param channel_name: 原始频道名
    :return: 清洗后的频道名
    """
    if not channel_name:
        return ""
    
    # 修复：转义-符号，避免被解析为字符范围
    # 将-放在字符集开头；
    cleaned_name = re.sub(r'[-$「」«»]', '', channel_name)  # 补充常见特殊字符
    cleaned_name = re.sub(r'\s+', '', cleaned_name)
    cleaned_name = re.sub(
        r'(\D*)(\d+)',
        lambda m: m.group(1) + str(int(m.group(2))),
        cleaned_name
    )
    return cleaned_name.upper()

def is_ipv6(url: str) -> bool:
    """判断URL是否为IPv6地址"""
    if not url:
        return False
    return re.match(r'^http:\/\/\[[0-9a-fA-F:]+\]', url) is not None


def find_similar_name(target_name: str, name_list: list, cutoff: float = 0.6) -> str | None:
    """
    模糊匹配最相似的频道名
    :param target_name: 目标名称
    :param name_list: 待匹配列表
    :param cutoff: 相似度阈值
    :return: 匹配到的名称或None
    """
    if not target_name or not name_list:
        return None
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=cutoff)
    return matches[0] if matches else None

def add_url_suffix(url: str, index: int, total_urls: int, ip_version: str) -> str:
    """为URL添加版本/线路后缀"""
    if not url:
        return ""
    # 移除原有后缀，避免重复
    base_url = url.split('$', 1)[0] if '$' in url else url
    # 生成新后缀
    if total_urls == 1:
        suffix = f"${ip_version}"
    else:
        suffix = f"${ip_version}•线路{index}"
    return f"{base_url}{suffix}"

def sort_and_filter_urls(urls: list, written_urls: set) -> list:
    """
    排序并过滤URL（去重、黑名单、IP优先级）
    :param urls: 原始URL列表
    :param written_urls: 已写入的URL集合（用于去重）
    :return: 处理后的URL列表
    """
    if not urls:
        return []
    
    # 1. 基础过滤：非空、未写入、不在黑名单
    blacklist = getattr(config, "url_blacklist", [])
    filtered = [
        url.strip() for url in urls
        if url and url.strip() and url not in written_urls
        and not any(bl in url for bl in blacklist)
    ]
    
    # 2. 按IP版本优先级排序
    ip_priority = getattr(config, "ip_version_priority", "ipv4")
    if ip_priority == "ipv6":
        # IPv6优先：True(IPv6)排在前面
        filtered.sort(key=lambda u: is_ipv6(u), reverse=True)
    else:
        # IPv4优先：False(IPv4)排在前面
        filtered.sort(key=lambda u: is_ipv6(u))
    
    # 3. 更新已写入集合
    written_urls.update(filtered)
    return filtered

def write_to_files(f_m3u, f_txt, category: str, channel_name: str, index: int, new_url: str):
    """统一写入M3U和TXT文件"""
    if not all([f_m3u, f_txt, category, channel_name, new_url]):
        return
    
    # LOGO路径优化：确保容错
    logo_url = f"https://github.com/fanmingming/live/tree/main/tv/{channel_name}.png"
    # M3U格式写入（完善元信息）
    f_m3u.write(
        f"#EXTINF:-1 tvg-id=\"{index}\" tvg-name=\"{channel_name}\" "
        f"tvg-logo=\"{logo_url}\" group-title=\"{category}\",{channel_name}\n"
    )
    f_m3u.write(f"{new_url}\n")
    
    
    # TXT格式写入
    f_txt.write(f"{channel_name},{new_url}\n")

# ===================== 解析相关函数 =====================
def parse_template(template_file: str | Path) -> OrderedDict:
    """
    解析模板文件，提取分类和频道名
    :param template_file: 模板文件路径
    :return: {分类: [频道名列表]}
    """
    template_channels = OrderedDict()
    current_category = None
    
    try:
        with open(template_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                # 跳过空行、注释行
                if not line or line.startswith("#"):
                    continue
                
                if "#genre#" in line:
                    # 提取分类名
                    current_category = line.split(",")[0].strip()
                    template_channels[current_category] = []
                    logger.debug(f"模板文件第{line_num}行：识别分类 {current_category}")
                elif current_category:
                    # 提取频道名
                    channel_name = line.split(",")[0].strip()
                    template_channels[current_category].append(channel_name)
                    logger.debug(f"模板文件第{line_num}行：添加频道 {channel_name} 到分类 {current_category}")
    
    except FileNotFoundError:
        logger.error(f"模板文件不存在：{template_file}")
    except Exception as e:
        logger.error(f"解析模板文件失败：{e}", exc_info=True)
    
    return template_channels

def parse_m3u_lines(lines: list) -> OrderedDict:
    """解析M3U格式的频道行"""
    channels = OrderedDict()
    current_category = None
    channel_name = ""  # 初始化，避免未定义
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        
        if line.startswith("#EXTINF"):
            # 提取M3U元信息
            match = re.search(r'group-title="(.*?)",\s*(.*)', line)
            if match:
                current_category = match.group(1).strip()
                channel_name = match.group(2).strip()
                # 清洗CCTV开头的频道名
                if channel_name and channel_name.startswith("CCTV"):
                    channel_name = clean_channel_name(channel_name)
                # 初始化分类
                if current_category not in channels:
                    channels[current_category] = []
            else:
                logger.warning(f"M3U第{line_num}行格式异常：{line}")
        elif not line.startswith("#"):
            # 播放地址行
            channel_url = line
            if current_category and channel_name and channel_url:
                channels[current_category].append((channel_name, channel_url))
    
    return channels

def parse_txt_lines(lines: list) -> OrderedDict:
    """解析TXT格式的频道行"""
    channels = OrderedDict()
    current_category = None
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        if "#genre#" in line:
            current_category = line.split(",")[0].strip()
            channels[current_category] = []
        elif current_category:
            match = re.match(r"^(.*?),(.*?)$", line)
            if match:
                channel_name = match.group(1).strip()
                if channel_name and channel_name.startswith("CCTV"):
                    channel_name = clean_channel_name(channel_name)
                # 处理多地址（#分隔）
                channel_urls = match.group(2).strip().split('#')
                for url in channel_urls:
                    url = url.strip()
                    if url:
                        channels[current_category].append((channel_name, url))
            else:
                # 兼容无地址的情况
                channels[current_category].append((line, ''))
    
    return channels

# ===================== 核心业务函数 =====================
def fetch_channels(url: str) -> OrderedDict:
    """
    从URL抓取频道列表（自动识别M3U/TXT）
    :param url: 源URL
    :return: {分类: [(频道名, 地址)]}
    """
    channels = OrderedDict()
    
    try:
        # 优化请求：添加超时、请求头
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or 'utf-8'
        lines = response.text.split("\n")
        
        # 判断格式
        is_m3u = any(line.startswith("#EXTINF") for line in lines[:15])
        source_type = "m3u" if is_m3u else "txt"
        logger.info(f"成功抓取 {url}，格式：{source_type}")
        
        # 解析内容
        if is_m3u:
            channels = parse_m3u_lines(lines)
        else:
            channels = parse_txt_lines(lines)
        
        # 日志输出分类信息
        if channels:
            categories = ", ".join(channels.keys())
            logger.info(f"{url} 包含分类：{categories}")
        else:
            logger.warning(f"{url} 未解析到任何频道")
    
    except requests.RequestException as e:
        logger.error(f"抓取 {url} 失败：{e}", exc_info=True)
    
    return channels

def merge_channels(target: OrderedDict, source: OrderedDict):
    """合并两个频道字典（去重）"""
    for category, channel_list in source.items():
        if category not in target:
            target[category] = []
        # 去重合并：基于（频道名+地址）去重
        existing = {(name, url) for name, url in target[category]}
        for name, url in channel_list:
            if (name, url) not in existing:
                target[category].append((name, url))
                existing.add((name, url))

def match_channels(template_channels: OrderedDict, all_channels: OrderedDict) -> OrderedDict:
    """
    匹配模板频道与抓取到的频道
    :param template_channels: 模板频道
    :param all_channels: 所有抓取到的频道
    :return: {模板分类: {模板频道名: [地址列表]}}
    """
    matched_channels = OrderedDict()
    
    # 收集所有在线频道名（用于匹配）
    all_online_names = []
    online_name_to_urls = {}  # 频道名 -> 地址列表
    for _, channel_list in all_channels.items():
        for name, url in channel_list:
            if name:
                all_online_names.append(name)
                online_name_to_urls.setdefault(name, []).append(url)
    
    # 遍历模板进行匹配
    for category, template_names in template_channels.items():
        matched_channels[category] = OrderedDict()
        for template_name in template_names:
            # 模糊匹配
            similar_name = find_similar_name(template_name, all_online_names)
            if similar_name:
                matched_channels[category][template_name] = online_name_to_urls.get(similar_name, [])
                logger.debug(f"匹配成功：{template_name} → {similar_name}")
            else:
                logger.warning(f"未匹配到频道：{template_name}")
    
    return matched_channels

def filter_source_urls(template_file: str | Path) -> tuple[OrderedDict, OrderedDict]:
    """
    抓取并过滤源URL，返回匹配后的频道
    :param template_file: 模板文件路径
    :return: (匹配后的频道, 模板频道)
    """
    # 解析模板
    template_channels = parse_template(template_file)
    if not template_channels:
        logger.error("模板解析为空，终止流程")
        return OrderedDict(), template_channels
    
    # 抓取所有源URL
    source_urls = getattr(config, "source_urls", [])
    if not source_urls:
        logger.error("未配置source_urls，终止流程")
        return OrderedDict(), template_channels
    
    all_channels = OrderedDict()
    for url in source_urls:
        fetched = fetch_channels(url)
        merge_channels(all_channels, fetched)
    
    # 匹配频道
    matched_channels = match_channels(template_channels, all_channels)
    return matched_channels, template_channels

def updateChannelUrlsM3U(channels: OrderedDict, template_channels: OrderedDict):
    """生成最终的M3U/TXT文件（IPv4/IPv6分离）"""
    if not channels or not template_channels:
        logger.warning("无有效频道数据，跳过文件生成")
        return
    
    # 文件路径
    ipv4_m3u = OUTPUT_DIR / "live_ipv4.m3u"
    ipv4_txt = OUTPUT_DIR / "live_ipv4.txt"
    ipv6_m3u = OUTPUT_DIR / "live_ipv6.m3u"
    ipv6_txt = OUTPUT_DIR / "live_ipv6.txt"
    
    # 已写入的URL（去重）
    written_ipv4 = set()
    written_ipv6 = set()
    
    # 获取配置项（容错）
    epg_urls = getattr(config, "epg_urls", [])
    announcements = getattr(config, "announcements", [])
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        with open(ipv4_m3u, "w", encoding="utf-8") as f_m3u4, \
             open(ipv4_txt, "w", encoding="utf-8") as f_txt4, \
             open(ipv6_m3u, "w", encoding="utf-8") as f_m3u6, \
             open(ipv6_txt, "w", encoding="utf-8") as f_txt6:
            
            # 写入M3U头部
            epg_str = ",".join(f'"{u}"' for u in epg_urls)
            f_m3u4.write(f"#EXTM3U x-tvg-url={epg_str}\n")
            f_m3u6.write(f"#EXTM3U x-tvg-url={epg_str}\n")
            
            # 写入公告类频道
            for group in announcements:
                group_name = group.get("channel", "公告")
                entries = group.get("entries", [])
                # 写入分类标识
                f_txt4.write(f"{group_name},#genre#\n")
                f_txt6.write(f"{group_name},#genre#\n")
                
                for entry in entries:
                    name = entry.get("name") or current_date
                    url = entry.get("url", "")
                    logo = entry.get("logo", "")
                    
                    if is_ipv6(url):
                        if url and url not in written_ipv6:
                            written_ipv6.add(url)
                            # 写入IPv6文件
                            f_m3u6.write(
                                f"#EXTINF:-1 tvg-id=\"1\" tvg-name=\"{name}\" "
                                f"tvg-logo=\"{logo}\" group-title=\"{group_name}\",{name}\n"
                            )
                            f_m3u6.write(f"{url}\n")
                            f_txt6.write(f"{name},{url}\n")
                    else:
                        if url and url not in written_ipv4:
                            written_ipv4.add(url)
                            # 写入IPv4文件
                            f_m3u4.write(
                                f"#EXTINF:-1 tvg-id=\"1\" tvg-name=\"{name}\" "
                                f"tvg-logo=\"{logo}\" group-title=\"{group_name}\",{name}\n"
                            )
                            f_m3u4.write(f"{url}\n")
                            f_txt4.write(f"{name},{url}\n")
            
            # 写入模板频道
            for category, template_names in template_channels.items():
                # 写入分类标识
                f_txt4.write(f"{category},#genre#\n")
                f_txt6.write(f"{category},#genre#\n")
                
                if category not in channels:
                    continue
                
                for channel_name in template_names:
                    if channel_name not in channels[category]:
                        continue
                    
                    # 获取并处理URL
                    raw_urls = channels[category][channel_name]
                    # 分离IPv4/IPv6
                    ipv4_urls = [u for u in raw_urls if not is_ipv6(u)]
                    ipv6_urls = [u for u in raw_urls if is_ipv6(u)]
                    
                    # 排序过滤
                    filtered_ipv4 = sort_and_filter_urls(ipv4_urls, written_ipv4)
                    filtered_ipv6 = sort_and_filter_urls(ipv6_urls, written_ipv6)
                    
                    # 写入IPv4频道
                    for idx, url in enumerate(filtered_ipv4, 1):
                        new_url = add_url_suffix(url, idx, len(filtered_ipv4), "IPV4")
                        write_to_files(f_m3u4, f_txt4, category, channel_name, idx, new_url)
                    
                    # 写入IPv6频道
                    for idx, url in enumerate(filtered_ipv6, 1):
                        new_url = add_url_suffix(url, idx, len(filtered_ipv6), "IPV6")
                        write_to_files(f_m3u6, f_txt6, category, channel_name, idx, new_url)
            
            # 结尾换行
            f_txt4.write("\n")
            f_txt6.write("\n")
        
        logger.info(f"文件生成完成：\n- IPv4: {ipv4_m3u}, {ipv4_txt}\n- IPv6: {ipv6_m3u}, {ipv6_txt}")
    
    except Exception as e:
        logger.error(f"生成文件失败：{e}", exc_info=True)

# ===================== 程序入口 =====================
if __name__ == "__main__":
    try:
        template_file = BASE_DIR / "demo.txt"
        # 核心流程
        matched_channels, template_channels = filter_source_urls(template_file)
        updateChannelUrlsM3U(matched_channels, template_channels)
        logger.info("程序执行完成！")
    except Exception as e:
        logger.critical(f"程序执行异常：{e}", exc_info=True)
