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
from typing import List, Dict, Optional, Tuple, Set
from functools import lru_cache
import warnings

# 屏蔽SSL不安全请求警告（解决日志中的InsecureRequestWarning）
warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

# ===================== 数据结构扩展 =====================
@dataclass
class SpeedTestResult:
    """测速结果数据类"""
    url: str
    latency: Optional[float] = None  # 延迟（毫秒）
    resolution: Optional[str] = None  # 分辨率
    success: bool = False  # 是否成功
    error: Optional[str] = None  # 错误信息

@dataclass
class ChannelMeta:
    """频道元信息（M3U标签提取）- 修复参数顺序：必填参数在前"""
    url: str  # 必填：播放URL
    channel_name: str  # 必填：标准化后的频道名
    tvg_id: Optional[str] = None  # 可选：tvg-id
    tvg_name: Optional[str] = None  # 可选：tvg-name
    tvg_logo: Optional[str] = None  # 可选：tvg-logo
    group_title: Optional[str] = None  # 可选：group-title

# ===================== 初始化配置（优化版） =====================
# 确保 output 文件夹存在
OUTPUT_FOLDER = Path("output")
OUTPUT_FOLDER.mkdir(exist_ok=True)

# 初始化 logo 目录
LOGO_DIRS = [Path("./pic/logos"), Path("./pic/logo")]
for dir_path in LOGO_DIRS:
    dir_path.mkdir(parents=True, exist_ok=True)

# 从config.py读取GitHub Logo配置（核心优化）
GITHUB_LOGO_BASE_URL = getattr(config, 'GITHUB_LOGO_BASE_URL', 
                              "https://raw.githubusercontent.com/fanmingming/live/main/tv")
BACKUP_LOGO_BASE_URL = getattr(config, 'BACKUP_LOGO_BASE_URL',
                              "https://ghproxy.com/https://raw.githubusercontent.com/fanmingming/live/main/tv")
GITHUB_LOGO_API_URLS = getattr(config, 'GITHUB_LOGO_API_URLS', [
    "https://api.github.com/repos/fanmingming/live/contents/main/tv",
    "https://ghproxy.com/https://api.github.com/repos/fanmingming/live/contents/main/tv"
])

# 测速配置（优化：新增匹配阈值、进度间隔配置）
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
    "SOURCE_URLS": [],
    "MATCH_CUTOFF": 0.4,  # 降低匹配阈值提升匹配率（原0.6）
    "PROGRESS_INTERVAL": 50  # 测速进度提示间隔
}

# GitHub 镜像域名列表
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

# 日志配置（优化：添加毫秒级时间戳，更精准）
LOG_FILE_PATH = OUTPUT_FOLDER / "function.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, "w", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 全局存储频道元信息（URL为键）
channel_meta_cache: Dict[str, ChannelMeta] = {}
# 新增：原始频道名映射（用于反向匹配）
raw_name_mapping: Dict[str, str] = {}

# ===================== 核心工具函数（深度优化） =====================
def clean_channel_name(channel_name: str) -> str:
    """标准化清洗频道名称（增强：支持港澳台/地方频道）"""
    if not channel_name:
        return ""
    
    # 保留特殊标识
    channel_name = re.sub(r'CCTV-?5\+', 'CCTV5+', channel_name)
    channel_name = re.sub(r'CCTV5\+\s*(\S+)', 'CCTV5+', channel_name)
    
    # 港澳台/凤凰卫视特殊处理（提升匹配率）
    channel_name = channel_name.replace("翡翠台", "TVB翡翠台")
    channel_name = channel_name.replace("凤凰中文", "凤凰卫视中文台")
    channel_name = channel_name.replace("凤凰资讯", "凤凰卫视资讯台")
    channel_name = channel_name.replace("凤凰香港", "凤凰卫视香港台")
    channel_name = channel_name.replace("凤凰卫视", "凤凰卫视中文台")
    channel_name = channel_name.replace("香港卫视", "香港卫视综合台")
    
    # 地方频道简化（解决菏泽二套/三套等匹配问题）
    channel_name = re.sub(r'(\w+)二套(\w+)', r'\12套\2', channel_name)
    channel_name = re.sub(r'(\w+)三套(\w+)', r'\13套\2', channel_name)
    channel_name = re.sub(r'经济生活', '经视', channel_name)
    channel_name = re.sub(r'影视', '影视频道', channel_name)
    channel_name = re.sub(r'文旅记录', '文旅', channel_name)
    
    # 移除特殊字符
    cleaned_name = re.sub(r'[$「」()（）\s-]', '', channel_name)
    # 数字标准化
    cleaned_name = re.sub(r'(\D*)(\d+)(\D*)', lambda m: m.group(1) + str(int(m.group(2))) + m.group(3), cleaned_name)
    
    # 保存原始名映射
    raw_name_mapping[cleaned_name.upper()] = channel_name
    return cleaned_name.upper()

