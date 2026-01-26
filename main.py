import re
import sys  # 新增：导入sys模块，解决平台判断报错
import requests
import logging
import asyncio
import aiohttp
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set
from functools import lru_cache
import warnings

# 屏蔽SSL不安全请求警告
warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

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
class ChannelMeta:
    """频道元信息（完整保留原始M3U标签）"""
    url: str  # 必填：播放URL
    raw_extinf: str = ""  # 新增：完整的原始#EXTINF行
    tvg_id: Optional[str] = None  # 原始tvg-id
    tvg_name: Optional[str] = None  # 原始tvg-name
    tvg_logo: Optional[str] = None  # 原始tvg-logo
    group_title: Optional[str] = None  # 原始group-title
    channel_name: Optional[str] = None  # 原始频道名（逗号后部分）
    clean_channel_name: str = ""  # 标准化后的频道名
    source_url: str = ""  # 来源URL

# ===================== 初始化配置 =====================
# 确保 output 文件夹存在
OUTPUT_FOLDER = Path("output")
OUTPUT_FOLDER.mkdir(exist_ok=True)

# 初始化 logo 目录
LOGO_DIRS = [Path("./pic/logos"), Path("./pic/logo")]
for dir_path in LOGO_DIRS:
    dir_path.mkdir(parents=True, exist_ok=True)

# 配置默认值（核心：新增URL黑名单默认配置）
CONFIG_DEFAULTS = {
    "LATENCY_THRESHOLD": 500,
    "CONCURRENT_LIMIT": 20,
    "TIMEOUT": 10,
    "RETRY_TIMES": 2,
    "IP_VERSION_PRIORITY": "ipv4",
    "URL_BLACKLIST": [],  # URL黑名单关键词
    "TEMPLATE_FILE": "demo.txt",
    "EPG_URLS": [],
    "ANNOUNCEMENTS": [],
    "SOURCE_URLS": [],
    "MATCH_CUTOFF": 0.4,
    "PROGRESS_INTERVAL": 50
}

# 尝试导入用户配置（如果不存在则使用默认值）
try:
    import config
    # 读取配置，不存在则用默认值
    LATENCY_THRESHOLD = getattr(config, 'LATENCY_THRESHOLD', CONFIG_DEFAULTS["LATENCY_THRESHOLD"])
    CONCURRENT_LIMIT = getattr(config, 'CONCURRENT_LIMIT', CONFIG_DEFAULTS["CONCURRENT_LIMIT"])
    TIMEOUT = getattr(config, 'TIMEOUT', CONFIG_DEFAULTS["TIMEOUT"])
    RETRY_TIMES = getattr(config, 'RETRY_TIMES', CONFIG_DEFAULTS["RETRY_TIMES"])
    IP_VERSION_PRIORITY = getattr(config, 'IP_VERSION_PRIORITY', CONFIG_DEFAULTS["IP_VERSION_PRIORITY"])
    URL_BLACKLIST = getattr(config, 'URL_BLACKLIST', CONFIG_DEFAULTS["URL_BLACKLIST"])
    TEMPLATE_FILE = getattr(config, 'TEMPLATE_FILE', CONFIG_DEFAULTS["TEMPLATE_FILE"])
    EPG_URLS = getattr(config, 'EPG_URLS', CONFIG_DEFAULTS["EPG_URLS"])
    ANNOUNCEMENTS = getattr(config, 'ANNOUNCEMENTS', CONFIG_DEFAULTS["ANNOUNCEMENTS"])
    SOURCE_URLS = getattr(config, 'SOURCE_URLS', CONFIG_DEFAULTS["SOURCE_URLS"])
    MATCH_CUTOFF = getattr(config, 'MATCH_CUTOFF', CONFIG_DEFAULTS["MATCH_CUTOFF"])
    PROGRESS_INTERVAL = getattr(config, 'PROGRESS_INTERVAL', CONFIG_DEFAULTS["PROGRESS_INTERVAL"])
    
    # GitHub Logo配置
    GITHUB_LOGO_BASE_URL = getattr(config, 'GITHUB_LOGO_BASE_URL', 
                                  "https://raw.githubusercontent.com/fanmingming/live/main/tv")
    BACKUP_LOGO_BASE_URL = getattr(config, 'BACKUP_LOGO_BASE_URL',
                                  "https://ghproxy.com/https://raw.githubusercontent.com/fanmingming/live/main/tv")
    GITHUB_LOGO_API_URLS = getattr(config, 'GITHUB_LOGO_API_URLS', [
        "https://api.github.com/repos/fanmingming/live/contents/main/tv",
        "https://ghproxy.com/https://api.github.com/repos/fanmingming/live/contents/main/tv"
    ])
