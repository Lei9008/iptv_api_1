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
from typing import List, Dict, Optional, Tuple, Any
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

# ===================== 数据结构 =====================
@dataclass
class SpeedTestResult:
    """测速结果数据类"""
    url: str
    latency: Optional[float] = None  # 延迟（毫秒）
    resolution: Optional[str] = None  # 分辨率
    success: bool = False  # 是否成功
    error: Optional[str] = None  # 错误信息

@dataclass
class ChannelInfo:
    """频道信息数据类（存储M3U标准字段）"""
    name: str  # 频道名称（优先tvg-name，其次自定义名称）
    url: str  # 播放地址
    group_title: str = "默认分类"  # 分类（group-title）
    tvg_name: str = ""  # TVG名称
    tvg_logo: str = ""  # TVG Logo地址
    tvg_id: str = ""  # TVG ID
    other_attrs: Dict[str, str] = None  # 其他属性

    def __post_init__(self):
        if self.other_attrs is None:
            self.other_attrs = {}

# ===================== 初始化配置 =====================
# 确保 output 文件夹存在
OUTPUT_FOLDER = Path("output")
OUTPUT_FOLDER.mkdir(exist_ok=True)

# 初始化 logo 目录
LOGO_DIRS = [Path("./pic/logos"), Path("./pic/logo")]
for dir_path in LOGO_DIRS:
    dir_path.mkdir(parents=True, exist_ok=True)

# 从config.py读取GitHub Logo配置
GITHUB_LOGO_BASE_URL = getattr(config, 'GITHUB_LOGO_BASE_URL', 
                              "https://raw.githubusercontent.com/fanmingming/live/main/tv")
BACKUP_LOGO_BASE_URL = getattr(config, 'BACKUP_LOGO_BASE_URL',
                              "https://ghproxy.com/https://raw.githubusercontent.com/fanmingming/live/main/tv")
GITHUB_LOGO_API_URLS = getattr(config, 'GITHUB_LOGO_API_URLS', [
    "https://api.github.com/repos/fanmingming/live/contents/main/tv",
    "https://ghproxy.com/https://api.github.com/repos/fanmingming/live/contents/main/tv"
])

# 测速配置（集中管理默认值）
CONFIG_DEFAULTS = {
    "LATENCY_THRESHOLD": 500,
    "CONCURRENT_LIMIT": 20,
    "TIMEOUT": 15,  # 增加超时时间
    "RETRY_TIMES": 3,  # 增加重试次数
    "IP_VERSION_PRIORITY": "ipv4",
    "URL_BLACKLIST": [],
    "TEMPLATE_FILE": "demo.txt",
    "EPG_URLS": [],
    "ANNOUNCEMENTS": [],
    "SOURCE_URLS": []
}

# GitHub 镜像域名列表
GITHUB_MIRRORS = [
    "raw.githubusercontent.com",
    "raw.kkgithub.com",
    "raw.githubusercontents.com",
    "raw.fgit.cf",
    "raw.fgithub.de"
]

