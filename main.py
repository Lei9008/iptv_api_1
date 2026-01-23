import re
import requests
import logging
import asyncio
import aiohttp
import time
from collections import OrderedDict
from datetime import datetime
import config
import os
import difflib
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional

# ===================== 数据结构 =====================
@dataclass
class SpeedTestResult:
    """测速结果数据类"""
    url: str
    latency: Optional[float] = None  # 延迟（毫秒）
    resolution: Optional[str] = None  # 分辨率
    success: bool = False  # 是否成功
    error: Optional[str] = None  # 错误信息

# ===================== 初始化配置 =====================
# 确保 output 文件夹存在
OUTPUT_FOLDER = Path("output")
OUTPUT_FOLDER.mkdir(exist_ok=True)

# 测速配置（可在config.py中配置，此处做默认值兜底）
DEFAULT_LATENCY_THRESHOLD = 500  # 延迟阈值（毫秒）
DEFAULT_CONCURRENT_LIMIT = 20    # 并发测速限制
DEFAULT_TIMEOUT = 10             # 超时时间（秒）
DEFAULT_RETRY_TIMES = 2          # 重试次数

# 日志配置
LOG_FILE_PATH = OUTPUT_FOLDER / "function.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, "w", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===================== 核心工具函数 =====================
def clean_channel_name(channel_name):
    """标准化清洗频道名称，提升匹配率"""
    if not channel_name:
        return ""
    # 第一步：专门处理CCTV5+等带+号的频道名，保留+号
    # 先把常见的CCTV5+变体统一为"CCTV5+"
    channel_name = re.sub(r'CCTV-?5\+', 'CCTV5+', channel_name)
    channel_name = re.sub(r'CCTV5\+\s*(\S+)', 'CCTV5+', channel_name)  # 去掉CCTV5+后面的多余文字
    
    # 第二步：清洗其他特殊字符（-放在最后避免解析为范围）
    # 注意：排除了+号，避免被清洗掉
    cleaned_name = re.sub(r'[$「」()（）\s-]', '', channel_name)
    
    # 数字标准化（如 05 → 5）
    cleaned_name = re.sub(r'(\D*)(\d+)', lambda m: m.group(1) + str(int(m.group(2))), cleaned_name)
    return cleaned_name.upper()

def is_ipv6(url):
    """判断URL是否为IPv6地址"""
    if not url:
        return False
    return re.match(r'^http:\/\/\[[0-9a-fA-F:]+\]', url) is not None

def find_similar_name(target_name, name_list, cutoff=0.4):
    """模糊匹配最相似的频道名"""
    if not target_name or not name_list:
        return None
    # 优先精确匹配（关键：避免CCTV5+被模糊匹配成其他）
    if target_name in name_list:
        return target_name
    # 模糊匹配
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=cutoff)
    return matches[0] if matches else None

def sort_and_filter_urls(urls, written_urls, latency_results: Dict[str, SpeedTestResult], latency_threshold):
    """排序和过滤URL（去重、黑名单、IP优先级、延迟过滤）"""
    if not urls:
        return []
    
    # 基础过滤：非空、未写入、不在黑名单、延迟达标
    filtered_urls = []
    for url in urls:
        url = url.strip()
        if not url or url in written_urls:
            continue
        
        # 黑名单过滤
        if any(blacklist in url for blacklist in getattr(config, 'url_blacklist', [])):
            continue
        
        # 延迟过滤
        result = latency_results.get(url)
        if not result or not result.success or result.latency is None or result.latency > latency_threshold:
            continue
        
        filtered_urls.append(url)
    
    # 按IP版本优先级排序
    ip_priority = getattr(config, 'ip_version_priority', 'ipv4')
    if ip_priority == "ipv6":
        filtered_urls.sort(key=lambda u: is_ipv6(u), reverse=True)
    else:
        filtered_urls.sort(key=lambda u: is_ipv6(u))
    
    # 按延迟升序排序（最优在前）
    filtered_urls.sort(key=lambda u: latency_results[u].latency)
    
    # 更新已写入集合
    written_urls.update(filtered_urls)
    return filtered_urls