except ImportError:
    # 无config.py时使用默认值
    LATENCY_THRESHOLD = CONFIG_DEFAULTS["LATENCY_THRESHOLD"]
    CONCURRENT_LIMIT = CONFIG_DEFAULTS["CONCURRENT_LIMIT"]
    TIMEOUT = CONFIG_DEFAULTS["TIMEOUT"]
    RETRY_TIMES = CONFIG_DEFAULTS["RETRY_TIMES"]
    IP_VERSION_PRIORITY = CONFIG_DEFAULTS["IP_VERSION_PRIORITY"]
    URL_BLACKLIST = CONFIG_DEFAULTS["URL_BLACKLIST"]
    TEMPLATE_FILE = CONFIG_DEFAULTS["TEMPLATE_FILE"]
    EPG_URLS = CONFIG_DEFAULTS["EPG_URLS"]
    ANNOUNCEMENTS = CONFIG_DEFAULTS["ANNOUNCEMENTS"]
    SOURCE_URLS = CONFIG_DEFAULTS["SOURCE_URLS"]
    MATCH_CUTOFF = CONFIG_DEFAULTS["MATCH_CUTOFF"]
    PROGRESS_INTERVAL = CONFIG_DEFAULTS["PROGRESS_INTERVAL"]
    
    GITHUB_LOGO_BASE_URL = "https://raw.githubusercontent.com/fanmingming/live/main/tv"
    BACKUP_LOGO_BASE_URL = "https://ghproxy.com/https://raw.githubusercontent.com/fanmingming/live/main/tv"
    GITHUB_LOGO_API_URLS = [
        "https://api.github.com/repos/fanmingming/live/contents/main/tv",
        "https://ghproxy.com/https://api.github.com/repos/fanmingming/live/contents/main/tv"
    ]

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

# 日志配置
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

# 全局存储
channel_meta_cache: Dict[str, ChannelMeta] = {}  # key: url, value: ChannelMeta
raw_extinf_mapping: Dict[str, str] = {}  # url -> 完整的原始#EXTINF行
url_source_mapping: Dict[str, str] = {}  # url -> 来源URL

# ===================== 核心工具函数 =====================
def standardize_channel_name(channel_name: str) -> str:
    """智能标准化频道名"""
    if not channel_name:
        return ""
    
    name = channel_name.upper().strip()
    
    # CCTV系列标准化
    cctv_pattern = r'(CCTV)\s*\-?(\d+)(?:\+|PLUS)?'
    cctv_match = re.search(cctv_pattern, name)
    if cctv_match:
        cctv_num = cctv_match.group(2)
        if '+' in name or 'PLUS' in name:
            standardized = f"CCTV{cctv_num}+"
        else:
            standardized = f"CCTV{cctv_num}"
        return standardized
    
    # 卫视系列标准化
    satellite_patterns = [
        (r'(湖南)\s*卫视', '湖南卫视'),
        (r'(浙江)\s*卫视', '浙江卫视'),
        (r'(江苏)\s*卫视', '江苏卫视'),
        (r'(东方)\s*卫视', '东方卫视'),
        (r'(北京)\s*卫视', '北京卫视'),
    ]
    for pattern, replacement in satellite_patterns:
        if re.search(pattern, name):
            return replacement
    
    # 基础清理
    cleaned = re.sub(r'[\s\(\)（）【】\-—_]+', '', name)
    return cleaned