def restore_raw_name(cleaned_name: str) -> str:
    """从标准化名恢复原始名"""
    return raw_name_mapping.get(cleaned_name, cleaned_name)

def is_ipv6(url: str) -> bool:
    """判断URL是否为IPv6地址"""
    if not url:
        return False
    return re.match(r'^http:\/\/\[[0-9a-fA-F:]+\]', url) is not None

def find_similar_name(target_name: str, name_list: List[str], cutoff: float = None) -> Optional[str]:
    """模糊匹配最相似的频道名（优化：动态阈值+多轮匹配）"""
    if not target_name or not name_list:
        return None
    
    # 使用配置的匹配阈值（默认0.4）
    cutoff = cutoff or getattr(config, 'MATCH_CUTOFF', CONFIG_DEFAULTS["MATCH_CUTOFF"])
    name_set = set(name_list)
    
    # 第一轮：精确匹配
    if target_name in name_set:
        return target_name
    
    # 第二轮：简化名匹配（如"凤凰卫视中文台" ↔ "凤凰中文"）
    simplified_target = re.sub(r'卫视|频道|综合|台', '', target_name)
    simplified_names = {re.sub(r'卫视|频道|综合|台', '', n): n for n in name_list}
    if simplified_target in simplified_names:
        return simplified_names[simplified_target]
    
    # 第三轮：模糊匹配
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=cutoff)
    if matches:
        return matches[0]
    
    # 第四轮：进一步降低阈值匹配
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=cutoff-0.1)
    return matches[0] if matches else None

def sort_and_filter_urls(
    urls: List[str], 
    written_urls: set, 
    latency_results: Dict[str, SpeedTestResult], 
    latency_threshold: float
) -> List[str]:
    """排序和过滤URL（优化：减少过度过滤）"""
    if not urls:
        return []
    
    filtered_urls = []
    url_blacklist = getattr(config, 'url_blacklist', [])
    
    for url in urls:
        url = url.strip()
        if not url or url in written_urls:
            continue
        
        # 优化：黑名单仅匹配关键词，而非完整URL
        blacklist_hit = False
        for blacklist in url_blacklist:
            if blacklist and blacklist in url:
                blacklist_hit = True
                break
        if blacklist_hit:
            continue
        
        # 优化：延迟过滤仅在测速完成后生效
        if latency_results:
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
    if latency_results:
        filtered_urls.sort(key=lambda u: latency_results[u].latency if latency_results.get(u) else 9999)
    
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
    """获取GitHub仓库中的logo文件列表（缓存机制+代理）"""
    headers = {"User-Agent": "Mozilla/5.0"}
    logo_files = []
    
    for api_url in GITHUB_LOGO_API_URLS:
        try:
            response = requests.get(api_url, headers=headers, timeout=10, verify=False)
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
    
    # 兜底：新增港澳台频道logo
    if not logo_files:
        logger.info("使用预设logo列表兜底")
        logo_files = [
            "CCTV1.png", "CCTV2.png", "CCTV3.png", "CCTV4.png", "CCTV5.png", "CCTV5PLUS.png",
            "CCTV6.png", "CCTV7.png", "CCTV8.png", "CCTV9.png", "CCTV10.png", "CCTV11.png",
            "CCTV12.png", "CCTV13.png", "CCTV14.png", "CCTV15.png", "湖南卫视.png", "浙江卫视.png",
            "江苏卫视.png", "东方卫视.png", "北京卫视.png", "安徽卫视.png", "TVB翡翠台.png",
            "凤凰卫视中文台.png", "凤凰卫视资讯台.png", "香港卫视综合台.png", "优漫卡通.png"
        ]
    
    return logo_files