def add_url_suffix(url, index, total_urls, ip_version, latency):
    """添加URL后缀，区分IP版本、线路和延迟"""
    if not url:
        return ""
    # 移除原有后缀
    base_url = url.split('$', 1)[0] if '$' in url else url
    # 生成新后缀（包含延迟信息）
    latency_str = f"{latency:.0f}ms"
    if total_urls == 1:
        suffix = f"${ip_version}({latency_str})"
    else:
        suffix = f"${ip_version}•线路{index}({latency_str})"
    return f"{base_url}{suffix}"

# ===================== 测速模块 =====================
class SpeedTester:
    """异步测速器"""
    def __init__(self):
        self.session = None
        self.concurrent_limit = getattr(config, 'CONCURRENT_LIMIT', DEFAULT_CONCURRENT_LIMIT)
        self.timeout = getattr(config, 'TIMEOUT', DEFAULT_TIMEOUT)
        self.retry_times = getattr(config, 'RETRY_TIMES', DEFAULT_RETRY_TIMES)
    
    async def __aenter__(self):
        """创建异步HTTP会话"""
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "Chrome/120.0.0.0 Safari/537.36"
        }
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭异步HTTP会话"""
        if self.session:
            await self.session.close()
    
    async def measure_latency(self, url: str) -> SpeedTestResult:
        """测量单个URL的延迟和分辨率"""
        result = SpeedTestResult(url=url)
        
        for attempt in range(self.retry_times + 1):
            try:
                start_time = time.time()
                async with self.session.get(url, ssl=False) as response:
                    # 计算延迟（毫秒）
                    latency = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        # 解析M3U8分辨率
                        resolution = "unknown"
                        content_type = response.headers.get("Content-Type", "")
                        
                        if "application/vnd.apple.mpegurl" in content_type:
                            try:
                                # 读取前1024字节解析分辨率
                                content = await response.content.read(1024)
                                res_match = re.search(rb"RESOLUTION=(\d+x\d+)", content)
                                if res_match:
                                    resolution = res_match.group(1).decode()
                            except Exception as e:
                                logger.debug(f"解析{url}分辨率失败：{str(e)[:30]}")
                        
                        result.latency = latency
                        result.resolution = resolution
                        result.success = True
                        logger.info(f"[{attempt+1}] {url[:50]} 成功 | 延迟: {latency:.2f}ms | 分辨率: {resolution}")
                        break
                    else:
                        result.error = f"HTTP状态码: {response.status}"
                        logger.warning(f"[{attempt+1}] {url[:50]} 失败 | 状态码: {response.status}")
            except asyncio.TimeoutError:
                result.error = "请求超时"
            except aiohttp.ClientConnectionError:
                result.error = "连接失败"
            except Exception as e:
                result.error = f"未知错误: {str(e)[:30]}"
            
            # 重试前等待1秒
            if attempt < self.retry_times:
                await asyncio.sleep(1)
        
        if not result.success:
            logger.warning(f"最终失败 {url[:50]} | 原因: {result.error}")
        
        return result
    
    async def batch_speed_test(self, urls: List[str]) -> Dict[str, SpeedTestResult]:
        """批量测速（带并发控制）"""
        results = {}
        semaphore = asyncio.Semaphore(self.concurrent_limit)
        
        async def worker(url):
            """测速工作函数"""
            async with semaphore:
                result = await self.measure_latency(url)
                results[url] = result
        
        # 创建并执行所有测速任务
        tasks = [worker(url) for url in urls if url.strip()]
        await asyncio.gather(*tasks)
        
        return results

# ===================== 模板解析与源抓取 =====================
def parse_template(template_file):
    """解析模板文件，提取频道分类和频道名称"""
    template_channels = OrderedDict()
    current_category = None

    try:
        with open(template_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                
                if "#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    template_channels[current_category] = []
                    logger.debug(f"模板第{line_num}行：识别分类 {current_category}")
                elif current_category:
                    channel_name = line.split(",")[0].strip()
                    template_channels[current_category].append(channel_name)
                    logger.debug(f"模板第{line_num}行：添加频道 {channel_name}")
    except FileNotFoundError:
        logger.error(f"模板文件不存在：{template_file}")
        return OrderedDict()
    except Exception as e:
        logger.error(f"解析模板失败：{str(e)}", exc_info=True)
        return OrderedDict()

    return template_channels

def parse_m3u_lines(lines):
    """解析M3U格式的频道列表行"""
    channels = OrderedDict()
    current_category = None
    channel_name = ""

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        
        if line.startswith("#EXTINF"):
            match = re.search(r'group-title="(.*?)",(.*)', line)
            if match:
                current_category = match.group(1).strip()
                channel_name = match.group(2).strip()
                # 修复：所有频道名都清洗，不只是CCTV开头
                channel_name = clean_channel_name(channel_name)
                if current_category not in channels:
                    channels[current_category] = []
            else:
                logger.warning(f"M3U第{line_num}行格式异常：{line}")
        elif not line.startswith("#"):
            channel_url = line.strip()
            if current_category and channel_name and channel_url:
                channels[current_category].append((channel_name, channel_url))

    return channels

def parse_txt_lines(lines):
    """解析TXT格式的频道列表行"""
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
                # 修复：所有频道名都清洗，不只是CCTV开头
                channel_name = clean_channel_name(channel_name)
                # 处理多URL（#分隔）
                channel_urls = match.group(2).strip().split('#')
                for url in channel_urls:
                    url = url.strip()
                    if url:
                        channels[current_category].append((channel_name, url))
            elif line:
                logger.warning(f"TXT第{line_num}行格式异常：{line}")

    return channels

def fetch_channels(url):
    """从指定URL抓取频道列表"""
    channels = OrderedDict()
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or 'utf-8'
        lines = response.text.split("\n")
        
        # 判断格式
        is_m3u = any(line.startswith("#EXTINF") for line in lines[:15])
        logger.info(f"成功抓取 {url}，格式：{'m3u' if is_m3u else 'txt'}")
        
        # 解析内容
        if is_m3u:
            channels = parse_m3u_lines(lines)
        else:
            channels = parse_txt_lines(lines)
            
    except requests.RequestException as e:
        logger.error(f"抓取 {url} 失败：{str(e)}", exc_info=True)

    return channels

def merge_channels(target, source):
    """合并两个频道字典（去重）"""
    for category, channel_list in source.items():
        if category not in target:
            target[category] = []
        # 去重合并
        existing = {(name, url) for name, url in target[category]}
        for name, url in channel_list:
            if (name, url) not in existing:
                target[category].append((name, url))
                existing.add((name, url))

# ===================== 频道匹配 =====================
def match_channels(template_channels, all_channels):
    """匹配模板中的频道与抓取到的频道（优化效率）"""
    matched_channels = OrderedDict()
    
    # 构建频道名到URL的映射（提升匹配效率）
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
            # 先清洗模板中的频道名（和源保持一致）
            cleaned_template_name = clean_channel_name(channel_name)
            # 模糊匹配
            similar_name = find_similar_name(cleaned_template_name, all_online_names)
            if similar_name:
                matched_channels[category][channel_name] = name_to_urls.get(similar_name, [])
                logger.debug(f"匹配成功：{channel_name} → {similar_name}")
            else:
                logger.warning(f"未匹配到频道：{channel_name}")
    
    return matched_channels

def filter_source_urls(template_file):
    """过滤源URL，获取匹配后的频道信息"""
    # 解析模板
    template_channels = parse_template(template_file)
    if not template_channels:
        logger.error("模板解析为空，终止流程")
        return OrderedDict(), OrderedDict()
    
    # 获取源URL配置
    source_urls = getattr(config, 'source_urls', [])
    if not source_urls:
        logger.error("未配置source_urls，终止流程")
        return OrderedDict(), template_channels
    
    # 抓取并合并所有源
    all_channels = OrderedDict()
    for url in source_urls:
        fetched_channels = fetch_channels(url)
        merge_channels(all_channels, fetched_channels)
    
    # 匹配频道
    matched_channels = match_channels(template_channels, all_channels)
    
    return matched_channels, template_channels

# ===================== 文件生成 =====================
def write_to_files(f_m3u, f_txt, category, channel_name, index, url, ip_version, latency):
    """写入M3U和TXT文件（包含延迟信息）"""
    if not url:
        return
    
    # 修复LOGO路径
    logo_url = f"./pic/logos/{channel_name}.png"
    # 写入M3U（添加延迟信息）
    display_name = f"{channel_name}({latency:.0f}ms)"
    f_m3u.write(
        f"#EXTINF:-1 tvg-id=\"{index}\" tvg-name=\"{channel_name}\" "
        f"tvg-logo=\"{logo_url}\" group-title=\"{category}\",{display_name}\n"
    )
    f_m3u.write(url + "\n")
    # 写入TXT
    f_txt.write(f"{channel_name},{url}\n")

def updateChannelUrlsM3U(channels, template_channels, latency_results: Dict[str, SpeedTestResult]):
    """更新频道URL到M3U和TXT文件中（添加延迟过滤）"""
    # 延迟阈值（默认500ms）
    latency_threshold = getattr(config, 'LATENCY_THRESHOLD', DEFAULT_LATENCY_THRESHOLD)
    # 已写入的URL集合（去重）
    written_urls_ipv4 = set()
    written_urls_ipv6 = set()

    # 文件路径
    current_date = datetime.now().strftime("%Y-%m-%d")
    ipv4_m3u_path = OUTPUT_FOLDER / "live_ipv4.m3u"
    ipv4_txt_path = OUTPUT_FOLDER / "live_ipv4.txt"
    ipv6_m3u_path = OUTPUT_FOLDER / "live_ipv6.m3u"
    ipv6_txt_path = OUTPUT_FOLDER / "live_ipv6.txt"

    # 获取EPG和公告配置
    epg_urls = getattr(config, 'epg_urls', [])
    announcements = getattr(config, 'announcements', [])

    try:
        with open(ipv4_m3u_path, "w", encoding="utf-8") as f_m3u_ipv4, \
             open(ipv4_txt_path, "w", encoding="utf-8") as f_txt_ipv4, \
             open(ipv6_m3u_path, "w", encoding="utf-8") as f_m3u_ipv6, \
             open(ipv6_txt_path, "w", encoding="utf-8") as f_txt_ipv6:

            # 写入M3U头部（EPG配置 + 延迟阈值说明）
            epg_str = ",".join(f'"{url}"' for url in epg_urls) if epg_urls else ""
            # 修复：去掉多余的括号
            header_note = f"# 延迟阈值：{latency_threshold}ms | 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            f_m3u_ipv4.write(f"#EXTM3U x-tvg-url={epg_str}\n{header_note}")
            f_m3u_ipv6.write(f"#EXTM3U x-tvg-url={epg_str}\n{header_note}")

            # 写入公告频道
            for group in announcements:
                channel_name = group.get('channel', '')
                if not channel_name:
                    continue
                # 写入分类
                f_txt_ipv4.write(f"{channel_name},#genre#\n")
                f_txt_ipv6.write(f"{channel_name},#genre#\n")
                
                for entry in group.get('entries', []):
                    entry_name = entry.get('name', current_date)
                    entry_url = entry.get('url', '')
                    entry_logo = entry.get('logo', '')
                    
                    if not entry_url:
                        continue
                    
                    # 公告频道也做延迟过滤
                    entry_result = latency_results.get(entry_url)
                    if entry_result and entry_result.success and entry_result.latency and entry_result.latency <= latency_threshold:
                        # 按IP版本分类写入
                        if is_ipv6(entry_url):
                            if entry_url not in written_urls_ipv6:
                                written_urls_ipv6.add(entry_url)
                                f_m3u_ipv6.write(
                                    f"#EXTINF:-1 tvg-id=\"1\" tvg-name=\"{entry_name}\" "
                                    f"tvg-logo=\"{entry_logo}\" group-title=\"{channel_name}\",{entry_name}({entry_result.latency:.0f}ms)\n"
                                )
                                f_m3u_ipv6.write(f"{entry_url}\n")
                                f_txt_ipv6.write(f"{entry_name},{entry_url}\n")
                        else:
                            if entry_url not in written_urls_ipv4:
                                written_urls_ipv4.add(entry_url)
                                f_m3u_ipv4.write(
                                    f"#EXTINF:-1 tvg-id=\"1\" tvg-name=\"{entry_name}\" "
                                    f"tvg-logo=\"{entry_logo}\" group-title=\"{channel_name}\",{entry_name}({entry_result.latency:.0f}ms)\n"
                                )
                                f_m3u_ipv4.write(f"{entry_url}\n")
                                f_txt_ipv4.write(f"{entry_name},{entry_url}\n")

            # 写入模板频道（带延迟过滤）
            for category, channel_list in template_channels.items():
                if not category or category not in channels:
                    continue
                
                # 写入分类
                f_txt_ipv4.write(f"{category},#genre#\n")
                f_txt_ipv6.write(f"{category},#genre#\n")
                
                for channel_name in channel_list:
                    if channel_name not in channels[category]:
                        continue
                    
                    # 获取该频道的所有URL
                    raw_urls = channels[category][channel_name]
                    
                    # 分离IPv4/IPv6并过滤（延迟<500ms）
                    ipv4_urls = sort_and_filter_urls(
                        [u for u in raw_urls if not is_ipv6(u)],
                        written_urls_ipv4,
                        latency_results,
                        latency_threshold
                    )
                    ipv6_urls = sort_and_filter_urls(
                        [u for u in raw_urls if is_ipv6(u)],
                        written_urls_ipv6,
                        latency_results,
                        latency_threshold
                    )
                    
                    # 写入IPv4 URL（带延迟信息）
                    total_ipv4 = len(ipv4_urls)
                    for idx, url in enumerate(ipv4_urls, start=1):
                        latency = latency_results[url].latency
                        new_url = add_url_suffix(url, idx, total_ipv4, "IPV4", latency)
                        write_to_files(f_m3u_ipv4, f_txt_ipv4, category, channel_name, idx, new_url, "IPV4", latency)
                    
                    # 写入IPv6 URL（带延迟信息）
                    total_ipv6 = len(ipv6_urls)
                    for idx, url in enumerate(ipv6_urls, start=1):
                        latency = latency_results[url].latency
                        new_url = add_url_suffix(url, idx, total_ipv6, "IPV6", latency)
                        write_to_files(f_m3u_ipv6, f_txt_ipv6, category, channel_name, idx, new_url, "IPV6", latency)

        # 生成测速报告
        generate_speed_report(latency_results, latency_threshold)
        
        logger.info(f"\n文件生成完成：")
        logger.info(f"  - IPv4 M3U: {ipv4_m3u_path}")
        logger.info(f"  - IPv4 TXT: {ipv4_txt_path}")
        logger.info(f"  - IPv6 M3U: {ipv6_m3u_path}")
        logger.info(f"  - IPv6 TXT: {ipv6_txt_path}")
        logger.info(f"  - 延迟阈值：{latency_threshold}ms")
        
    except Exception as e:
        logger.error(f"生成文件失败：{str(e)}", exc_info=True)

def generate_speed_report(latency_results: Dict[str, SpeedTestResult], latency_threshold):
    """生成测速报告"""
    report_path = OUTPUT_FOLDER / "speed_test_report.txt"
    
    # 分类统计
    total_urls = len(latency_results)
    success_urls = [r for r in latency_results.values() if r.success]
    valid_urls = [r for r in success_urls if r.latency and r.latency <= latency_threshold]
    
    # 按延迟排序
    valid_urls.sort(key=lambda x: x.latency)
    
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("IPTV直播源测速报告\n")
            f.write("="*60 + "\n")
            f.write(f"测试时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"延迟阈值：{latency_threshold}ms\n")
            f.write(f"总测试URL数：{total_urls}\n")
            f.write(f"测试成功数：{len(success_urls)} ({len(success_urls)/total_urls*100:.1f}%)\n")
            f.write(f"有效URL数（延迟<{latency_threshold}ms）：{len(valid_urls)}\n")
            f.write("="*60 + "\n\n")
            
            # 有效URL详情
            f.write("【有效URL列表（按延迟升序）】\n")
            for idx, result in enumerate(valid_urls, 1):
                f.write(f"{idx:3d}. 延迟：{result.latency:6.2f}ms | 分辨率：{result.resolution:8s} | URL：{result.url}\n")
            
            # 失败URL统计
            failed_urls = [r for r in latency_results.values() if not r.success]
            if failed_urls:
                f.write("\n【失败URL列表】\n")
                for idx, result in enumerate(failed_urls, 1):
                    f.write(f"{idx:3d}. 原因：{result.error:10s} | URL：{result.url}\n")
        
        logger.info(f"  - 测速报告：{report_path}")
    except Exception as e:
        logger.error(f"生成测速报告失败：{str(e)}", exc_info=True)

# ===================== 主程序 =====================
async def main():
    """主函数（异步执行）"""
    try:
        # 1. 配置加载
        template_file = getattr(config, 'TEMPLATE_FILE', "demo.txt")
        latency_threshold = getattr(config, 'LATENCY_THRESHOLD', DEFAULT_LATENCY_THRESHOLD)
        logger.info("===== 开始处理直播源 =====")
        logger.info(f"延迟阈值设置：{latency_threshold}ms")
        
        # 2. 抓取并匹配频道
        logger.info("\n===== 1. 抓取并匹配直播源 =====")
        channels, template_channels = filter_source_urls(template_file)
        if not channels:
            logger.error("无匹配的频道数据，终止流程")
            return
        
        # 3. 收集所有需要测速的URL
        all_urls = set()
        # 收集模板频道URL
        for category in channels.values():
            for urls in category.values():
                all_urls.update(urls)
        # 收集公告频道URL
        for group in getattr(config, 'announcements', []):
            for entry in group.get('entries', []):
                url = entry.get('url', '')
                if url:
                    all_urls.add(url)
        
        all_urls = list(all_urls)
        logger.info(f"\n===== 2. 开始批量测速（共{len(all_urls)}个URL） =====")
        
        # 4. 异步测速
        async with SpeedTester() as tester:
            latency_results = await tester.batch_speed_test(all_urls)
        
        # 5. 生成最终文件（过滤延迟>500ms的URL）
        logger.info("\n===== 3. 生成最终文件（过滤延迟>500ms） =====")
        updateChannelUrlsM3U(channels, template_channels, latency_results)
        
        logger.info("\n===== 所有流程执行完成 =====")
    
    except Exception as e:
        logger.critical(f"程序执行异常：{str(e)}", exc_info=True)

if __name__ == "__main__":
    # 兼容Windows异步事件循环
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 运行异步主程序
    asyncio.run(main())