def clean_channel_name(channel_name: str) -> str:
    """标准化清洗频道名称"""
    if not channel_name:
        return ""
    
    standardized_name = standardize_channel_name(channel_name)
    standardized_name = re.sub(r'CCTV-?5\+', 'CCTV5+', standardized_name)
    
    # 特殊频道处理
    standardized_name = standardized_name.replace("翡翠台", "TVB翡翠台")
    standardized_name = standardized_name.replace("凤凰中文", "凤凰卫视中文台")
    
    # 移除特殊字符
    cleaned_name = re.sub(r'[$「」()（）\s-]', '', standardized_name)
    return cleaned_name.upper()

def is_ipv6(url: str) -> bool:
    """判断URL是否为IPv6地址"""
    if not url:
        return False
    return re.match(r'^http:\/\/\[[0-9a-fA-F:]+\]', url) is not None

def find_similar_name(target_name: str, name_list: List[str], cutoff: float = None) -> Optional[str]:
    """模糊匹配最相似的频道名"""
    import difflib
    if not target_name or not name_list:
        return None
    
    cutoff = cutoff or MATCH_CUTOFF
    name_set = set(name_list)
    
    # 精确匹配
    if target_name in name_set:
        return target_name
    
    # 模糊匹配
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=cutoff)
    return matches[0] if matches else None

def sort_and_filter_urls(
    urls: List[str], 
    written_urls: set, 
    latency_results: Dict[str, SpeedTestResult], 
    latency_threshold: float
) -> List[str]:
    """排序和过滤URL（核心：URL黑名单过滤）"""
    if not urls:
        return []
    
    filtered_urls = []
    # 预处理黑名单关键词（转小写，去空）
    url_blacklist = [kw.strip().lower() for kw in URL_BLACKLIST if kw.strip()]
    blacklist_filter_count = 0

    for url in urls:
        url = url.strip()
        if not url or url in written_urls:
            continue
        
        # URL黑名单过滤：包含任意关键词即过滤
        if url_blacklist:
            url_lower = url.lower()
            hit_kw = [kw for kw in url_blacklist if kw in url_lower]
            if hit_kw:
                blacklist_filter_count += 1
                logger.debug(f"URL命中黑名单过滤：{url[:80]} | 命中关键词：{','.join(hit_kw)}")
                continue
        
        # 延迟过滤
        if latency_results:
            result = latency_results.get(url)
            if not result or not result.success or result.latency is None or result.latency > latency_threshold:
                continue
        
        filtered_urls.append(url)
    
    # 输出黑名单过滤统计
    if url_blacklist and blacklist_filter_count > 0:
        logger.info(f"URL黑名单过滤完成：共过滤 {blacklist_filter_count} 个URL")
    
    # 按IP版本排序
    if IP_VERSION_PRIORITY == "ipv6":
        filtered_urls.sort(key=lambda u: is_ipv6(u), reverse=True)
    else:
        filtered_urls.sort(key=lambda u: is_ipv6(u))
    
    # 按延迟排序
    if latency_results:
        filtered_urls.sort(key=lambda u: latency_results[u].latency if latency_results.get(u) else 9999)
    
    written_urls.update(filtered_urls)
    return filtered_urls

def add_url_suffix(url: str, index: int, total_urls: int, ip_version: str, latency: float) -> str:
    """添加URL后缀"""
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
    """获取GitHub logo列表"""
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
            break
        except Exception as e:
            logger.warning(f"获取GitHub logo列表失败：{str(e)[:50]}")
            continue
    
    if not logo_files:
        logo_files = [
            "CCTV1.png", "CCTV2.png", "湖南卫视.png", "浙江卫视.png", "江苏卫视.png"
        ]
    
    return logo_files