def get_channel_logo_url(channel_name: str) -> str:
    """检测logo文件，生成动态logo_url（增强：支持港澳台频道）"""
    clean_logo_name = clean_channel_name(channel_name)
    logo_filename = f"{clean_logo_name}.png"
    
    # 优先使用M3U提取的logo
    for meta in channel_meta_cache.values():
        if meta.channel_name == clean_logo_name and meta.tvg_logo:
            return meta.tvg_logo
    
    # 检测本地logo
    for logo_dir in LOGO_DIRS:
        local_logo_path = logo_dir / logo_filename
        if local_logo_path.exists():
            return local_logo_path.as_posix()
    
    # 检测GitHub远程logo
    github_logo_files = get_github_logo_list()
    if logo_filename in github_logo_files:
        return f"{BACKUP_LOGO_BASE_URL}/{logo_filename}"
    
    # 港澳台频道特殊匹配
    special_mapping = {
        "TVB翡翠台.png": "翡翠台.png",
        "凤凰卫视中文台.png": ["凤凰中文.png", "凤凰卫视.png"],
        "凤凰卫视资讯台.png": ["凤凰资讯.png", "凤凰卫视.png"],
        "香港卫视综合台.png": ["香港卫视.png"]
    }
    for target_logo, aliases in special_mapping.items():
        if logo_filename == target_logo:
            for alias in aliases:
                if alias in github_logo_files:
                    return f"{BACKUP_LOGO_BASE_URL}/{alias}"
    
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
    
    similar_logo = find_similar_name(clean_logo_name, [f.replace(".png", "") for f in github_logo_files], cutoff=0.5)
    if similar_logo:
        return f"{BACKUP_LOGO_BASE_URL}/{similar_logo}.png"
    
    return ""

# ===================== M3U精准提取核心函数（重大优化） =====================
def extract_m3u_meta(content: str) -> List[ChannelMeta]:
    """
    精准提取M3U文件中的元信息（优化：兼容更多M3U变种格式）
    """
    # 优化正则：支持更多M3U格式变种
    m3u_pattern = re.compile(
        r"#EXTINF:\s*-?\d+\s*(.*?)\n\s*([^#\n\r\s].*?)(?=\s|#|$)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE
    )
    attr_pattern = re.compile(r'(\w+)-?(\w+)?="?(.*?)"?(?=\s|,|$)')
    
    meta_list = []
    matches = m3u_pattern.findall(content)
    
    for extinf_attrs, url in matches:
        url = url.strip()
        if not url or not url.startswith(("http://", "https://")):
            continue
        
        # 初始化元信息
        channel_name = "未知频道"
        tvg_id = None
        tvg_name = None
        tvg_logo = None
        group_title = None
        
        # 解析#EXTINF属性
        attr_matches = attr_pattern.findall(extinf_attrs)
        for attr1, attr2, value in attr_matches:
            attr_key = f"{attr1}-{attr2}".lower() if attr2 else attr1.lower()
            value = value.strip()
            if attr_key == "tvg-id":
                tvg_id = value
            elif attr_key == "tvg-name":
                tvg_name = value
                channel_name = clean_channel_name(value)
            elif attr_key == "tvg-logo":
                tvg_logo = value
            elif attr_key == "group-title":
                group_title = value
        
        # 优化：更强的频道名提取逻辑
        if channel_name == "未知频道":
            # 匹配最后一个逗号后的所有内容
            name_match = re.search(r',\s*(.+?)\s*$', extinf_attrs)
            if name_match:
                channel_name = clean_channel_name(name_match.group(1).strip())
            # 兜底：从URL提取
            else:
                url_parts = url.split("/")
                for part in url_parts:
                    if part and len(part) > 2 and not part.startswith(("http", "www", "live", "stream")):
                        channel_name = clean_channel_name(part)
                        break
        
        # 创建ChannelMeta实例
        meta = ChannelMeta(
            url=url,
            channel_name=channel_name,
            tvg_id=tvg_id,
            tvg_name=tvg_name,
            tvg_logo=tvg_logo,
            group_title=group_title
        )
        
        meta_list.append(meta)
        channel_meta_cache[url] = meta
    
    logger.info(f"M3U精准提取：{len(meta_list)}个频道元信息（匹配{len(matches)}个原始条目）")
    return meta_list

