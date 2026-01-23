import re
import requests
import logging
from collections import OrderedDict
from datetime import datetime
import config
import os
import difflib
from pathlib import Path
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.parse

# ===================== 全局配置与初始化 =====================
# 使用Path简化路径操作，确保输出目录存在
BASE_DIR = Path(__file__).parent
OUTPUT_FOLDER = BASE_DIR / "output"
OUTPUT_FOLDER.mkdir(exist_ok=True)

# 日志配置（追加模式，保留历史日志，添加文件名/行号）
LOG_FILE_PATH = OUTPUT_FOLDER / "function.log"
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.handlers.clear()  # 清除默认处理器避免重复输出

# 日志格式：时间 - 级别 - 文件名:行号 - 信息
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 文件处理器（追加模式，避免清空历史日志）
file_handler = logging.FileHandler(LOG_FILE_PATH, "a", encoding="utf-8")
file_handler.setFormatter(formatter)

# 控制台处理器
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# 测速配置（可在config.py中覆盖）
DEFAULT_TIMEOUT = 5  # 测速超时时间（秒）
MAX_WORKERS = 10     # 并发测速线程数
DELAY_THRESHOLD = 600  # 延迟阈值（ms），小于此值才保留

# ===================== 速度测试工具类 =====================
class URLSpeedTester:
    """URL速度测试工具类：测量延迟、分辨率，支持并发测试"""
    
    def __init__(self, timeout=DEFAULT_TIMEOUT, max_workers=MAX_WORKERS):
        self.timeout = timeout
        self.max_workers = max_workers
        self.lock = threading.Lock()  # 线程安全锁
    
    def get_url_resolution(self, url: str) -> str:
        """
        解析URL对应的视频分辨率（简易版，支持常见格式）
        :param url: 播放地址
        :return: 分辨率字符串（如1080p/720p/480p/未知）
        """
        if not url:
            return "未知"
        
        # 从URL或参数中提取分辨率关键词
        url_lower = url.lower()
        resolution_keywords = {
            "1080p": ["1080p", "fhd", "1920x1080"],
            "720p": ["720p", "hd", "1280x720"],
            "480p": ["480p", "sd", "854x480"],
            "360p": ["360p", "ld", "640x360"]
        }
        
        for res, keywords in resolution_keywords.items():
            if any(kw in url_lower for kw in keywords):
                return res
        return "未知"
    
    def test_single_url_delay(self, url: str) -> tuple[float, str]:
        """
        测试单个URL的延迟（ms）和分辨率
        :param url: 待测试URL
        :return: (延迟时间(ms)，分辨率)，失败返回(-1, "未知")
        """
        if not url or not url.startswith(("http", "https")):
            return -1, "未知"
        
        try:
            # 解析域名，测试TCP连接延迟（更贴近实际播放延迟）
            parsed_url = urllib.parse.urlparse(url)
            if not parsed_url.netloc:
                return -1, "未知"
            
            # 开始计时
            start_time = time.perf_counter()
            
            # 发送HEAD请求（优先）或GET请求（部分服务器不支持HEAD）
            try:
                response = requests.head(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    timeout=self.timeout,
                    allow_redirects=True
                )
                response.raise_for_status()
            except requests.RequestException:
                # HEAD失败则尝试GET（仅获取头部，不下载内容）
                response = requests.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    timeout=self.timeout,
                    stream=True,
                    allow_redirects=True
                )
                response.raise_for_status()
                response.close()  # 立即关闭连接，避免下载内容
            
            # 计算延迟（转换为ms）
            delay_ms = (time.perf_counter() - start_time) * 1000
            delay_ms = round(delay_ms, 2)
            
            # 获取分辨率
            resolution = self.get_url_resolution(url)
            
            logger.debug(f"URL测速结果：{url} → 延迟：{delay_ms}ms，分辨率：{resolution}")
            return delay_ms, resolution
        
        except Exception as e:
            logger.warning(f"URL测速失败：{url} → {str(e)[:50]}")
            return -1, "未知"
    
    def batch_test_urls(self, urls: list) -> list[tuple[str, float, str]]:
        """
        批量测试URL列表，返回(URL, 延迟ms, 分辨率)
        :param urls: URL列表
        :return: 测试结果列表
        """
        if not urls:
            return []
        
        results = []
        # 使用线程池并发测试
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_url = {
                executor.submit(self.test_single_url_delay, url): url
                for url in urls
            }
            
            # 处理完成的任务
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    delay_ms, resolution = future.result()
                    with self.lock:
                        results.append((url, delay_ms, resolution))
                except Exception as e:
                    logger.error(f"批量测速异常：{url} → {e}")
                    with self.lock:
                        results.append((url, -1, "未知"))
        
        return results

