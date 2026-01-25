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
from typing import List, Dict, Optional, Tuple
from functools import lru_cache

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

# 初始化 logo 目录
LOGO_DIRS = [Path("./pic/logos"), Path("./pic/logo")]
for dir_path in LOGO_DIRS:
    dir_path.mkdir(parents=True, exist_ok=True)

# 从config.py读取GitHub Logo配置（核心优化）
# 读取Logo基础URL，设置默认值
GITHUB_LOGO_BASE_URL = getattr(config, 'GITHUB_LOGO_BASE_URL', 
                              "https://raw.githubusercontent.com/fanmingming/live/main/tv")
BACKUP_LOGO_BASE_URL = getattr(config, 'BACKUP_LOGO_BASE_URL',
                              "https://ghproxy.com/https://raw.githubusercontent.com/fanmingming/live/main/tv")
# 读取Logo API URL列表，设置默认值
GITHUB_LOGO_API_URLS = getattr(config, 'GITHUB_LOGO_API_URLS', [
    "https://api.github.com/repos/fanmingming/live/contents/main/tv",
    "https://ghproxy.com/https://api.github.com/repos/fanmingming/live/contents/main/tv"
])

# 测速配置（集中管理默认值）
CONFIG_DEFAULTS = {
    "LATENCY_THRESHOLD": 500,
    "CONCURRENT_LIMIT": 20,
    "TIMEOUT": 10,
    "RETRY_TIMES": 2,
    "IP_VERSION_PRIORITY": "ipv4",
    "URL_BLACKLIST": [],
    "TEMPLATE_FILE": "demo.txt",
    "EPG_URLS": [],
    "ANNOUNCEMENTS": [],
    "SOURCE_URLS": []
}

# GitHub 镜像域名列表（用于替换不可访问的域名）
GITHUB_MIRRORS = [
    "raw.githubusercontent.com",
    "raw.kkgithub.com",
    "raw.githubusercontents.com",
    "raw.fgit.cf",
    "raw.fgithub.de"
]

# 代理前缀列表
PROXY_PREFIXES = [
    "https://ghproxy.com/",
    "https://mirror.ghproxy.com/",
    "https://gh.api.99988866.xyz/"
]

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
def clean_channel_name(channel_name: str) -> str:
    """标准化清洗频道名称，提升匹配率"""
    if not channel_name:
        return ""
    # 保留CCTV5+等特殊标识
    channel_name = re.sub(r'CCTV-?5\+', 'CCTV5+', channel_name)
    channel_name = re.sub(r'CCTV5\+\s*(\S+)', 'CCTV5+', channel_name)
    # 移除特殊字符
    cleaned_name = re.sub(r'[$「」()（）\s-]', '', channel_name)
    # 数字标准化
    cleaned_name = re.sub(r'(\D*)(\d+)(\D*)', lambda m: m.group(1) + str(int(m.group(2))) + m.group(3), cleaned_name)
    return cleaned_name.upper()

def is_ipv6(url: str) -> bool:
    """判断URL是否为IPv6地址"""
    if not url:
        return False
    return re.match(r'^http:\/\/\[[0-9a-fA-F:]+\]', url) is not None

def find_similar_name(target_name: str, name_list: List[str], cutoff: float = 0.6) -> Optional[str]:
    """模糊匹配最相似的频道名"""
    if not target_name or not name_list:
        return None
    name_set = set(name_list)
    if target_name in name_set:
        return target_name
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=cutoff)
    return matches[0] if matches else None

def sort_and_filter_urls(
    urls: List[str], 
    written_urls: set, 
    latency_results: Dict[str, SpeedTestResult], 
    latency_threshold: float
) -> List[str]:
    """排序和过滤URL（去重、黑名单、IP优先级、延迟过滤）"""
    if not urls:
        return []
    
    filtered_urls = []
    url_blacklist = getattr(config, 'url_blacklist', [])
    
    for url in urls:
        url = url.strip()
        if not url or url in written_urls:
            continue
        
        # 黑名单过滤
        if any(blacklist in url for blacklist in url_blacklist):
            continue
        
        # 延迟过滤
        result = latency_results.get(url)
        if not result or not result.success or result.latency is None or result.latency > latency_threshold:
            continue
        
        filtered_urls.append(url)
    
    # 按IP版本优先级排序
    ip_priority = getattr(config, 'ip_version_priority', CONFIG_DEFAULTS["IP_VERSION_PRIORITY"])
    if ip_priority == "ipv6":
        filtered_urls.sort(key=lambda u: is_ipv6(u), reverse=True)
    else:
        filtered_urls.sort(key=lambda u: is_ipv6(u))
    
    # 按延迟升序排序
    filtered_urls.sort(key=lambda u: latency_results[u].latency)
    
    written_urls.update(filtered_urls)
    return filtered_urls