# ===================== 通用频道提取函数（增强版） =====================
def extract_channels_from_content(content: str) -> List[Tuple[str, str]]:
    """
    从任意文本内容中提取频道名和URL（增强：严格去重）
    """
    channels = []
    seen_pairs: Set[Tuple[str, str]] = set()
    seen_urls: Set[str] = set()  # 新增：URL全局去重
    
    # 第一步：优先处理M3U格式
    if "#EXTM3U" in content:
        m3u_meta_list = extract_m3u_meta(content)
        for meta in m3u_meta_list:
            pair = (meta.channel_name, meta.url)
            if pair not in seen_pairs and meta.url not in seen_urls:
                seen_pairs.add(pair)
                seen_urls.add(meta.url)
                channels.append(pair)
    
    # 第二步：兼容原有提取逻辑
    pattern1 = r'([^,]+),\s*(https?://[^\s,]+)'
    pattern3 = r'(https?://[^\s]+)'
    
    # 匹配格式1
    matches1 = re.findall(pattern1, content, re.IGNORECASE | re.MULTILINE)
    for match in matches1:
        part1, part2 = match[0].strip(), match[1].strip()
        if part1.startswith(("http://", "https://")):
            url, name = part1, part2
        else:
            name, url = part1, part2
        
        name = clean_channel_name(name)
        if not name or not url.startswith(("http://", "https://")):
            continue
        
        if (name, url) not in seen_pairs and url not in seen_urls:
            seen_pairs.add((name, url))
            seen_urls.add(url)
            channels.append((name, url))
    
    # 匹配格式3
    matches3 = re.findall(pattern3, content, re.IGNORECASE | re.MULTILINE)
    for url in matches3:
        url = url.strip()
        if not url.startswith(("http://", "https://")) or url in seen_urls:
            continue
        
        name = "未知频道"
        url_parts = url.split("/")
        for part in url_parts:
            if part and not part.startswith(("http", "www", "live", "stream")) and len(part) > 2:
                name = clean_channel_name(part)
                break
        
        if (name, url) not in seen_pairs:
            seen_pairs.add((name, url))
            seen_urls.add(url)
            channels.append((name, url))
    
    logger.info(f"从内容中提取到 {len(channels)} 个有效频道（含M3U精准提取，去重后）")
    return channels

# ===================== 链接修复和重试函数 =====================
def replace_github_domain(url: str) -> List[str]:
    """替换GitHub域名（优化：限制候选数量）"""
    if not url or "github" not in url.lower():
        return [url]
    
    candidate_urls = [url]
    
    for mirror in GITHUB_MIRRORS:
        for original in GITHUB_MIRRORS:
            if original in url:
                new_url = url.replace(original, mirror)
                if new_url not in candidate_urls:
                    candidate_urls.append(new_url)
    
    proxy_urls = []
    for base_url in candidate_urls:
        for proxy in PROXY_PREFIXES:
            if not base_url.startswith(proxy):
                proxy_url = proxy + base_url
                if proxy_url not in proxy_urls:
                    proxy_urls.append(proxy_url)
    
    candidate_urls.extend(proxy_urls)
    unique_urls = list(dict.fromkeys(candidate_urls))
    
    # 优化：限制候选数量，避免过多重试
    return unique_urls[:5]