# ===================== 工具函数 =====================
def clean_channel_name(channel_name):
    """标准化清洗频道名称，处理特殊字符、空白和数字格式"""
    if not channel_name:
        return ""
    cleaned_name = re.sub(r'[$「」-]', '', channel_name)  # 去掉特殊字符
    cleaned_name = re.sub(r'\s+', '', cleaned_name)  # 去掉所有空白字符
    # 数字格式化（如"CCTV 01"→"CCTV1"）
    cleaned_name = re.sub(r'(\D*)(\d+)', lambda m: m.group(1) + str(int(m.group(2))), cleaned_name)
    return cleaned_name.upper()  # 统一大写

def is_ipv6(url):
    """判断URL是否为IPv6地址"""
    if not url:
        return False
    return re.match(r'^http:\/\/\[[0-9a-fA-F:]+\]', url) is not None

def find_similar_name(target_name, name_list, cutoff=0.6):
    """模糊匹配最相似的频道名，返回匹配结果或None"""
    if not target_name or not name_list:
        return None
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=cutoff)
    return matches[0] if matches else None

def add_url_suffix(url, index, total_urls, ip_version, delay_ms=None, resolution=None):
    """为URL添加IP版本/线路/测速信息后缀"""
    if not url:
        return ""
    # 移除原有后缀，防止重复添加
    base_url = url.split('$', 1)[0] if '$' in url else url
    # 基础后缀（IP版本+线路）
    if total_urls == 1:
        suffix = f"${ip_version}"
    else:
        suffix = f"${ip_version}•线路{index}"
    # 追加测速信息（如果有）
    if delay_ms and delay_ms > 0 and resolution:
        suffix += f"•延迟{delay_ms}ms•{resolution}"
    return f"{base_url}{suffix}"

def sort_and_filter_urls(urls, written_urls, speed_tester: URLSpeedTester = None):
    """
    排序并过滤URL：去重、黑名单、IP版本优先级、测速过滤
    :param urls: 原始URL列表
    :param written_urls: 已写入的URL集合
    :param speed_tester: 测速工具实例
    :return: 过滤后的URL列表（含测速信息），格式：[(url, delay_ms, resolution), ...]
    """
    if not urls:
        return []
    
    # 获取配置项（容错处理）
    ip_priority = getattr(config, "ip_version_priority", "ipv4")
    url_blacklist = getattr(config, "url_blacklist", [])
    delay_threshold = getattr(config, "delay_threshold", DELAY_THRESHOLD)
    
    # 1. 基础过滤：非空、未写入、不在黑名单
    filtered_base = [
        url.strip() for url in urls
        if url and url.strip() and url not in written_urls
        and not any(bl in url for bl in url_blacklist)
    ]
    
    # 2. 测速过滤（仅保留延迟<600ms的URL）
    filtered_with_speed = []
    if speed_tester and filtered_base:
        logger.info(f"开始测速，共{len(filtered_base)}个URL，阈值：{delay_threshold}ms")
        # 批量测速
        speed_results = speed_tester.batch_test_urls(filtered_base)
        # 过滤延迟符合要求的URL
        for url, delay_ms, resolution in speed_results:
            if 0 < delay_ms < delay_threshold:
                filtered_with_speed.append((url, delay_ms, resolution))
        logger.info(f"测速完成，保留{len(filtered_with_speed)}/{len(filtered_base)}个URL")
    else:
        # 无测速工具时，仅基础过滤（兼容原有逻辑）
        filtered_with_speed = [(url, 0, "未知") for url in filtered_base]
    
    # 3. 按IP版本优先级+延迟排序（延迟越低越靠前）
    def sort_key(item):
        url, delay_ms, _ = item
        # 先按IP优先级，再按延迟升序
        ip_key = is_ipv6(url) if ip_priority == "ipv6" else not is_ipv6(url)
        return (not ip_key, delay_ms)  # 优先级高的在前，延迟低的在前
    
    filtered_with_speed.sort(key=sort_key)
    
    # 4. 更新已写入集合
    written_urls.update([item[0] for item in filtered_with_speed])
    
    return filtered_with_speed