def add_url_suffix(url: str, index: int, total_urls: int, ip_version: str, latency: float) -> str:
    """添加URL后缀，区分IP版本、线路和延迟"""
    if not url:
        return ""
    base_url = url.split('$', 1)[0] if '$' in url else url
    ip_version = ip_version.lower()
    latency_str = f"{latency:.0f}ms"
    if total_urls == 1:
        suffix = f"${ip_version}({latency_str})"
    else:
        suffix = f"${ip_version}•线路{index}({latency_str})"
    return f"{base_url}{suffix}"

@lru_cache(maxsize=1)
def get_github_logo_list() -> List[str]:
    """获取GitHub仓库中的logo文件列表（缓存机制+代理）- 从config读取API URL"""
    headers = {"User-Agent": "Mozilla/5.0"}
    logo_files = []
    
    # 使用从config读取的API URL列表
    for api_url in GITHUB_LOGO_API_URLS:
        try:
            response = requests.get(api_url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            for item in data:
                if item.get("type") == "file" and item.get("name", "").lower().endswith(".png"):
                    logo_files.append(item["name"])
            
            logger.info(f"成功获取GitHub logo列表，共{len(logo_files)}个文件（来源：{api_url}）")
            break
        except Exception as e:
            logger.warning(f"获取GitHub logo列表失败（{api_url}）：{str(e)[:50]}")
            continue
    
    # 兜底：预设常见logo列表
    if not logo_files:
        logger.info("使用预设logo列表兜底")
        logo_files = [
            "CCTV1.png", "CCTV2.png", "CCTV3.png", "CCTV4.png", "CCTV5.png", "CCTV5PLUS.png",
            "CCTV6.png", "CCTV7.png", "CCTV8.png", "CCTV9.png", "CCTV10.png", "CCTV11.png",
            "CCTV12.png", "CCTV13.png", "CCTV14.png", "CCTV15.png", "湖南卫视.png", "浙江卫视.png",
            "江苏卫视.png", "东方卫视.png", "北京卫视.png", "安徽卫视.png"
        ]
    
    return logo_files

def get_channel_logo_url(channel_name: str) -> str:
    """检测logo文件，生成动态logo_url - 从config读取基础URL"""
    clean_logo_name = clean_channel_name(channel_name)
    logo_filename = f"{clean_logo_name}.png"
    
    # 检测本地logo
    for logo_dir in LOGO_DIRS:
        local_logo_path = logo_dir / logo_filename
        if local_logo_path.exists():
            return local_logo_path.as_posix()
    
    # 检测GitHub远程logo（使用从config读取的URL）
    github_logo_files = get_github_logo_list()
    if logo_filename in github_logo_files:
        return f"{BACKUP_LOGO_BASE_URL}/{logo_filename}"
    
    # 模糊匹配
    candidate_names = [
        logo_filename,
        logo_filename.replace("+", "PLUS"),
        logo_filename.upper(),
        logo_filename.lower()
    ]
    for candidate in candidate_names:
        if candidate in github_logo_files:
            return f"{BACKUP_LOGO_BASE_URL}/{candidate}"
    
    similar_logo = find_similar_name(clean_logo_name, [f.replace(".png", "") for f in github_logo_files], cutoff=0.7)
    if similar_logo:
        return f"{BACKUP_LOGO_BASE_URL}/{similar_logo}.png"
    
    return ""

# ===================== 通用频道提取函数 =====================
def extract_channels_from_content(content: str) -> List[Tuple[str, str]]:
    """
    从任意文本内容中提取频道名和URL
    :param content: 抓取到的直播源文本内容
    :return: 列表[(频道名, URL), ...]
    """
    channels = []
    # 去重集合
    seen_pairs = set()
    
    # 正则1：匹配 "频道名,URL" 或 "URL,频道名" 格式（最常见）
    pattern1 = r'([^,]+),\s*(https?://[^\s,]+)'
    # 正则2：匹配 M3U 格式（#EXTINF:...,频道名\nURL）
    pattern2 = r'#EXTINF:-?\d+\s*(?:[^,]+,)?\s*([^\\n]+)\n\s*(https?://[^\s]+)'
    # 正则3：匹配单独的URL（尝试从上下文提取频道名）
    pattern3 = r'(https?://[^\s]+)'
    
    # 第一步：匹配格式1（频道名,URL / URL,频道名）
    matches1 = re.findall(pattern1, content, re.IGNORECASE | re.MULTILINE)
    for match in matches1:
        part1, part2 = match[0].strip(), match[1].strip()
        if part1.startswith(("http://", "https://")):
            url, name = part1, part2
        else:
            name, url = part1, part2
        
        # 清洗和验证
        name = clean_channel_name(name)
        if not name or not url.startswith(("http://", "https://")):
            continue
        
        # 去重
        pair = (name, url)
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            channels.append(pair)
    
    # 第二步：匹配格式2（M3U格式）
    matches2 = re.findall(pattern2, content, re.IGNORECASE | re.MULTILINE | re.DOTALL)
    for match in matches2:
        name, url = match[0].strip(), match[1].strip()
        name = clean_channel_name(name)
        if not name or not url.startswith(("http://", "https://")):
            continue
        
        pair = (name, url)
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            channels.append(pair)
    
    # 第三步：匹配单独的URL（尝试提取频道名）
    matches3 = re.findall(pattern3, content, re.IGNORECASE | re.MULTILINE)
    for url in matches3:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            continue
        
        # 从URL中提取简易频道名
        name = "未知频道"
        # 从URL路径中提取关键词
        url_parts = url.split("/")
        for part in url_parts:
            if part and not part.startswith(("http", "www", "live", "stream")) and len(part) > 2:
                name = clean_channel_name(part)
                break
        
        pair = (name, url)
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            channels.append(pair)
    
    logger.info(f"从内容中提取到 {len(channels)} 个有效频道")
    return channels

# ===================== 链接修复和重试函数 =====================
def replace_github_domain(url: str) -> List[str]:
    """
    替换GitHub域名，生成多个可访问的镜像链接
    :param url: 原始URL
    :return: 多个候选URL列表
    """
    if not url or "github" not in url.lower():
        return [url]
    
    candidate_urls = [url]
    
    # 替换不同的GitHub镜像域名
    for mirror in GITHUB_MIRRORS:
        for original in GITHUB_MIRRORS:
            if original in url:
                new_url = url.replace(original, mirror)
                if new_url not in candidate_urls:
                    candidate_urls.append(new_url)
    
    # 添加代理前缀
    proxy_urls = []
    for base_url in candidate_urls:
        for proxy in PROXY_PREFIXES:
            if not base_url.startswith(proxy):
                proxy_url = proxy + base_url
                proxy_urls.append(proxy_url)
    
    candidate_urls.extend(proxy_urls)
    
    # 去重并返回
    unique_urls = list(dict.fromkeys(candidate_urls))
    return unique_urls

def fetch_url_with_retry(url: str, timeout: int = 15) -> Optional[str]:
    """
    带重试和镜像替换的URL抓取函数
    :param url: 原始URL
    :param timeout: 超时时间
    :return: 抓取到的内容，失败返回None
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # 生成候选URL列表
    candidate_urls = replace_github_domain(url)
    
    for idx, candidate in enumerate(candidate_urls):
        try:
            logger.debug(f"尝试抓取 [{idx+1}/{len(candidate_urls)}]: {candidate}")
            response = requests.get(
                candidate,
                headers=headers,
                timeout=timeout,
                verify=False,  # 忽略SSL证书错误
                allow_redirects=True
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding or 'utf-8'
            logger.info(f"成功抓取：{candidate}")
            return response.text
        except requests.RequestException as e:
            logger.warning(f"抓取失败 [{idx+1}/{len(candidate_urls)}]: {candidate} | 原因：{str(e)[:50]}")
            continue
    
    logger.error(f"所有候选链接都抓取失败：{url}")
    return None

# ===================== 测速模块 =====================
class SpeedTester:
    """异步测速器"""
    def __init__(self):
        self.session = None
        self.concurrent_limit = getattr(config, 'CONCURRENT_LIMIT', CONFIG_DEFAULTS["CONCURRENT_LIMIT"])
        self.timeout = getattr(config, 'TIMEOUT', CONFIG_DEFAULTS["TIMEOUT"])
        self.retry_times = getattr(config, 'RETRY_TIMES', CONFIG_DEFAULTS["RETRY_TIMES"])
    
    async def __aenter__(self):
        """创建异步HTTP会话"""
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
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
                async with self.session.get(url) as response:
                    latency = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        # 解析分辨率
                        resolution = "unknown"
                        content_type = response.headers.get("Content-Type", "")
                        if "application/vnd.apple.mpegurl" in content_type:
                            try:
                                content = await response.content.read(1024)
                                res_match = re.search(rb"RESOLUTION=(\d+x\d+)", content)
                                if res_match:
                                    resolution = res_match.group(1).decode()
                            except Exception as e:
                                logger.debug(f"解析{url[:60]}分辨率失败：{str(e)[:30]}")
                        
                        result.latency = latency
                        result.resolution = resolution
                        result.success = True
                        logger.info(f"[{attempt+1}] {url[:60]} 成功 | 延迟: {latency:.2f}ms | 分辨率: {resolution}")
                        break
                    else:
                        result.error = f"HTTP状态码: {response.status}"
                        logger.warning(f"[{attempt+1}] {url[:60]} 失败 | 状态码: {response.status}")
            except asyncio.TimeoutError:
                result.error = "请求超时"
            except aiohttp.ClientConnectionError:
                result.error = "连接失败"
            except Exception as e:
                result.error = f"未知错误: {str(e)[:30]}"
            
            if attempt < self.retry_times:
                await asyncio.sleep(1)
        
        if not result.success:
            logger.warning(f"最终失败 {url[:60]} | 原因: {result.error}")
        
        return result
    
    async def batch_speed_test(self, urls: List[str]) -> Dict[str, SpeedTestResult]:
        """批量测速"""
        results = {}
        semaphore = asyncio.Semaphore(self.concurrent_limit)
        
        async def worker(url):
            async with semaphore:
                result = await self.measure_latency(url)
                results[url] = result
        
        tasks = [worker(url) for url in urls if url.strip()]
        await asyncio.gather(*tasks)
        
        return results

# ===================== 模板解析与源抓取 =====================
def parse_template(template_file: str) -> OrderedDict:
    """解析模板文件，提取频道分类和频道名称（移除自动创建逻辑）"""
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
                elif current_category:
                    channel_name = line.split(",")[0].strip()
                    template_channels[current_category].append(channel_name)
    except FileNotFoundError:
        logger.error(f"模板文件不存在：{template_file}，请手动创建模板文件后再运行")
        return OrderedDict()
    except Exception as e:
        logger.error(f"解析模板失败：{str(e)}", exc_info=True)
        return OrderedDict()

    return template_channels

def fetch_channels(url: str) -> OrderedDict:
    """从指定URL抓取并提取频道（增强异常处理+多镜像重试）"""
    channels = OrderedDict()
    default_category = "默认分类"
    channels[default_category] = []
    
    try:
        # 使用增强的抓取函数（带重试和镜像替换）
        content = fetch_url_with_retry(url)
        if content is None:
            return channels
        
        # 核心：使用通用提取函数提取频道
        extracted_channels = extract_channels_from_content(content)
        channels[default_category].extend(extracted_channels)
            
    except Exception as e:
        logger.error(f"处理 {url} 时发生异常：{str(e)}", exc_info=True)

    return channels

def merge_channels(target: OrderedDict, source: OrderedDict):
    """合并两个频道字典（去重）"""
    for category, channel_list in source.items():
        if category not in target:
            target[category] = []
        
        existing = {(name, url) for name, url in target[category]}
        for name, url in channel_list:
            if (name, url) not in existing:
                target[category].append((name, url))
                existing.add((name, url))

def match_channels(template_channels: OrderedDict, all_channels: OrderedDict) -> OrderedDict:
    """匹配模板中的频道与抓取到的频道"""
    matched_channels = OrderedDict()
    
    # 构建频道名到URL的映射
    name_to_urls = {}
    all_online_names = set()
    for _, channel_list in all_channels.items():
        for name, url in channel_list:
            if name:
                all_online_names.add(name)
                name_to_urls.setdefault(name, []).append(url)
    
    all_online_names_list = list(all_online_names)
    
    # 遍历模板进行匹配
    for category, template_names in template_channels.items():
        matched_channels[category] = OrderedDict()
        for channel_name in template_names:
            cleaned_template_name = clean_channel_name(channel_name)
            similar_name = find_similar_name(cleaned_template_name, all_online_names_list)
            if similar_name:
                matched_channels[category][channel_name] = name_to_urls.get(similar_name, [])
                logger.debug(f"匹配成功：{channel_name} → {similar_name}")
            else:
                logger.warning(f"未匹配到频道：{channel_name}")
    
    return matched_channels

def filter_source_urls(template_file: str) -> Tuple[OrderedDict, OrderedDict]:
    """过滤源URL，获取匹配后的频道信息（增强容错）"""
    # 解析模板
    template_channels = parse_template(template_file)
    if not template_channels:
        logger.error("模板解析为空，终止流程")
        return OrderedDict(), OrderedDict()
    
    # 获取源URL配置
    source_urls = getattr(config, 'source_urls', CONFIG_DEFAULTS["SOURCE_URLS"])
    if not source_urls:
        logger.error("未配置source_urls，终止流程")
        return OrderedDict(), template_channels
    
    # 抓取并合并所有源（单个源失败不影响）
    all_channels = OrderedDict()
    failed_urls = []
    
    for url in source_urls:
        logger.info(f"\n开始抓取源：{url}")
        fetched_channels = fetch_channels(url)
        if not fetched_channels or not fetched_channels.get("默认分类"):
            failed_urls.append(url)
            logger.warning(f"源 {url} 未抓取到任何频道")
            continue
        
        merge_channels(all_channels, fetched_channels)
        logger.info(f"源 {url} 抓取完成，新增频道数：{len(fetched_channels['默认分类'])}")
    
    # 输出抓取统计
    total_channels = sum(len(ch_list) for _, ch_list in all_channels.items())
    logger.info(f"\n抓取统计：")
    logger.info(f"  - 总源数：{len(source_urls)}")
    logger.info(f"  - 失败源数：{len(failed_urls)}")
    logger.info(f"  - 成功抓取频道总数：{total_channels}")
    
    if failed_urls:
        logger.info(f"  - 失败的源：{', '.join(failed_urls)}")
    
    # 匹配频道
    matched_channels = match_channels(template_channels, all_channels)
    
    return matched_channels, template_channels

# ===================== 文件生成 =====================
def write_to_files(f_m3u, f_txt, category, channel_name, index, url, ip_version, latency):
    """写入M3U和TXT文件"""
    if not url:
        return
    
    logo_url = get_channel_logo_url(channel_name)
    
    # 写入M3U
    f_m3u.write(
        f"#EXTINF:-1 tvg-id=\"{index}\" tvg-name=\"{channel_name}\" "
        f"tvg-logo=\"{logo_url}\" group-title=\"{category}\",{channel_name}\n"
    )
    f_m3u.write(url + "\n")
    # 写入TXT
    f_txt.write(f"{channel_name},{url}\n")

def updateChannelUrlsM3U(channels, template_channels, latency_results: Dict[str, SpeedTestResult]):
    """更新频道URL到M3U和TXT文件中"""
    latency_threshold = getattr(config, 'LATENCY_THRESHOLD', CONFIG_DEFAULTS["LATENCY_THRESHOLD"])
    written_urls_ipv4 = set()
    written_urls_ipv6 = set()

    # 文件路径
    ipv4_m3u_path = OUTPUT_FOLDER / "live_ipv4.m3u"
    ipv4_txt_path = OUTPUT_FOLDER / "live_ipv4.txt"
    ipv6_m3u_path = OUTPUT_FOLDER / "live_ipv6.m3u"
    ipv6_txt_path = OUTPUT_FOLDER / "live_ipv6.txt"

    # 获取EPG和公告配置
    epg_urls = getattr(config, 'epg_urls', CONFIG_DEFAULTS["EPG_URLS"])
    announcements = getattr(config, 'announcements', CONFIG_DEFAULTS["ANNOUNCEMENTS"])

    try:
        with open(ipv4_m3u_path, "w", encoding="utf-8") as f_m3u_ipv4, \
             open(ipv4_txt_path, "w", encoding="utf-8") as f_txt_ipv4, \
             open(ipv6_m3u_path, "w", encoding="utf-8") as f_m3u_ipv6, \
             open(ipv6_txt_path, "w", encoding="utf-8") as f_txt_ipv6:

            # 写入M3U头部
            epg_str = ",".join(f'"{url}"' for url in epg_urls) if epg_urls else ""
            header_note = f"# 延迟阈值：{latency_threshold}ms | 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            f_m3u_ipv4.write(f"#EXTM3U x-tvg-url={epg_str}\n{header_note}")
            f_m3u_ipv6.write(f"#EXTM3U x-tvg-url={epg_str}\n{header_note}")

            # 写入公告频道
            announcement_id = 1
            for group in announcements:
                channel_name = group.get('channel', '')
                if not channel_name:
                    continue
                
                f_txt_ipv4.write(f"{channel_name},#genre#\n")
                f_txt_ipv6.write(f"{channel_name},#genre#\n")
                
                for entry in group.get('entries', []):
                    entry_name = entry.get('name', datetime.now().strftime("%Y-%m-%d"))
                    entry_url = entry.get('url', '')
                    entry_logo = entry.get('logo', '')
                    
                    if not entry_url:
                        continue
                    
                    entry_result = latency_results.get(entry_url)
                    if entry_result and entry_result.success and entry_result.latency and entry_result.latency <= latency_threshold:
                        if is_ipv6(entry_url):
                            if entry_url not in written_urls_ipv6:
                                written_urls_ipv6.add(entry_url)
                                f_m3u_ipv6.write(
                                    f"#EXTINF:-1 tvg-id=\"{announcement_id}\" tvg-name=\"{entry_name}\" "
                                    f"tvg-logo=\"{entry_logo}\" group-title=\"{channel_name}\",{entry_name}({entry_result.latency:.0f}ms)\n"
                                )
                                f_m3u_ipv6.write(f"{entry_url}\n")
                                f_txt_ipv6.write(f"{entry_name},{entry_url}\n")
                                announcement_id += 1
                        else:
                            if entry_url not in written_urls_ipv4:
                                written_urls_ipv4.add(entry_url)
                                f_m3u_ipv4.write(
                                    f"#EXTINF:-1 tvg-id=\"{announcement_id}\" tvg-name=\"{entry_name}\" "
                                    f"tvg-logo=\"{entry_logo}\" group-title=\"{channel_name}\",{entry_name}({entry_result.latency:.0f}ms)\n"
                                )
                                f_m3u_ipv4.write(f"{entry_url}\n")
                                f_txt_ipv4.write(f"{entry_name},{entry_url}\n")
                                announcement_id += 1

            # 写入模板频道
            for category, channel_list in template_channels.items():
                if not category or category not in channels:
                    continue
                
                f_txt_ipv4.write(f"{category},#genre#\n")
                f_txt_ipv6.write(f"{category},#genre#\n")
                
                for channel_name in channel_list:
                    if channel_name not in channels[category]:
                        continue
                    
                    raw_urls = channels[category][channel_name]
                    
                    # 分离IPv4/IPv6并过滤
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
                    
                    # 写入IPv4 URL
                    total_ipv4 = len(ipv4_urls)
                    for idx, url in enumerate(ipv4_urls, start=1):
                        latency = latency_results[url].latency
                        new_url = add_url_suffix(url, idx, total_ipv4, "IPV4", latency)
                        write_to_files(f_m3u_ipv4, f_txt_ipv4, category, channel_name, idx, new_url, "IPV4", latency)
                    
                    # 写入IPv6 URL
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

def generate_speed_report(latency_results: Dict[str, SpeedTestResult], latency_threshold: float):
    """生成测速报告"""
    report_path = OUTPUT_FOLDER / "speed_test_report.txt"
    
    total_urls = len(latency_results)
    success_urls = [r for r in latency_results.values() if r.success]
    valid_urls = [r for r in success_urls if r.latency and r.latency <= latency_threshold]
    valid_urls.sort(key=lambda x: x.latency)
    
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("IPTV直播源测速报告\n")
            f.write("="*60 + "\n")
            f.write(f"测试时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"延迟阈值：{latency_threshold}ms\n")
            f.write(f"总测试URL数：{total_urls}\n")
            success_rate = f"{len(success_urls)/total_urls*100:.1f}%" if total_urls > 0 else "0.0%"
            f.write(f"测试成功数：{len(success_urls)} ({success_rate})\n")
            f.write(f"有效URL数（延迟<{latency_threshold}ms）：{len(valid_urls)}\n")
            f.write("="*60 + "\n\n")
            
            if valid_urls:
                f.write("【有效URL列表（按延迟升序）】\n")
                for idx, result in enumerate(valid_urls, 1):
                    f.write(f"{idx:3d}. 延迟：{result.latency:6.2f}ms | 分辨率：{result.resolution:8s} | URL：{result.url}\n")
            else:
                f.write("【有效URL列表（按延迟升序）】\n")
                f.write("无有效URL\n")
            
            failed_urls = [r for r in latency_results.values() if not r.success]
            if failed_urls:
                f.write("\n【失败URL列表】\n")
                for idx, result in enumerate(failed_urls, 1):
                    f.write(f"{idx:3d}. 原因：{result.error:10s} | URL：{result.url}\n")
            else:
                f.write("\n【失败URL列表】\n")
                f.write("无失败URL\n")
        
        logger.info(f"  - 测速报告：{report_path}")
    except Exception as e:
        logger.error(f"生成测速报告失败：{str(e)}", exc_info=True)

# ===================== 主程序 =====================
async def main():
    """主函数（增强容错）"""
    try:
        # 配置加载
        template_file = getattr(config, 'TEMPLATE_FILE', CONFIG_DEFAULTS["TEMPLATE_FILE"])
        latency_threshold = getattr(config, 'LATENCY_THRESHOLD', CONFIG_DEFAULTS["LATENCY_THRESHOLD"])
        logger.info("===== 开始处理直播源 =====")
        logger.info(f"延迟阈值设置：{latency_threshold}ms")
        
        # 预加载GitHub logo列表
        get_github_logo_list()
        
        # 抓取并匹配频道
        logger.info("\n===== 1. 抓取并提取直播源频道 =====")
        channels, template_channels = filter_source_urls(template_file)
        if not channels:
            logger.error("无匹配的频道数据，终止流程")
            return
        
        # 收集所有需要测速的URL
        all_urls = set()
        for category in channels.values():
            for urls in category.values():
                all_urls.update(urls)
        for group in getattr(config, 'announcements', []):
            for entry in group.get('entries', []):
                url = entry.get('url', '')
                if url:
                    all_urls.add(url)
        
        all_urls = list(all_urls)
        logger.info(f"\n===== 2. 开始批量测速（共{len(all_urls)}个URL） =====")
        
        # 异步测速
        async with SpeedTester() as tester:
            latency_results = await tester.batch_speed_test(all_urls)
        
        # 生成最终文件
        logger.info("\n===== 3. 生成最终文件（过滤延迟>500ms） =====")
        updateChannelUrlsM3U(channels, template_channels, latency_results)
        
        logger.info("\n===== 所有流程执行完成 =====")
    
    except Exception as e:
        logger.critical(f"程序执行异常：{str(e)}", exc_info=True)

if __name__ == "__main__":
    # 兼容Windows异步事件循环
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 运行主程序
    asyncio.run(main())