def fetch_url_with_retry(url: str, timeout: int = 15) -> Optional[str]:
    """带重试和镜像替换的URL抓取函数（优化：分级超时）"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    candidate_urls = replace_github_domain(url)
    
    # 分级超时：首次快速失败，后续增加超时
    timeouts = [5, 10, 15, 15, 15]
    
    for idx, candidate in enumerate(candidate_urls):
        current_timeout = timeouts[min(idx, len(timeouts)-1)]
        try:
            logger.debug(f"尝试抓取 [{idx+1}/{len(candidate_urls)}]: {candidate} (超时：{current_timeout}s)")
            response = requests.get(
                candidate,
                headers=headers,
                timeout=current_timeout,
                verify=False,
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

# ===================== 测速模块（重大优化：进度反馈） =====================
class SpeedTester:
    """异步测速器（优化：添加进度提示+性能监控）"""
    def __init__(self):
        self.session = None
        self.concurrent_limit = getattr(config, 'CONCURRENT_LIMIT', CONFIG_DEFAULTS["CONCURRENT_LIMIT"])
        self.timeout = getattr(config, 'TIMEOUT', CONFIG_DEFAULTS["TIMEOUT"])
        self.retry_times = getattr(config, 'RETRY_TIMES', CONFIG_DEFAULTS["RETRY_TIMES"])
        self.progress_interval = getattr(config, 'PROGRESS_INTERVAL', CONFIG_DEFAULTS["PROGRESS_INTERVAL"])
        self.processed_count = 0
        self.total_count = 0
        self.start_time = None
    
    async def __aenter__(self):
        """创建异步HTTP会话（优化：TCP连接复用）"""
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        connector = aiohttp.TCPConnector(limit=self.concurrent_limit, ttl_dns_cache=300)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        }
        self.session = aiohttp.ClientSession(
            timeout=timeout, 
            headers=headers,
            connector=connector
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭异步HTTP会话"""
        if self.session:
            await self.session.close()
    
    def _update_progress(self):
        """更新测速进度"""
        self.processed_count += 1
        if self.processed_count % self.progress_interval == 0 or self.processed_count == self.total_count:
            elapsed = time.time() - self.start_time
            speed = self.processed_count / elapsed if elapsed > 0 else 0
            remaining = (self.total_count - self.processed_count) / speed if speed > 0 else 0
            logger.info(
                f"测速进度：{self.processed_count}/{self.total_count} "
                f"({self.processed_count/self.total_count*100:.1f}%) | "
                f"速度：{speed:.1f} URL/s | 剩余：{remaining:.0f}s"
            )
    
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
                        logger.debug(f"[{attempt+1}] {url[:60]} 成功 | 延迟: {latency:.2f}ms | 分辨率: {resolution}")
                        break
                    else:
                        result.error = f"HTTP状态码: {response.status}"
                        logger.debug(f"[{attempt+1}] {url[:60]} 失败 | 状态码: {response.status}")
            except asyncio.TimeoutError:
                result.error = "请求超时"
            except aiohttp.ClientConnectionError:
                result.error = "连接失败"
            except Exception as e:
                result.error = f"未知错误: {str(e)[:30]}"
            
            if attempt < self.retry_times:
                await asyncio.sleep(0.5)  # 优化：减少重试间隔
        
        # 更新进度
        self._update_progress()
        
        if not result.success:
            logger.debug(f"最终失败 {url[:60]} | 原因: {result.error}")
        
        return result
    
    async def batch_speed_test(self, urls: List[str]) -> Dict[str, SpeedTestResult]:
        """批量测速（优化：进度反馈+性能统计）"""
        results = {}
        self.total_count = len(urls)
        self.processed_count = 0
        self.start_time = time.time()
        
        if self.total_count == 0:
            logger.info("无URL需要测速")
            return results
        
        logger.info(f"开始批量测速：共{self.total_count}个URL | 并发数：{self.concurrent_limit} | 超时：{self.timeout}s")
        
        semaphore = asyncio.Semaphore(self.concurrent_limit)
        
        async def worker(url):
            async with semaphore:
                result = await self.measure_latency(url)
                results[url] = result
        
        tasks = [worker(url) for url in urls if url.strip()]
        await asyncio.gather(*tasks)
        
        # 统计测速结果
        success_count = sum(1 for r in results.values() if r.success)
        avg_latency = sum(r.latency for r in results.values() if r.success and r.latency) / success_count if success_count > 0 else 0
        elapsed = time.time() - self.start_time
        
        logger.info(
            f"测速完成：成功{success_count}/{self.total_count} "
            f"({success_count/self.total_count*100:.1f}%) | "
            f"平均延迟：{avg_latency:.2f}ms | 总耗时：{elapsed:.1f}s"
        )
        
        return results

# ===================== 模板解析与源抓取（优化匹配） =====================
def parse_template(template_file: str) -> OrderedDict:
    """解析模板文件（优化：保留原始频道名）"""
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

    logger.info(f"解析模板完成：{len(template_channels)}个分类，{sum(len(v) for v in template_channels.values())}个频道")
    return template_channels

def fetch_channels(url: str) -> OrderedDict:
    """从指定URL抓取并提取频道（优化：错误处理更友好）"""
    channels = OrderedDict()
    default_category = "默认分类"
    channels[default_category] = []
    
    try:
        content = fetch_url_with_retry(url)
        if content is None:
            return channels
        
        extracted_channels = extract_channels_from_content(content)
        channels[default_category].extend(extracted_channels)
            
    except Exception as e:
        logger.error(f"处理 {url} 时发生异常：{str(e)}", exc_info=True)

    return channels