def write_to_files(f_m3u, f_txt, category, channel_name, index, new_url):
    """统一写入M3U和TXT文件，增加参数校验"""
    if not all([f_m3u, f_txt, category, channel_name, new_url]):
        logger.warning(f"写入文件参数不全，跳过：{channel_name} - {new_url}")
        return
    
    # 修复LOGO路径（添加分隔符）
    logo_url = f"./pic/logos/{channel_name}.png"
    # 写入M3U格式
    f_m3u.write(
        f"#EXTINF:-1 tvg-id=\"{index}\" tvg-name=\"{channel_name}\" "
        f"tvg-logo=\"{logo_url}\" group-title=\"{category}\",{channel_name}\n"
    )
    f_m3u.write(f"{new_url}\n")
    # 写入TXT格式
    f_txt.write(f"{channel_name},{new_url}\n")

# ===================== 解析函数 =====================
def parse_template(template_file):
    """解析模板文件，提取分类和频道名，增加异常处理"""
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
                    logger.debug(f"模板第{line_num}行：识别分类 {current_category}")
                elif current_category:
                    # 提取频道名
                    channel_name = line.split(",")[0].strip()
                    template_channels[current_category].append(channel_name)
                    logger.debug(f"模板第{line_num}行：添加频道 {channel_name} 到分类 {current_category}")
    
    except FileNotFoundError:
        logger.error(f"模板文件不存在：{template_file}")
        return OrderedDict()
    except Exception as e:
        logger.error(f"解析模板文件失败：{e}", exc_info=True)
        return OrderedDict()
    
    return template_channels

def parse_m3u_lines(lines):
    """解析M3U格式行，修复channel_name未定义问题，增强容错"""
    channels = OrderedDict()
    current_category = None
    current_channel_name = None  # 初始化变量，避免UnboundLocalError
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        
        if line.startswith("#EXTINF"):
            # 提取分类和频道名（增强正则匹配）
            match = re.search(r'group-title=["\'](.*?)["\'].*?,([^#\n\r]+)', line)
            if match:
                current_category = match.group(1).strip()
                current_channel_name = match.group(2).strip()
                # 仅清洗CCTV开头的频道名
                if current_channel_name and current_channel_name.startswith("CCTV"):
                    current_channel_name = clean_channel_name(current_channel_name)
                # 初始化分类容器
                if current_category not in channels:
                    channels[current_category] = []
                logger.debug(f"M3U第{line_num}行：解析到 {current_category} - {current_channel_name}")
            else:
                logger.warning(f"M3U第{line_num}行格式异常：{line}")
                current_channel_name = None  # 重置，避免污染后续解析
        elif not line.startswith("#"):
            # 播放地址行
            channel_url = line
            # 仅当分类和频道名都有效时添加
            if current_category and current_channel_name and channel_url:
                channels[current_category].append((current_channel_name, channel_url))
            else:
                logger.warning(f"M3U第{line_num}行无匹配频道信息：{channel_url}")
    
    return channels

def parse_txt_lines(lines):
    """解析TXT格式行，增强边界处理"""
    channels = OrderedDict()
    current_category = None
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        if "#genre#" in line:
            # 提取分类名
            current_category = line.split(",")[0].strip()
            channels[current_category] = []
            logger.debug(f"TXT第{line_num}行：识别分类 {current_category}")
        elif current_category:
            match = re.match(r"^(.*?),(.*?)$", line)
            if match:
                channel_name = match.group(1).strip()
                # 清洗CCTV开头的频道名
                if channel_name and channel_name.startswith("CCTV"):
                    channel_name = clean_channel_name(channel_name)
                # 处理多URL（#分隔）
                channel_urls = match.group(2).strip().split('#')
                for url in channel_urls:
                    url = url.strip()
                    if url:  # 仅添加非空URL
                        channels[current_category].append((channel_name, url))
            elif line:
                # 兼容无URL的频道行
                logger.warning(f"TXT第{line_num}行无URL：{line}")
                channels[current_category].append((line, ''))
    
    return channels