def get_channel_logo_url(channel_name: str) -> str:
    """生成logo URL"""
    if not channel_name:
        return ""
    
    clean_logo_name = clean_channel_name(channel_name)
    logo_filename = f"{clean_logo_name}.png"
    
    # 本地logo
    for logo_dir in LOGO_DIRS:
        local_logo_path = logo_dir / logo_filename
        if len(str(local_logo_path)) < 255 and local_logo_path.exists():
            return local_logo_path.as_posix()
    
    # GitHub logo
    try:
        github_logo_files = get_github_logo_list()
        if logo_filename in github_logo_files:
            return f"{BACKUP_LOGO_BASE_URL}/{logo_filename}"
    except Exception as e:
        logger.debug(f"检查GitHub logo失败：{str(e)[:30]}")
    
    return ""

# ===================== M3U处理函数 =====================
def generate_basic_m3u(all_channels: OrderedDict):
    """生成基础M3U文件"""
    basic_m3u_path = OUTPUT_FOLDER / "live_basic.m3u"
    basic_txt_path = OUTPUT_FOLDER / "live_basic.txt"
    
    try:
        with open(basic_m3u_path, "w", encoding="utf-8") as f_m3u, \
             open(basic_txt_path, "w", encoding="utf-8") as f_txt:
            
            # 写入M3U头部
            epg_str = ",".join(f'"{url}"' for url in EPG_URLS) if EPG_URLS else ""
            f_m3u.write(f"#EXTM3U x-tvg-url={epg_str}\n")
            f_m3u.write(f"# 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            total_written = 0
            for group_title, channel_list in all_channels.items():
                f_m3u.write(f"# ===== 分类：{group_title} =====\n")
                f_txt.write(f"{group_title},#genre#\n")
                
                for channel_name, url in channel_list:
                    if not url or not url.startswith(("http://", "https://")):
                        continue
                    
                    # 获取元信息
                    meta = channel_meta_cache.get(url)
                    if meta and meta.raw_extinf:
                        f_m3u.write(meta.raw_extinf + "\n")
                    else:
                        standardized_tvg_name = standardize_channel_name(channel_name)
                        f_m3u.write(
                            f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{standardized_tvg_name}\" "
                            f"tvg-logo=\"{get_channel_logo_url(channel_name)}\" group-title=\"{group_title}\",{channel_name}\n"
                        )
                    
                    f_m3u.write(url + "\n\n")
                    f_txt.write(f"{channel_name},{url}\n")
                    total_written += 1
            
            logger.info(f"基础M3U文件生成完成：{basic_m3u_path} (共{total_written}个频道)")
    except Exception as e:
        logger.error(f"生成基础M3U失败：{str(e)}", exc_info=True)

def extract_m3u_meta(content: str, source_url: str) -> Tuple[OrderedDict, List[ChannelMeta]]:
    """提取M3U元信息"""
    m3u_pattern = re.compile(
        r"(#EXTINF:-?\d+.*?)\n\s*([^#\n\r\s].*?)(?=\s|#|$)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE
    )
    attr_pattern = re.compile(r'(\w+)-(\w+)="([^"]*)"')
    
    categorized_channels = OrderedDict()
    meta_list = []
    seen_urls = set()
    
    matches = m3u_pattern.findall(content)
    for raw_extinf, url in matches:
        url = url.strip()
        raw_extinf = raw_extinf.strip()
        
        if not url or not url.startswith(("http://", "https://")) or url in seen_urls:
            continue
        
        seen_urls.add(url)
        url_source_mapping[url] = source_url
        
        # 解析属性
        tvg_id = tvg_name = tvg_logo = group_title = None
        channel_name = "未知频道"
        
        attr_matches = attr_pattern.findall(raw_extinf)
        for attr1, attr2, value in attr_matches:
            if attr1 == "tvg" and attr2 == "id":
                tvg_id = value
            elif attr1 == "tvg" and attr2 == "name":
                tvg_name = standardize_channel_name(value)
            elif attr1 == "tvg" and attr2 == "logo":
                tvg_logo = value
            elif attr1 == "group" and attr2 == "title":
                group_title = value
        
        # 提取频道名
        name_match = re.search(r',\s*(.+?)\s*$', raw_extinf)
        if name_match:
            channel_name = name_match.group(1).strip()
        
        group_title = group_title if group_title else "未分类"
        
        # 创建元信息
        meta = ChannelMeta(
            url=url,
            raw_extinf=raw_extinf,
            tvg_id=tvg_id,
            tvg_name=tvg_name,
            tvg_logo=tvg_logo,
            group_title=group_title,
            channel_name=channel_name,
            clean_channel_name=clean_channel_name(channel_name),
            source_url=source_url
        )
        
        meta_list.append(meta)
        channel_meta_cache[url] = meta
        
        if group_title not in categorized_channels:
            categorized_channels[group_title] = []
        categorized_channels[group_title].append((channel_name, url))
    
    logger.info(f"M3U提取完成：{len(meta_list)}个频道")
    return categorized_channels, meta_list

def extract_channels_from_content(content: str, source_url: str) -> OrderedDict:
    """提取频道和URL"""
    categorized_channels = OrderedDict()
    
    # 优先处理M3U格式
    if "#EXTM3U" in content:
        m3u_categorized, _ = extract_m3u_meta(content, source_url)
        categorized_channels = m3u_categorized
    else:
        # 处理普通文本格式
        lines = content.split('\n')
        current_group = "默认分类"
        seen_urls = set()
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith(("//", "#", "/*", "*/")):
                # 识别分类行
                if any(keyword in line.lower() for keyword in ['#分类', '#genre', '分类:', 'genre:']):
                    group_match = re.search(r'[：:=](\S+)', line)
                    current_group = group_match.group(1).strip() if group_match else "默认分类"
                continue
            
            # 匹配频道名,URL格式
            pattern = r'([^,|#$]+)[,|#$]\s*(https?://[^\s,|#$]+)'
            matches = re.findall(pattern, line, re.IGNORECASE)
            if matches:
                for name, url in matches:
                    name = name.strip()
                    url = url.strip()
                    if not url or url in seen_urls:
                        continue
                    
                    seen_urls.add(url)
                    
                    # 智能分类
                    group_title = current_group
                    if any(keyword in name for keyword in ['CCTV', '央视']):
                        group_title = "央视频道"
                    elif any(keyword in name for keyword in ['卫视']):
                        group_title = "卫视频道"
                    
                    # 生成元信息
                    standardized_tvg_name = standardize_channel_name(name)
                    tvg_logo = get_channel_logo_url(name)
                    raw_extinf = f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{standardized_tvg_name}\" tvg-logo=\"{tvg_logo}\" group-title=\"{group_title}\",{name}"
                    
                    meta = ChannelMeta(
                        url=url,
                        raw_extinf=raw_extinf,
                        tvg_id="",
                        tvg_name=standardized_tvg_name,
                        tvg_logo=tvg_logo,
                        group_title=group_title,
                        channel_name=name,
                        clean_channel_name=clean_channel_name(name),
                        source_url=source_url
                    )
                    channel_meta_cache[url] = meta
                    
                    if group_title not in categorized_channels:
                        categorized_channels[group_title] = []
                    categorized_channels[group_title].append((name, url))
    
    if not categorized_channels:
        categorized_channels["未分类频道"] = []
    
    logger.info(f"提取到 {sum(len(v) for v in categorized_channels.values())} 个有效频道")
    return categorized_channels

# ===================== 网络请求函数 =====================
def replace_github_domain(url: str) -> List[str]:
    """替换GitHub域名"""
    if not url or "github" not in url.lower():
        return [url]
    
    candidate_urls = [url]
    for mirror in GITHUB_MIRRORS:
        for original in GITHUB_MIRRORS:
            if original in url:
                new_url = url.replace(original, mirror)
                if new_url not in candidate_urls:
                    candidate_urls.append(new_url)
    
    for base_url in candidate_urls:
        for proxy in PROXY_PREFIXES:
            if not base_url.startswith(proxy):
                proxy_url = proxy + base_url
                if proxy_url not in candidate_urls:
                    candidate_urls.append(proxy_url)
    
    return list(dict.fromkeys(candidate_urls))[:5]

def fetch_url_with_retry(url: str, timeout: int = 15) -> Optional[str]:
    """带重试的URL抓取"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # 修复GitHub blob URL
    original_url = url
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    
    candidate_urls = replace_github_domain(url)
    timeouts = [5, 10, 15]
    
    for idx, candidate in enumerate(candidate_urls):
        current_timeout = timeouts[min(idx, len(timeouts)-1)]
        try:
            response = requests.get(
                candidate,
                headers=headers,
                timeout=current_timeout,
                verify=False,
                allow_redirects=True
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding or 'utf-8'
            return response.text
        except Exception as e:
            logger.warning(f"抓取失败 [{idx+1}]: {candidate} | {str(e)[:50]}")
            continue
    
    logger.error(f"所有链接抓取失败：{original_url}")
    return None

# ===================== 测速模块 =====================
class SpeedTester:
    """异步测速器"""
    def __init__(self):
        self.session = None
        self.concurrent_limit = CONCURRENT_LIMIT
        self.timeout = TIMEOUT
        self.retry_times = RETRY_TIMES
        self.progress_interval = PROGRESS_INTERVAL
        self.processed_count = 0
        self.total_count = 0
        self.start_time = None
    
    async def __aenter__(self):
        """创建会话"""
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        connector = aiohttp.TCPConnector(limit=self.concurrent_limit, ttl_dns_cache=300)
        headers = {"User-Agent": "Mozilla/5.0"}
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers, connector=connector)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭会话"""
        if self.session:
            await self.session.close()
    
    def _update_progress(self):
        """更新进度"""
        self.processed_count += 1
        if self.processed_count % self.progress_interval == 0 or self.processed_count == self.total_count:
            elapsed = time.time() - self.start_time
            speed = self.processed_count / elapsed if elapsed > 0 else 0
            remaining = (self.total_count - self.processed_count) / speed if speed > 0 else 0
            logger.info(
                f"测速进度：{self.processed_count}/{self.total_count} ({self.processed_count/self.total_count*100:.1f}%) | "
                f"速度：{speed:.1f} URL/s | 剩余：{remaining:.0f}s"
            )
    
    async def measure_latency(self, url: str) -> SpeedTestResult:
        """测量单个URL延迟"""
        result = SpeedTestResult(url=url)
        
        for attempt in range(self.retry_times + 1):
            try:
                start_time = time.time()
                async with self.session.get(url) as response:
                    latency = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        result.latency = latency
                        result.success = True
                        break
                    else:
                        result.error = f"HTTP {response.status}"
            except asyncio.TimeoutError:
                result.error = "超时"
            except Exception as e:
                result.error = f"错误：{str(e)[:30]}"
            
            if attempt < self.retry_times:
                await asyncio.sleep(0.5)
        
        self._update_progress()
        return result
    
    async def batch_speed_test(self, urls: List[str]) -> Dict[str, SpeedTestResult]:
        """批量测速"""
        results = {}
        self.total_count = len(urls)
        self.processed_count = 0
        self.start_time = time.time()
        
        if self.total_count == 0:
            logger.info("无URL需要测速")
            return results
        
        logger.info(f"开始测速：{self.total_count}个URL | 并发：{self.concurrent_limit} | 超时：{self.timeout}s")
        
        semaphore = asyncio.Semaphore(self.concurrent_limit)
        
        async def worker(url):
            async with semaphore:
                result = await self.measure_latency(url)
                results[url] = result
        
        tasks = [worker(url) for url in urls if url.strip()]
        await asyncio.gather(*tasks)
        
        # 统计结果
        success_count = sum(1 for r in results.values() if r.success)
        avg_latency = sum(r.latency for r in results.values() if r.success and r.latency) / success_count if success_count > 0 else 0
        elapsed = time.time() - self.start_time
        
        logger.info(
            f"测速完成：成功{success_count}/{self.total_count} | 平均延迟：{avg_latency:.2f}ms | 耗时：{elapsed:.1f}s"
        )
        
        return results

# ===================== 核心业务逻辑 =====================
def parse_template(template_file: str) -> OrderedDict:
    """解析模板文件"""
    template_channels = OrderedDict()
    current_category = None

    try:
        with open(template_file, "r", encoding="utf-8") as f:
            for line in f:
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
        logger.error(f"模板文件不存在：{template_file}")
        return OrderedDict()
    except Exception as e:
        logger.error(f"解析模板失败：{str(e)}")
        return OrderedDict()

    logger.info(f"解析模板：{len(template_channels)}个分类，{sum(len(v) for v in template_channels.values())}个频道")
    return template_channels

def fetch_channels(url: str) -> OrderedDict:
    """抓取频道"""
    channels = OrderedDict()
    
    try:
        content = fetch_url_with_retry(url)
        if content is None:
            return channels
        
        channels = extract_channels_from_content(content, url)
    except Exception as e:
        logger.error(f"处理 {url} 异常：{str(e)}", exc_info=True)

    return channels

def merge_channels(target: OrderedDict, source: OrderedDict):
    """合并频道"""
    url_set = set()
    
    # 收集已有的URL
    for category_name, ch_list in target.items():
        for _, url in ch_list:
            url_set.add(url)
    
    # 合并源数据
    for category_name, channel_list in source.items():
        if category_name not in target:
            target[category_name] = []
        
        for name, url in channel_list:
            if url not in url_set:
                target[category_name].append((name, url))
                url_set.add(url)

def match_channels(template_channels: OrderedDict, all_channels: OrderedDict) -> OrderedDict:
    """匹配频道"""
    matched_channels = OrderedDict()
    unmatched_channels = []
    
    # 构建映射
    name_to_urls = {}
    all_online_names = set()
    all_clean_names = set()
    
    for _, channel_list in all_channels.items():
        for name, url in channel_list:
            if name:
                clean_name = clean_channel_name(name)
                all_online_names.add(name)
                all_clean_names.add(clean_name)
                name_to_urls.setdefault(name, []).append(url)
                name_to_urls.setdefault(clean_name, []).append(url)
    
    all_online_names_list = list(all_online_names)
    all_clean_names_list = list(all_clean_names)
    
    # 匹配
    for category, template_names in template_channels.items():
        matched_channels[category] = OrderedDict()
        for channel_name in template_names:
            clean_template_name = clean_channel_name(channel_name)
            matched_name = None
            
            # 多轮匹配
            if channel_name in all_online_names:
                matched_name = channel_name
            elif clean_template_name in all_clean_names:
                matched_name = clean_template_name
            else:
                matched_name = find_similar_name(channel_name, all_online_names_list)
            if not matched_name:
                matched_name = find_similar_name(clean_template_name, all_clean_names_list)
            
            if matched_name and matched_name in name_to_urls:
                matched_channels[category][channel_name] = name_to_urls[matched_name]
            else:
                unmatched_channels.append(channel_name)
    
    # 统计
    total_template = sum(len(v) for v in template_channels.values())
    matched_count = total_template - len(unmatched_channels)
    logger.info(f"\n频道匹配统计：")
    logger.info(f"  - 模板总频道：{total_template}")
    logger.info(f"  - 匹配成功：{matched_count} ({matched_count/total_template*100:.1f}%)")
    logger.info(f"  - 未匹配：{len(unmatched_channels)}")
    
    return matched_channels

def generate_final_m3u(matched_channels: OrderedDict, latency_results: Dict[str, SpeedTestResult]):
    """生成最终的M3U文件"""
    final_m3u_path = OUTPUT_FOLDER / "live_final.m3u"
    written_urls = set()
    
    try:
        with open(final_m3u_path, "w", encoding="utf-8") as f:
            # 写入头部
            epg_str = ",".join(f'"{url}"' for url in EPG_URLS) if EPG_URLS else ""
            f.write(f"#EXTM3U x-tvg-url={epg_str}\n")
            f.write(f"# 最终版直播源（已过滤黑名单+测速筛选）\n")
            f.write(f"# 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# URL黑名单关键词：{URL_BLACKLIST}\n\n")
            
            # 写入公告
            for announcement in ANNOUNCEMENTS:
                f.write(f"# {announcement}\n")
            f.write("\n")
            
            total_written = 0
            for category, channel_dict in matched_channels.items():
                f.write(f"# ===== {category} =====\n")
                
                for channel_name, urls in channel_dict.items():
                    # 过滤和排序URL
                    filtered_urls = sort_and_filter_urls(
                        urls, written_urls, latency_results, LATENCY_THRESHOLD
                    )
                    
                    if not filtered_urls:
                        continue
                    
                    # 写入频道信息
                    for idx, url in enumerate(filtered_urls, 1):
                        meta = channel_meta_cache.get(url)
                        latency = latency_results[url].latency if latency_results.get(url) else 0
                        ip_version = "IPv6" if is_ipv6(url) else "IPv4"
                        suffix_url = add_url_suffix(url, idx, len(filtered_urls), ip_version, latency)
                        
                        if meta and meta.raw_extinf:
                            f.write(meta.raw_extinf + "\n")
                        else:
                            standardized_tvg_name = standardize_channel_name(channel_name)
                            f.write(
                                f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{standardized_tvg_name}\" "
                                f"tvg-logo=\"{get_channel_logo_url(channel_name)}\" group-title=\"{category}\",{channel_name}\n"
                            )
                        f.write(suffix_url + "\n")
                    
                    total_written += 1
            
            logger.info(f"\n最终M3U文件生成完成：{final_m3u_path} (共{total_written}个频道)")
    except Exception as e:
        logger.error(f"生成最终M3U失败：{str(e)}", exc_info=True)

# ===================== 主函数（运行入口） =====================
async def main():
    """主函数"""
    logger.info("===== 开始处理直播源 =====")
    logger.info(f"URL黑名单配置：{URL_BLACKLIST}")
    
    # 1. 解析模板
    template_channels = parse_template(TEMPLATE_FILE)
    if not template_channels:
        logger.error("模板解析为空，退出")
        return
    
    # 2. 检查源URL
    if not SOURCE_URLS:
        logger.error("未配置SOURCE_URLS，退出")
        return
    
    # 3. 抓取所有频道
    all_channels = OrderedDict()
    for url in SOURCE_URLS:
        logger.info(f"\n抓取源：{url}")
        fetched_channels = fetch_channels(url)
        merge_channels(all_channels, fetched_channels)
    
    # 4. 生成基础M3U
    generate_basic_m3u(all_channels)
    
    # 5. 匹配频道
    matched_channels = match_channels(template_channels, all_channels)
    
    # 6. 收集所有需要测速的URL
    all_test_urls = []
    for _, channel_dict in matched_channels.items():
        for _, urls in channel_dict.items():
            all_test_urls.extend(urls)
    all_test_urls = list(dict.fromkeys(all_test_urls))  # 去重
    
    # 7. 批量测速
    latency_results = {}
    if all_test_urls:
        async with SpeedTester() as tester:
            latency_results = await tester.batch_speed_test(all_test_urls)
    
    # 8. 生成最终M3U
    generate_final_m3u(matched_channels, latency_results)
    
    logger.info("\n===== 所有处理完成 =====")
    logger.info(f"结果文件位置：{OUTPUT_FOLDER.absolute()}")
    logger.info(f"日志文件：{LOG_FILE_PATH.absolute()}")

# ===================== 运行入口 =====================
if __name__ == "__main__":
    # Windows系统需要设置事件循环策略
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 运行主函数
    asyncio.run(main())