def merge_channels(target: OrderedDict, source: OrderedDict):
    """合并两个频道字典（优化：URL去重）"""
    url_set = set()
    for _, ch_list in target.values():
        url_set.update([url for _, url in ch_list])
    
    for category, channel_list in source.items():
        if category not in target:
            target[category] = []
        
        for name, url in channel_list:
            if url not in url_set:
                target[category].append((name, url))
                url_set.add(url)

def match_channels(template_channels: OrderedDict, all_channels: OrderedDict) -> OrderedDict:
    """匹配模板中的频道与抓取到的频道（重大优化：提升匹配率）"""
    matched_channels = OrderedDict()
    unmatched_channels = []
    
    # 构建多维度映射
    name_to_urls = {}
    all_online_names = set()
    all_clean_names = set()
    
    for _, channel_list in all_channels.items():
        for name, url in channel_list:
            if name:
                clean_name = clean_channel_name(name)
                all_online_names.add(name)
                all_clean_names.add(clean_name)
                # 原始名和清洗名都能映射到URL
                name_to_urls.setdefault(name, []).append(url)
                name_to_urls.setdefault(clean_name, []).append(url)
    
    all_online_names_list = list(all_online_names)
    all_clean_names_list = list(all_clean_names)
    
    # 遍历模板进行匹配
    for category, template_names in template_channels.items():
        matched_channels[category] = OrderedDict()
        for channel_name in template_names:
            # 多轮匹配策略
            clean_template_name = clean_channel_name(channel_name)
            matched_name = None
            
            # 1. 精确匹配原始名
            if channel_name in all_online_names:
                matched_name = channel_name
            # 2. 精确匹配清洗名
            elif clean_template_name in all_clean_names:
                matched_name = clean_template_name
            # 3. 模糊匹配原始名
            else:
                matched_name = find_similar_name(channel_name, all_online_names_list)
            # 4. 模糊匹配清洗名
            if not matched_name:
                matched_name = find_similar_name(clean_template_name, all_clean_names_list)
            
            if matched_name and matched_name in name_to_urls:
                matched_channels[category][channel_name] = name_to_urls[matched_name]
                logger.debug(f"匹配成功：{channel_name} → {restore_raw_name(matched_name)}")
            else:
                unmatched_channels.append(channel_name)
                logger.warning(f"未匹配到频道：{channel_name}")
    
    # 输出匹配统计
    total_template = sum(len(v) for v in template_channels.values())
    matched_count = total_template - len(unmatched_channels)
    logger.info(f"\n频道匹配统计：")
    logger.info(f"  - 模板总频道数：{total_template}")
    logger.info(f"  - 匹配成功数：{matched_count} ({matched_count/total_template*100:.1f}%)")
    logger.info(f"  - 未匹配数：{len(unmatched_channels)}")
    
    if len(unmatched_channels) > 0 and len(unmatched_channels) <= 20:
        logger.info(f"  - 未匹配频道：{', '.join(unmatched_channels)}")
    
    return matched_channels

def filter_source_urls(template_file: str) -> Tuple[OrderedDict, OrderedDict]:
    """过滤源URL（优化：更详细的统计）"""
    template_channels = parse_template(template_file)
    if not template_channels:
        logger.error("模板解析为空，终止流程")
        return OrderedDict(), OrderedDict()
    
    source_urls = getattr(config, 'source_urls', CONFIG_DEFAULTS["SOURCE_URLS"])
    if not source_urls:
        logger.error("未配置source_urls，终止流程")
        return OrderedDict(), template_channels
    
    all_channels = OrderedDict()
    failed_urls = []
    total_extracted = 0
    
    for url in source_urls:
        logger.info(f"\n开始抓取源：{url}")
        fetched_channels = fetch_channels(url)
        fetched_count = len(fetched_channels.get("默认分类", []))
        
        if fetched_count == 0:
            failed_urls.append(url)
            logger.warning(f"源 {url} 未抓取到任何频道")
            continue
        
        merge_channels(all_channels, fetched_channels)
        total_extracted += fetched_count
        logger.info(f"源 {url} 抓取完成，新增频道数：{fetched_count}")
    
    # 输出抓取统计
    total_channels = sum(len(ch_list) for _, ch_list in all_channels.items())
    logger.info(f"\n抓取统计：")
    logger.info(f"  - 总源数：{len(source_urls)}")
    logger.info(f"  - 失败源数：{len(failed_urls)}")
    logger.info(f"  - 原始提取频道数：{total_extracted}")
    logger.info(f"  - 去重后频道总数：{total_channels}")
    
    if failed_urls:
        logger.info(f"  - 失败的源：{', '.join(failed_urls)}")
    
    # 匹配频道
    matched_channels = match_channels(template_channels, all_channels)
    
    return matched_channels, template_channels