# ===================== 核心业务函数 =====================
def fetch_channels(url):
    """从URL抓取频道列表，自动识别M3U/TXT格式"""
    channels = OrderedDict()
    
    try:
        # 优化请求：添加超时、请求头，避免被拦截
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or 'utf-8'
        lines = response.text.split("\n")
        
        # 识别格式（结合内容和URL后缀，提高准确性）
        is_m3u = any(line.startswith("#EXTINF") for line in lines[:15]) or url.lower().endswith((".m3u", ".m3u8"))
        source_type = "m3u" if is_m3u else "txt"
        logger.info(f"成功抓取 {url}，格式：{source_type}")
        
        # 解析内容
        if is_m3u:
            channels = parse_m3u_lines(lines)
        else:
            channels = parse_txt_lines(lines)
        
        # 日志输出解析结果
        if channels:
            categories = ", ".join(channels.keys())
            logger.info(f"{url} 包含分类：{categories}，总频道数：{sum(len(v) for v in channels.values())}")
        else:
            logger.warning(f"{url} 未解析到任何频道")
    
    except requests.RequestException as e:
        logger.error(f"抓取 {url} 失败：{e}", exc_info=True)
    
    return channels

def merge_channels(target, source):
    """合并频道字典，基于（频道名+URL）去重"""
    for category, channel_list in source.items():
        if category not in target:
            target[category] = []
        # 去重：用集合存储已存在的（名称+URL）
        existing = {(name, url) for name, url in target[category]}
        for name, url in channel_list:
            if (name, url) not in existing:
                target[category].append((name, url))
                existing.add((name, url))

def match_channels(template_channels, all_channels):
    """高效匹配模板频道与抓取的频道，避免多层循环"""
    matched_channels = OrderedDict()
    
    # 预处理：构建{频道名: [URL列表]}的映射，提升匹配效率
    name_to_urls = {}
    all_online_names = []
    for _, channel_list in all_channels.items():
        for name, url in channel_list:
            if name:
                all_online_names.append(name)
                name_to_urls.setdefault(name, []).append(url)
    
    # 遍历模板进行匹配
    for category, template_names in template_channels.items():
        matched_channels[category] = OrderedDict()
        for channel_name in template_names:
            # 模糊匹配相似名称
            similar_name = find_similar_name(channel_name, all_online_names)
            if similar_name:
                matched_channels[category][channel_name] = name_to_urls.get(similar_name, [])
                logger.debug(f"匹配成功：{channel_name} → {similar_name}")
            else:
                logger.warning(f"未匹配到频道：{channel_name}")
    
    return matched_channels

def filter_source_urls(template_file):
    """抓取并过滤源URL，返回匹配后的频道"""
    # 解析模板
    template_channels = parse_template(template_file)
    if not template_channels:
        logger.error("模板解析为空，终止流程")
        return OrderedDict(), template_channels
    
    # 抓取所有源URL
    source_urls = getattr(config, "source_urls", [])
    if not source_urls:
        logger.error("config中未配置source_urls，终止流程")
        return OrderedDict(), template_channels
    
    all_channels = OrderedDict()
    for url in source_urls:
        fetched = fetch_channels(url)
        merge_channels(all_channels, fetched)
    
    # 匹配频道
    matched_channels = match_channels(template_channels, all_channels)
    return matched_channels, template_channels