# 代理前缀列表（扩充更多可用代理）
PROXY_PREFIXES = [
    "https://ghproxy.com/",
    "https://mirror.ghproxy.com/",
    "https://gh.api.99988866.xyz/",
    "https://mirror.ghproxy.net/",
    "https://github.moeyy.xyz/"
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

def convert_github_url(raw_url: str) -> str:
    """
    自动转换GitHub URL格式：
    - blob/main → raw.githubusercontent.com
    - github.com → raw.githubusercontent.com
    示例：
    https://github.com/xxx/blob/main/file.txt → https://raw.githubusercontent.com/xxx/main/file.txt
    """
    if not raw_url or "github.com" not in raw_url:
        return raw_url
    
    # 解析URL
    parsed = urlparse(raw_url)
    path_parts = parsed.path.split('/')
    
    # 移除blob或tree部分
    if 'blob' in path_parts:
        path_parts.remove('blob')
    elif 'tree' in path_parts:
        path_parts.remove('tree')
    
    # 重构路径
    new_path = '/'.join(path_parts)
    
    # 替换域名并重构URL
    new_parsed = parsed._replace(
        netloc='raw.githubusercontent.com',
        path=new_path
    )
    
    converted_url = urlunparse(new_parsed)
    logger.debug(f"转换GitHub URL: {raw_url} → {converted_url}")
    return converted_url

def parse_m3u_attributes(line: str) -> Dict[str, str]:
    """解析M3U属性行（#EXTINF:...）中的键值对"""
    attrs = {}
    
    # 提取逗号前的属性部分
    attr_part = line.split(',')[0] if ',' in line else line
    # 移除EXTINF前缀
    attr_part = attr_part.replace('#EXTINF:', '').strip()
    
    # 提取数字（时长）后的部分
    attr_part = re.sub(r'^-?\d+\s*', '', attr_part)
    
    # 正则匹配带引号的属性（key="value"）
    quoted_pattern = r'(\w+)="([^"]*)"'
    quoted_matches = re.findall(quoted_pattern, attr_part)
    for key, value in quoted_matches:
        attrs[key.lower()] = value.strip()
    
    # 正则匹配不带引号的属性（key=value）
    unquoted_pattern = r'(\w+)=([^\s"]+)'
    unquoted_matches = re.findall(unquoted_pattern, attr_part)
    for key, value in unquoted_matches:
        if key.lower() not in attrs:  # 不覆盖带引号的属性
            attrs[key.lower()] = value.strip()
    
    # 提取频道名（逗号后部分）
    if ',' in line:
        channel_name = line.split(',', 1)[1].strip()
        attrs['_channel_name'] = channel_name
    
    return attrs

def extract_channels_from_content(content: str) -> List[ChannelInfo]:
    """从直播源内容中提取频道信息，优先解析M3U标准字段"""
    channels = []
    # 去重集合（URL+名称）
    seen_pairs = set()
    
    lines = content.splitlines()
    current_attrs = {}
    
    # 逐行解析M3U格式
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        
        # 1. 匹配M3U属性行（优先解析）
        if line.startswith('#EXTINF:'):
            current_attrs = parse_m3u_attributes(line)
            continue
        
        # 2. 匹配播放地址行（紧跟在EXTINF行后）
        if line.startswith(('http://', 'https://', 'rtmp://', 'rtsp://')) and current_attrs:
            url = line.strip()
            
            # 提取关键属性
            tvg_name = current_attrs.get('tvg-name', '')
            group_title = current_attrs.get('group-title', current_attrs.get('group', '默认分类'))
            tvg_logo = current_attrs.get('tvg-logo', '')
            tvg_id = current_attrs.get('tvg-id', '')
            channel_name = current_attrs.get('_channel_name', tvg_name or '未知频道')
            
            # 清洗频道名
            cleaned_name = clean_channel_name(channel_name)
            if not cleaned_name:
                cleaned_name = clean_channel_name(tvg_name) or '未知频道'
            
            # 去重检查
            pair_key = (cleaned_name, url)
            if pair_key in seen_pairs:
                current_attrs = {}
                continue
            seen_pairs.add(pair_key)
            
            # 创建频道信息对象
            channel_info = ChannelInfo(
                name=cleaned_name,
                url=url,
                group_title=group_title,
                tvg_name=tvg_name,
                tvg_logo=tvg_logo,
                tvg_id=tvg_id,
                other_attrs={k: v for k, v in current_attrs.items() if k not in ['tvg-name', 'group-title', 'tvg-logo', 'tvg-id', '_channel_name']}
            )
            channels.append(channel_info)
            
            # 重置当前属性
            current_attrs = {}
            continue
        
        # 3. 兼容旧格式（频道名,URL）
        if ',' in line and not line.startswith('#'):
            parts = line.split(',', 1)
            if len(parts) == 2 and parts[1].strip().startswith(('http://', 'https://')):
                name_part = parts[0].strip()
                url_part = parts[1].strip()
                
                cleaned_name = clean_channel_name(name_part) or '未知频道'
                pair_key = (cleaned_name, url_part)
                
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                
                # 创建兼容模式的频道信息
                channel_info = ChannelInfo(
                    name=cleaned_name,
                    url=url_part,
                    group_title="默认分类"
                )
                channels.append(channel_info)
                continue
        
        # 4. 单独的URL（无属性）
        if line.startswith(('http://', 'https://')) and not current_attrs:
            url = line.strip()
            # 从URL提取简易名称
            url_parts = url.split('/')
            name_from_url = '未知频道'
            for part in url_parts:
                if part and not part.startswith(('http', 'www', 'live', 'stream')) and len(part) > 2:
                    name_from_url = clean_channel_name(part)
                    break
            
            pair_key = (name_from_url, url)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            
            channel_info = ChannelInfo(
                name=name_from_url,
                url=url,
                group_title="默认分类"
            )
            channels.append(channel_info)
    
    logger.info(f"从内容中提取到 {len(channels)} 个有效频道（优先解析M3U标准字段）")
    return channels

def sort_and_filter_urls(
    channel_infos: List[ChannelInfo], 
    written_urls: set, 
    latency_results: Dict[str, SpeedTestResult], 
    latency_threshold: float
) -> List[ChannelInfo]:
    """排序和过滤频道信息（基于ChannelInfo对象）"""
    if not channel_infos:
        return []
    
    filtered_channels = []
    url_blacklist = getattr(config, 'url_blacklist', [])
    
    for channel in channel_infos:
        url = channel.url.strip()
        if not url or url in written_urls:
            continue
        
        # 黑名单过滤
        if any(blacklist in url for blacklist in url_blacklist):
            continue
        
        # 延迟过滤
        result = latency_results.get(url)
        if not result or not result.success or result.latency is None or result.latency > latency_threshold:
            continue
        
        filtered_channels.append(channel)
    
    # 按IP版本优先级排序
    ip_priority = getattr(config, 'ip_version_priority', CONFIG_DEFAULTS["IP_VERSION_PRIORITY"])
    if ip_priority == "ipv6":
        filtered_channels.sort(key=lambda c: is_ipv6(c.url), reverse=True)
    else:
        filtered_channels.sort(key=lambda c: is_ipv6(c.url))
    
    # 按延迟升序排序
    filtered_channels.sort(key=lambda c: latency_results[c.url].latency if latency_results.get(c.url) else float('inf'))
    
    # 更新已写入URL集合
    written_urls.update([c.url for c in filtered_channels])
    
    return filtered_channels

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
    """获取GitHub仓库中的logo文件列表"""
    headers = {"User-Agent": "Mozilla/5.0"}
    logo_files = []
    
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
    """检测logo文件，生成动态logo_url"""
    clean_logo_name = clean_channel_name(channel_name)
    logo_filename = f"{clean_logo_name}.png"
    
    # 检测本地logo
    for logo_dir in LOGO_DIRS:
        local_logo_path = logo_dir / logo_filename
        if local_logo_path.exists():
            return local_logo_path.as_posix()
    
    # 获取有效的logo URL
    def get_valid_logo_url(filename):
        base_urls = [GITHUB_LOGO_BASE_URL, BACKUP_LOGO_BASE_URL]
        
        for base_url in base_urls:
            for mirror in GITHUB_MIRRORS:
                if "raw.githubusercontent.com" in base_url:
                    test_url = base_url.replace("raw.githubusercontent.com", mirror) + f"/{filename}"
                else:
                    test_url = base_url + f"/{filename}"
                
                try:
                    response = requests.head(test_url, timeout=3, allow_redirects=True)
                    if response.status_code == 200:
                        return test_url
                except:
                    continue
        
        return f"{BACKUP_LOGO_BASE_URL}/{filename}"
    
    github_logo_files = get_github_logo_list()
    
    if logo_filename in github_logo_files:
        return get_valid_logo_url(logo_filename)
    
    # 模糊匹配
    candidate_names = [
        logo_filename,
        logo_filename.replace("+", "PLUS"),
        logo_filename.upper(),
        logo_filename.lower()
    ]
    for candidate in candidate_names:
        if candidate in github_logo_files:
            return get_valid_logo_url(candidate)
    
    similar_logo = find_similar_name(clean_logo_name, [f.replace(".png", "") for f in github_logo_files], cutoff=0.7)
    if similar_logo:
        return get_valid_logo_url(f"{similar_logo}.png")
    
    return ""

# ===================== 链接修复和重试函数 =====================
def replace_github_domain(url: str) -> List[str]:
    """替换GitHub域名，生成多个可访问的镜像链接"""
    if not url:
        return [url]
    
    # 先转换GitHub URL格式
    url = convert_github_url(url)
    
    candidate_urls = [url]
    
    # 替换不同的GitHub镜像域名
    for mirror in GITHUB_MIRRORS:
        for original in GITHUB_MIRRORS:
            if original in url:
                new_url = url.replace(original, mirror)
                if new_url not in candidate_urls:
                    candidate_urls.append(new_url)
    
    # 添加代理前缀（优先使用不同的代理）
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
    增强版：带重试和镜像替换的URL抓取函数
    - 自动转换GitHub URL格式
    - 增加超时时间
    - 更多重试策略
    """
    # 自定义请求头（模拟浏览器）
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    # 生成候选URL列表（包含格式转换和镜像）
    candidate_urls = replace_github_domain(url)
    
    # 增加重试间隔
    retry_delays = [1, 2, 3]  # 重试间隔（秒）
    
    for idx, candidate in enumerate(candidate_urls):
        try:
            logger.debug(f"尝试抓取 [{idx+1}/{len(candidate_urls)}]: {candidate}")
            
            # 创建会话，启用重试和超时
            session = requests.Session()
            session.mount('https://', requests.adapters.HTTPAdapter(
                max_retries=requests.packages.urllib3.util.retry.Retry(
                    total=3,
                    backoff_factor=0.5,
                    status_forcelist=[429, 500, 502, 503, 504]
                )
            ))
            
            response = session.get(
                candidate,
                headers=headers,
                timeout=timeout,
                verify=False,  # 忽略SSL证书错误
                allow_redirects=True,
                stream=True  # 流式读取，避免大文件占用内存
            )
            
            # 检查状态码
            response.raise_for_status()
            
            # 处理编码
            if response.encoding is None:
                response.encoding = 'utf-8'
            
            # 读取内容（处理gzip压缩）
            content = response.content.decode(response.encoding, errors='ignore')
            
            logger.info(f"成功抓取：{candidate} (大小：{len(content)}字节)")
            return content
            
        except requests.exceptions.Timeout:
            logger.warning(f"抓取超时 [{idx+1}/{len(candidate_urls)}]: {candidate}")
        except requests.exceptions.ConnectionError:
            logger.warning(f"连接失败 [{idx+1}/{len(candidate_urls)}]: {candidate}")
        except requests.exceptions.HTTPError as e:
            logger.warning(f"HTTP错误 [{idx+1}/{len(candidate_urls)}]: {candidate} | 状态码：{e.response.status_code}")
        except Exception as e:
            logger.warning(f"抓取失败 [{idx+1}/{len(candidate_urls)}]: {candidate} | 原因：{str(e)[:50]}")
        
        # 重试间隔
        if idx < len(candidate_urls) - 1 and idx < len(retry_delays):
            time.sleep(retry_delays[idx])
    
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

def fetch_channels(url: str) -> Dict[str, List[ChannelInfo]]:
    """抓取频道并按group-title分类"""
    # 按分类存储频道
    categorized_channels = OrderedDict()
    categorized_channels["默认分类"] = []
    
    try:
        content = fetch_url_with_retry(url)
        if content is None:
            return categorized_channels
        
        # 提取带完整元数据的频道列表
        channel_list = extract_channels_from_content(content)
        
        # 按group-title分类
        for channel in channel_list:
            group = channel.group_title or "默认分类"
            if group not in categorized_channels:
                categorized_channels[group] = []
            categorized_channels[group].append(channel)
            
    except Exception as e:
        logger.error(f"处理 {url} 时发生异常：{str(e)}", exc_info=True)

    return categorized_channels

def merge_channels(target: Dict[str, List[ChannelInfo]], source: Dict[str, List[ChannelInfo]]):
    """合并分类的频道信息（去重）"""
    # 先收集所有已存在的URL用于去重
    existing_urls = set()
    for group in target:
        for channel in target[group]:
            existing_urls.add(channel.url)
    
    for group, channels in source.items():
        if group not in target:
            target[group] = []
        
        for channel in channels:
            if channel.url not in existing_urls:
                target[group].append(channel)
                existing_urls.add(channel.url)

def match_channels(template_channels: OrderedDict, all_channels: Dict[str, List[ChannelInfo]]) -> Dict[str, Dict[str, List[ChannelInfo]]]:
    """匹配模板频道与抓取的频道（基于完整元数据）"""
    matched_channels = OrderedDict()
    
    # 构建所有频道名到频道信息的映射
    name_to_channels = {}
    all_channel_names = set()
    
    for group, channels in all_channels.items():
        for channel in channels:
            channel_name = channel.name
            all_channel_names.add(channel_name)
            if channel_name not in name_to_channels:
                name_to_channels[channel_name] = []
            name_to_channels[channel_name].append(channel)
    
    all_channel_names_list = list(all_channel_names)
    
    # 遍历模板进行匹配
    for template_group, template_names in template_channels.items():
        matched_channels[template_group] = OrderedDict()
        
        for template_name in template_names:
            cleaned_template_name = clean_channel_name(template_name)
            # 优先精确匹配，再模糊匹配
            if cleaned_template_name in name_to_channels:
                matched_channels[template_group][template_name] = name_to_channels[cleaned_template_name]
                logger.debug(f"精确匹配成功：{template_name} → {cleaned_template_name}")
            else:
                similar_name = find_similar_name(cleaned_template_name, all_channel_names_list)
                if similar_name:
                    matched_channels[template_group][template_name] = name_to_channels.get(similar_name, [])
                    logger.debug(f"模糊匹配成功：{template_name} → {similar_name}")
                else:
                    matched_channels[template_group][template_name] = []
                    logger.warning(f"未匹配到频道：{template_name}")
    
    return matched_channels

def filter_source_urls(template_file: str) -> Tuple[Dict[str, Dict[str, List[ChannelInfo]]], OrderedDict]:
    """过滤源URL，返回分类的匹配结果"""
    # 解析模板
    template_channels = parse_template(template_file)
    if not template_channels:
        logger.error("模板解析为空，终止流程")
        return {}, OrderedDict()
    
    # 获取源URL配置
    source_urls = getattr(config, 'source_urls', CONFIG_DEFAULTS["SOURCE_URLS"])
    if not source_urls:
        logger.error("未配置source_urls，终止流程")
        return {}, template_channels
    
    # 抓取并合并所有源
    all_channels = OrderedDict()
    all_channels["默认分类"] = []
    failed_urls = []
    success_urls = []
    
    for url in source_urls:
        logger.info(f"\n开始抓取源：{url}")
        fetched_channels = fetch_channels(url)
        
        # 检查是否抓取到有效频道
        total_fetched = sum(len(channels) for channels in fetched_channels.values())
        if total_fetched == 0:
            failed_urls.append(url)
            logger.warning(f"源 {url} 未抓取到任何频道")
            continue
        
        # 合并分类的频道
        merge_channels(all_channels, fetched_channels)
        success_urls.append(url)
        logger.info(f"源 {url} 抓取完成，新增频道数：{total_fetched}（按{len(fetched_channels)}个分类组织）")
    
    # 输出抓取统计
    total_channels = sum(len(channels) for channels in all_channels.values())
    logger.info(f"\n抓取统计：")
    logger.info(f"  - 总源数：{len(source_urls)}")
    logger.info(f"  - 成功源数：{len(success_urls)}")
    logger.info(f"  - 失败源数：{len(failed_urls)}")
    logger.info(f"  - 成功抓取频道总数：{total_channels}")
    logger.info(f"  - 频道分类数：{len(all_channels)}")
    
    if success_urls:
        logger.info(f"  - 成功的源：{', '.join(success_urls[:3])}{'...' if len(success_urls)>3 else ''}")
    if failed_urls:
        logger.info(f"  - 失败的源：{', '.join(failed_urls[:3])}{'...' if len(failed_urls)>3 else ''}")
    
    # 匹配频道
    matched_channels = match_channels(template_channels, all_channels)
    
    return matched_channels, template_channels

# ===================== 文件生成 =====================
def write_to_files(f_m3u, f_txt, category, channel_info: ChannelInfo, index: int, ip_version: str, latency: float):
    """写入带完整元数据的频道信息"""
    if not channel_info.url:
        return
    
    # 优先使用频道自带的tvg-logo，否则自动匹配
    logo_url = channel_info.tvg_logo or get_channel_logo_url(channel_info.name)
    
    # 构建M3U属性行
    extinf_parts = [f"#EXTINF:-1"]
    if channel_info.tvg_name:
        extinf_parts.append(f'tvg-name="{channel_info.tvg_name}"')
    if logo_url:
        extinf_parts.append(f'tvg-logo="{logo_url}"')
    if channel_info.tvg_id:
        extinf_parts.append(f'tvg-id="{channel_info.tvg_id}"')
    if category:
        extinf_parts.append(f'group-title="{category}"')
    
    # 添加频道名
    extinf_line = ' '.join(extinf_parts) + f',{channel_info.name}'
    
    # 生成带后缀的URL
    url_with_suffix = add_url_suffix(channel_info.url, index, 1, ip_version, latency)
    
    # 写入M3U
    f_m3u.write(f"{extinf_line}\n")
    f_m3u.write(f"{url_with_suffix}\n")
    
    # 写入TXT（分类,频道名,URL）
    f_txt.write(f"{category},{channel_info.name},{url_with_suffix}\n")

def updateChannelUrlsM3U(matched_channels: Dict[str, Dict[str, List[ChannelInfo]]], 
                         template_channels: OrderedDict, 
                         latency_results: Dict[str, SpeedTestResult]):
    """生成带完整M3U元数据的文件"""
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

            # 写入M3U头部（包含EPG信息）
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
                
                f_txt_ipv4.write(f"{channel_name},#genre#,\n")
                f_txt_ipv6.write(f"{channel_name},#genre#,\n")
                
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
                                # 构建公告频道的EXTINF行
                                extinf = f"#EXTINF:-1 tvg-name=\"{entry_name}\" tvg-logo=\"{entry_logo}\" group-title=\"{channel_name}\",{entry_name}({entry_result.latency:.0f}ms)"
                                f_m3u_ipv6.write(f"{extinf}\n{entry_url}\n")
                                f_txt_ipv6.write(f"{channel_name},{entry_name},{entry_url}\n")
                                announcement_id += 1
                        else:
                            if entry_url not in written_urls_ipv4:
                                written_urls_ipv4.add(entry_url)
                                extinf = f"#EXTINF:-1 tvg-name=\"{entry_name}\" tvg-logo=\"{entry_logo}\" group-title=\"{channel_name}\",{entry_name}({entry_result.latency:.0f}ms)"
                                f_m3u_ipv4.write(f"{extinf}\n{entry_url}\n")
                                f_txt_ipv4.write(f"{channel_name},{entry_name},{entry_url}\n")
                                announcement_id += 1

            # 写入模板频道（按分类组织）
            for template_group, channel_map in matched_channels.items():
                if not template_group:
                    continue
                
                # 写入分类标记
                f_txt_ipv4.write(f"{template_group},#genre#,\n")
                f_txt_ipv6.write(f"{template_group},#genre#,\n")
                
                for channel_name, channel_infos in channel_map.items():
                    if not channel_infos:
                        continue
                    
                    # 分离IPv4/IPv6频道
                    ipv4_channels = sort_and_filter_urls(
                        [c for c in channel_infos if not is_ipv6(c.url)],
                        written_urls_ipv4,
                        latency_results,
                        latency_threshold
                    )
                    ipv6_channels = sort_and_filter_urls(
                        [c for c in channel_infos if is_ipv6(c.url)],
                        written_urls_ipv6,
                        latency_results,
                        latency_threshold
                    )
                    
                    # 写入IPv4频道
                    for idx, channel in enumerate(ipv4_channels, start=1):
                        latency = latency_results[channel.url].latency
                        write_to_files(f_m3u_ipv4, f_txt_ipv4, template_group, channel, idx, "IPV4", latency)
                    
                    # 写入IPv6频道
                    for idx, channel in enumerate(ipv6_channels, start=1):
                        latency = latency_results[channel.url].latency
                        write_to_files(f_m3u_ipv6, f_txt_ipv6, template_group, channel, idx, "IPV6", latency)

        # 生成测速报告
        generate_speed_report(latency_results, latency_threshold)
        
        logger.info(f"\n文件生成完成：")
        logger.info(f"  - IPv4 M3U: {ipv4_m3u_path}（包含完整M3U元数据）")
        logger.info(f"  - IPv4 TXT: {ipv4_txt_path}（分类,频道名,URL格式）")
        logger.info(f"  - IPv6 M3U: {ipv6_m3u_path}（包含完整M3U元数据）")
        logger.info(f"  - IPv6 TXT: {ipv6_txt_path}（分类,频道名,URL格式）")
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
        logger.info("===== 开始处理直播源（优化M3U元数据解析+增强抓取） =====")
        logger.info(f"延迟阈值设置：{latency_threshold}ms")
        
        # 预加载GitHub logo列表
        get_github_logo_list()
        
        # 抓取并匹配频道（带完整元数据）
        logger.info("\n===== 1. 抓取并提取直播源频道（优先解析M3U字段） =====")
        matched_channels, template_channels = filter_source_urls(template_file)
        if not matched_channels:
            logger.error("无匹配的频道数据，终止流程")
            return
        
        # 收集所有需要测速的URL
        all_urls = set()
        for group in matched_channels.values():
            for channel_infos in group.values():
                for channel in channel_infos:
                    all_urls.add(channel.url)
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
        
        # 生成最终文件（带完整M3U元数据）
        logger.info("\n===== 3. 生成最终文件（包含group-title/tvg-name等元数据） =====")
        updateChannelUrlsM3U(matched_channels, template_channels, latency_results)
        
        logger.info("\n===== 所有流程执行完成 =====")
    
    except Exception as e:
        logger.critical(f"程序执行异常：{str(e)}", exc_info=True)

if __name__ == "__main__":
    # 禁用requests警告
    requests.packages.urllib3.disable_warnings()
    
    # 兼容Windows异步事件循环
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 运行主程序
    asyncio.run(main())