# ===================== 文件生成（优化） =====================
def write_to_files(f_m3u, f_txt, category, channel_name, index, url, ip_version, latency):
    """写入M3U和TXT文件（优化：编码容错）"""
    if not url:
        return
    
    try:
        meta = channel_meta_cache.get(url)
        logo_url = meta.tvg_logo if (meta and meta.tvg_logo) else get_channel_logo_url(channel_name)
        tvg_id = meta.tvg_id if (meta and meta.tvg_id) else str(index)
        tvg_name = meta.tvg_name if (meta and meta.tvg_name) else channel_name
        group_title = meta.group_title if (meta and meta.group_title) else category
        
        # 写入M3U（确保UTF-8编码）
        f_m3u.write(
            f"#EXTINF:-1 tvg-id=\"{tvg_id}\" tvg-name=\"{tvg_name}\" "
            f"tvg-logo=\"{logo_url}\" group-title=\"{group_title}\",{channel_name}\n"
        )
        f_m3u.write(url + "\n")
        # 写入TXT
        f_txt.write(f"{channel_name},{url}\n")
    except Exception as e:
        logger.warning(f"写入文件失败（频道：{channel_name}）：{str(e)[:50]}")

def updateChannelUrlsM3U(channels, template_channels, latency_results: Dict[str, SpeedTestResult]):
    """更新频道URL到M3U和TXT文件中（优化：文件写入性能）"""
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
        # 优化：使用大缓冲区写入
        with open(ipv4_m3u_path, "w", encoding="utf-8", buffering=1024*1024) as f_m3u_ipv4, \
             open(ipv4_txt_path, "w", encoding="utf-8", buffering=1024*1024) as f_txt_ipv4, \
             open(ipv6_m3u_path, "w", encoding="utf-8", buffering=1024*1024) as f_m3u_ipv6, \
             open(ipv6_txt_path, "w", encoding="utf-8", buffering=1024*1024) as f_txt_ipv6:

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
            ipv4_written = 0
            ipv6_written = 0
            
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
                        ipv4_written += 1
                    
                    # 写入IPv6 URL
                    total_ipv6 = len(ipv6_urls)
                    for idx, url in enumerate(ipv6_urls, start=1):
                        latency = latency_results[url].latency
                        new_url = add_url_suffix(url, idx, total_ipv6, "IPV6", latency)
                        write_to_files(f_m3u_ipv6, f_txt_ipv6, category, channel_name, idx, new_url, "IPV6", latency)
                        ipv6_written += 1

            # 生成测速报告
            generate_speed_report(latency_results, latency_threshold)
            
            logger.info(f"\n文件生成完成：")
            logger.info(f"  - IPv4 M3U: {ipv4_m3u_path} (写入{ipv4_written}个URL)")
            logger.info(f"  - IPv4 TXT: {ipv4_txt_path}")
            logger.info(f"  - IPv6 M3U: {ipv6_m3u_path} (写入{ipv6_written}个URL)")
            logger.info(f"  - IPv6 TXT: {ipv6_txt_path}")
            logger.info(f"  - 延迟阈值：{latency_threshold}ms")
            
    except Exception as e:
        logger.error(f"生成文件失败：{str(e)}", exc_info=True)