def updateChannelUrlsM3U(channels, template_channels):
    """生成IPv4/IPv6分离的M3U和TXT文件，整合测速过滤逻辑"""
    if not channels or not template_channels:
        logger.warning("无有效频道数据，跳过文件生成")
        return
    
    # 初始化测速工具
    speed_timeout = getattr(config, "speed_test_timeout", DEFAULT_TIMEOUT)
    speed_workers = getattr(config, "speed_test_workers", MAX_WORKERS)
    speed_tester = URLSpeedTester(timeout=speed_timeout, max_workers=speed_workers)
    
    # 文件路径
    ipv4_m3u_path = OUTPUT_FOLDER / "live_ipv4.m3u"
    ipv4_txt_path = OUTPUT_FOLDER / "live_ipv4.txt"
    ipv6_m3u_path = OUTPUT_FOLDER / "live_ipv6.m3u"
    ipv6_txt_path = OUTPUT_FOLDER / "live_ipv6.txt"
    
    # 已写入的URL（去重）
    written_urls_ipv4 = set()
    written_urls_ipv6 = set()
    
    # 处理公告配置（容错）
    current_date = datetime.now().strftime("%Y-%m-%d")
    announcements = getattr(config, "announcements", [])
    epg_urls = getattr(config, "epg_urls", [])
    
    try:
        with open(ipv4_m3u_path, "w", encoding="utf-8") as f_m3u_ipv4, \
             open(ipv4_txt_path, "w", encoding="utf-8") as f_txt_ipv4, \
             open(ipv6_m3u_path, "w", encoding="utf-8") as f_m3u_ipv6, \
             open(ipv6_txt_path, "w", encoding="utf-8") as f_txt_ipv6:
            
            # 写入M3U头部
            epg_str = ",".join(f'"{u}"' for u in epg_urls)
            f_m3u_ipv4.write(f"#EXTM3U x-tvg-url={epg_str}\n")
            f_m3u_ipv6.write(f"#EXTM3U x-tvg-url={epg_str}\n")
            
            # 写入公告频道（公告URL不参与测速）
            for group in announcements:
                group_name = group.get("channel", "公告")
                entries = group.get("entries", [])
                # 写入分类标识
                f_txt_ipv4.write(f"{group_name},#genre#\n")
                f_txt_ipv6.write(f"{group_name},#genre#\n")
                
                for entry in entries:
                    name = entry.get("name") or current_date
                    url = entry.get("url", "")
                    logo = entry.get("logo", "")
                    
                    if is_ipv6(url):
                        if url and url not in written_urls_ipv6:
                            written_urls_ipv6.add(url)
                            f_m3u_ipv6.write(
                                f"#EXTINF:-1 tvg-id=\"1\" tvg-name=\"{name}\" "
                                f"tvg-logo=\"{logo}\" group-title=\"{group_name}\",{name}\n"
                            )
                            f_m3u_ipv6.write(f"{url}\n")
                            f_txt_ipv6.write(f"{name},{url}\n")
                    else:
                        if url and url not in written_urls_ipv4:
                            written_urls_ipv4.add(url)
                            f_m3u_ipv4.write(
                                f"#EXTINF:-1 tvg-id=\"1\" tvg-name=\"{name}\" "
                                f"tvg-logo=\"{logo}\" group-title=\"{group_name}\",{name}\n"
                            )
                            f_m3u_ipv4.write(f"{url}\n")
                            f_txt_ipv4.write(f"{name},{url}\n")
            
            # 写入模板频道（参与测速过滤）
            for category, template_names in template_channels.items():
                f_txt_ipv4.write(f"{category},#genre#\n")
                f_txt_ipv6.write(f"{category},#genre#\n")
                
                if category not in channels:
                    continue
                
                for channel_name in template_names:
                    if channel_name not in channels[category]:
                        continue
                    
                    # 获取原始URL列表
                    raw_urls = channels[category][channel_name]
                    # 分离IPv4/IPv6
                    ipv4_urls = [u for u in raw_urls if not is_ipv6(u)]
                    ipv6_urls = [u for u in raw_urls if is_ipv6(u)]
                    
                    # 排序过滤（含测速，仅保留延迟<600ms的URL）
                    filtered_ipv4 = sort_and_filter_urls(ipv4_urls, written_urls_ipv4, speed_tester)
                    filtered_ipv6 = sort_and_filter_urls(ipv6_urls, written_urls_ipv6, speed_tester)
                    
                    # 写入IPv4频道（带测速信息）
                    for idx, (url, delay_ms, resolution) in enumerate(filtered_ipv4, 1):
                        new_url = add_url_suffix(url, idx, len(filtered_ipv4), "IPV4", delay_ms, resolution)
                        write_to_files(f_m3u_ipv4, f_txt_ipv4, category, channel_name, idx, new_url)
                    
                    # 写入IPv6频道（带测速信息）
                    for idx, (url, delay_ms, resolution) in enumerate(filtered_ipv6, 1):
                        new_url = add_url_suffix(url, idx, len(filtered_ipv6), "IPV6", delay_ms, resolution)
                        write_to_files(f_m3u_ipv6, f_txt_ipv6, category, channel_name, idx, new_url)
            
            # 结尾换行
            f_txt_ipv4.write("\n")
            f_txt_ipv6.write("\n")
        
        logger.info(f"文件生成完成（仅保留延迟<{DELAY_THRESHOLD}ms的URL）：")
        logger.info(f"- IPv4: {ipv4_m3u_path}, {ipv4_txt_path}")
        logger.info(f"- IPv6: {ipv6_m3u_path}, {ipv6_txt_path}")
    
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