def generate_speed_report(latency_results: Dict[str, SpeedTestResult], latency_threshold: float):
    """生成测速报告（优化：更详细的统计）"""
    report_path = OUTPUT_FOLDER / "speed_test_report.txt"
    
    total_urls = len(latency_results)
    success_urls = [r for r in latency_results.values() if r.success]
    valid_urls = [r for r in success_urls if r.latency and r.latency <= latency_threshold]
    ipv4_urls = [r for r in valid_urls if not is_ipv6(r.url)]
    ipv6_urls = [r for r in valid_urls if is_ipv6(r.url)]
    
    valid_urls.sort(key=lambda x: x.latency)
    
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("IPTV直播源测速报告\n")
            f.write("="*80 + "\n")
            f.write(f"测试时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"延迟阈值：{latency_threshold}ms | 并发数：{getattr(config, 'CONCURRENT_LIMIT', 20)}\n")
            f.write(f"总测试URL数：{total_urls}\n")
            success_rate = f"{len(success_urls)/total_urls*100:.1f}%" if total_urls > 0 else "0.0%"
            f.write(f"测试成功数：{len(success_urls)} ({success_rate})\n")
            valid_rate = f"{len(valid_urls)/len(success_urls)*100:.1f}%" if len(success_urls) > 0 else "0.0%"
            f.write(f"有效URL数（延迟<{latency_threshold}ms）：{len(valid_urls)} ({valid_rate})\n")
            f.write(f"  - IPv4有效URL：{len(ipv4_urls)}\n")
            f.write(f"  - IPv6有效URL：{len(ipv6_urls)}\n")
            
            if valid_urls:
                avg_latency = sum(r.latency for r in valid_urls) / len(valid_urls)
                min_latency = min(r.latency for r in valid_urls)
                max_latency = max(r.latency for r in valid_urls)
                f.write(f"有效URL延迟统计：平均{avg_latency:.2f}ms | 最小{min_latency:.2f}ms | 最大{max_latency:.2f}ms\n")
            
            f.write("="*80 + "\n\n")
            
            if valid_urls:
                f.write("【有效URL列表（按延迟升序）】\n")
                f.write(f"{'排名':<4} {'延迟(ms)':<10} {'分辨率':<10} {'IP版本':<8} {'URL'}\n")
                f.write("-"*80 + "\n")
                for idx, result in enumerate(valid_urls, 1):
                    ip_version = "IPv6" if is_ipv6(result.url) else "IPv4"
                    f.write(f"{idx:<4} {result.latency:<10.2f} {result.resolution:<10} {ip_version:<8} {result.url[:100]}\n")
            else:
                f.write("【有效URL列表（按延迟升序）】\n")
                f.write("无有效URL\n")
            
            failed_urls = [r for r in latency_results.values() if not r.success]
            if failed_urls:
                f.write("\n【失败URL列表】\n")
                f.write(f"{'排名':<4} {'失败原因':<15} {'URL'}\n")
                f.write("-"*80 + "\n")
                for idx, result in enumerate(failed_urls[:50], 1):  # 限制输出数量
                    f.write(f"{idx:<4} {result.error:<15} {result.url[:100]}\n")
                if len(failed_urls) > 50:
                    f.write(f"... 共{len(failed_urls)}个失败URL，仅显示前50个\n")
            else:
                f.write("\n【失败URL列表】\n")
                f.write("无失败URL\n")
        
        logger.info(f"  - 测速报告：{report_path}")
    except Exception as e:
        logger.error(f"生成测速报告失败：{str(e)}", exc_info=True)

# ===================== 主程序（优化：全局异常捕获） =====================
async def main():
    """主函数（优化：性能统计+全局异常处理）"""
    start_total = time.time()
    try:
        # 清空缓存
        global channel_meta_cache, raw_name_mapping
        channel_meta_cache = {}
        raw_name_mapping = {}
        
        # 配置加载
        template_file = getattr(config, 'TEMPLATE_FILE', CONFIG_DEFAULTS["TEMPLATE_FILE"])
        latency_threshold = getattr(config, 'LATENCY_THRESHOLD', CONFIG_DEFAULTS["LATENCY_THRESHOLD"])
        logger.info("===== 开始处理直播源 =====")
        logger.info(f"配置信息：延迟阈值{latency_threshold}ms | 匹配阈值{getattr(config, 'MATCH_CUTOFF', 0.4)}")
        
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
        logger.info("\n===== 3. 生成最终文件 =====")
        updateChannelUrlsM3U(channels, template_channels, latency_results)
        
        # 总耗时统计
        total_elapsed = time.time() - start_total
        logger.info(f"\n===== 所有流程执行完成 | 总耗时：{total_elapsed:.1f}s =====")
    
    except Exception as e:
        logger.critical(f"程序执行异常：{str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    # 兼容Windows异步事件循环
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 运行主程序
    asyncio.run(main())
