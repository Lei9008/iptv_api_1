import re
import requests
import logging
import asyncio
import aiohttp
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from functools import lru_cache
import warnings
import difflib
import os

# 尝试导入config配置，不存在则使用默认值
try:
    import config
except ImportError:
    config = None

# ===================== 全局配置与常量 =====================
# 屏蔽SSL不安全请求警告
warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

# 画质关键词映射（优先级从低到高）
QUALITY_KEYWORDS = {
    1: ['标清', 'SD', '360p', '480p'],    # 标清
    2: ['高清', 'HD', '720p', '1080i'],   # 高清
    3: ['超清', 'FHD', '1080p', '1080P'], # 超清
    4: ['4K', '超清4K', '2160p', 'UHD']   # 4K
}

# 反向映射：关键词→画质等级
KEYWORD_TO_QUALITY = {}
for level, keywords in QUALITY_KEYWORDS.items():
    for kw in keywords:
        KEYWORD_TO_QUALITY[kw.lower()] = level
        KEYWORD_TO_QUALITY[kw.upper()] = level

# 央视频道别名映射
CNTV_ALIASES = {
    # 基础频道
    "CCTV1": "CCTV1综合",
    "CCTV2": "CCTV2财经",
    "CCTV3": "CCTV3综艺",
    "CCTV4": "CCTV4中文国际",
    "CCTV5": "CCTV5体育",
    "CCTV5+": "CCTV5+体育赛事",
    "cctv5plus": "CCTV5+体育赛事",
    "CCTV6": "CCTV6电影",
    "CCTV7": "CCTV7国防军事",
    "CCTV8": "CCTV8电视剧",
    "CCTV9": "CCTV9纪录",
    "cctvjilu": "CCTV9纪录",
    "CCTV10": "CCTV10科教",
    "CCTV11": "CCTV11戏曲",
    "CCTV12": "CCTV12社会与法",
    "CCTV13": "CCTV13新闻",
    "CCTV14": "CCTV14少儿",
    "cctvchild": "CCTV14少儿",
    "CCTV15": "CCTV15音乐",
    "CCTV16": "CCTV16奥林匹克",
    "CCTV17": "CCTV17农业农村",
    # 海外频道
    "CCTV4欧洲": "CCTV4中文国际（欧洲版）",
    "cctveurope": "CCTV4中文国际（欧洲版）",
    "CCTV4美洲": "CCTV4中文国际（美洲版）",
    "cctvamerica": "CCTV4中文国际（美洲版）"
}

# 超清/4K频道别名映射
CNTV_HD_ALIASES = {
    "CCTV1超清": "CCTV1超清",
    "CCTV2超清": "CCTV2超清",
    "CCTV3超清": "CCTV3超清",
    "CCTV4超清": "CCTV4超清",
    "CCTV5超清": "CCTV5超清",
    "CCTV5+超清": "CCTV5+超清",
    "CCTV6超清": "CCTV6超清",
    "CCTV7超清": "CCTV7超清",
    "CCTV8超清": "CCTV8超清",
    "CCTV9超清": "CCTV9超清",
    "CCTV10超清": "CCTV10超清",
    "CCTV11超清": "CCTV11超清",
    "CCTV12超清": "CCTV12超清",
    "CCTV13超清": "CCTV13超清",
    "CCTV14超清": "CCTV14超清",
    "CCTV15超清": "CCTV15超清",
    "CCTV17超清": "CCTV17超清",
    "湖南卫视4K": "湖南卫视4K",
    "浙江卫视4K": "浙江卫视4K",
    "广东4K超高清": "广东4K超高清",
    "浙江卫视超清": "浙江卫视超清",
    "江苏卫视超清": "江苏卫视超清",
    "北京卫视超清": "北京卫视超清",
    "湖北卫视超清": "湖北卫视超清",
    "广东卫视超清": "广东卫视超清",
    "东方卫视超清": "东方卫视超清",
    "辽宁卫视超清": "辽宁卫视超清",
    "东南卫视超清": "东南卫视超清",
    "江西卫视超清": "江西卫视超清"
}

# 合并别名映射
CNTV_ALIASES.update(CNTV_HD_ALIASES)

# 标准名→官方简写（用于台标）
CNTV_STANDARD_TO_SHORT = {
    "CCTV1综合": "cctv1",
    "CCTV2财经": "cctv2",
    "CCTV3综艺": "cctv3",
    "CCTV4中文国际": "cctv4",
    "CCTV5体育": "cctv5",
    "CCTV5+体育赛事": "cctv5plus",
    "CCTV6电影": "cctv6",
    "CCTV7国防军事": "cctv7",
    "CCTV8电视剧": "cctv8",
    "CCTV9纪录": "cctvjilu",
    "CCTV10科教": "cctv10",
    "CCTV11戏曲": "cctv11",
    "CCTV12社会与法": "cctv12",
    "CCTV13新闻": "cctv13",
    "CCTV14少儿": "cctvchild",
    "CCTV15音乐": "cctv15",
    "CCTV16奥林匹克": "cctv16",
    "CCTV17农业农村": "cctv17",
    "CCTV4中文国际（欧洲版）": "cctveurope",
    "CCTV4中文国际（美洲版）": "cctvamerica",
    # 超清/4K频道
    "CCTV1超清": "cctv1hd",
    "CCTV2超清": "cctv2hd",
    "CCTV3超清": "cctv3hd",
    "CCTV4超清": "cctv4hd",
    "CCTV5超清": "cctv5hd",
    "CCTV5+超清": "cctv5plushd",
    "CCTV6超清": "cctv6hd",
    "CCTV7超清": "cctv7hd",
    "CCTV8超清": "cctv8hd",
    "CCTV9超清": "cctv9hd",
    "CCTV10超清": "cctv10hd",
    "CCTV11超清": "cctv11hd",
    "CCTV12超清": "cctv12hd",
    "CCTV13超清": "cctv13hd",
    "CCTV14超清": "cctv14hd",
    "CCTV15超清": "cctv15hd",
    "CCTV17超清": "cctv17hd",
    "湖南卫视4K": "hunan4k",
    "浙江卫视4K": "zhejiang4k",
    "广东4K超高清": "guangdong4k",
    "浙江卫视超清": "zhejianghd",
    "江苏卫视超清": "jiangsuhd",
    "北京卫视超清": "beijinghd"
}

# 默认配置
CONFIG_DEFAULTS = {
    "LATENCY_THRESHOLD": 800,
    "CONCURRENT_LIMIT": 30,
    "TIMEOUT": 15,
    "RETRY_TIMES": 3,
    "IP_VERSION_PRIORITY": "ipv4",
    "URL_BLACKLIST": [],
    "TEMPLATE_FILE": "demo.txt",
    "EPG_URLS": [],
    "ANNOUNCEMENTS": [],
    "SOURCE_URLS": [],
    "MATCH_CUTOFF": 0.8,
    "PROGRESS_INTERVAL": 100,
    "QUALITY_FIRST": True,
    "HD_LATENCY_BONUS": 400,
    "MIN_HD_CHANNELS": 80
}

# GitHub镜像和代理
GITHUB_MIRRORS = [
    "raw.githubusercontent.com",
    "raw.kkgithub.com",
    "raw.githubusercontents.com",
    "raw.fgit.cf",
    "raw.fgithub.de"
]

PROXY_PREFIXES = [
    "https://ghproxy.com/",
    "https://mirror.ghproxy.com/",
    "https://gh.api.99988866.xyz/"
]

# ===================== 数据结构定义 =====================
@dataclass
class SpeedTestResult:
    """测速结果数据类"""
    url: str
    latency: Optional[float] = None  # 延迟（毫秒）
    resolution: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    quality_level: int = 0  # 画质等级：0-未知 1-标清 2-高清 3-超清 4-4K
    is_hd: bool = False     # 是否高清以上
    quality_tags: List[str] = field(default_factory=list)

@dataclass
class ChannelMeta:
    """频道元信息"""
    url: str
    raw_extinf: str = ""
    tvg_id: Optional[str] = None
    tvg_name: Optional[str] = None
    tvg_logo: Optional[str] = None
    group_title: Optional[str] = None
    channel_name: Optional[str] = None
    clean_channel_name: str = ""
    source_url: str = ""
    has_hd_tag: bool = False  # 频道名是否含高清标识

# ===================== 全局存储 =====================
channel_meta_cache: Dict[str, ChannelMeta] = {}  # key: url
raw_extinf_mapping: Dict[str, str] = {}          # url -> 原始#EXTINF行
url_source_mapping: Dict[str, str] = {}          # url -> 来源URL

# ===================== 日志配置 =====================
OUTPUT_FOLDER = Path("output")
OUTPUT_FOLDER.mkdir(exist_ok=True)
LOG_FILE_PATH = OUTPUT_FOLDER / "iptv_processor.log"

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

# ===================== 工具函数 =====================
def get_config_value(key: str):
    """获取配置值（优先config.py，无则用默认）"""
    if config and hasattr(config, key):
        return getattr(config, key)
    return CONFIG_DEFAULTS.get(key)

def get_cctv_standard_name(alias: str) -> Optional[str]:
    """根据别名获取央视标准频道名"""
    if not alias:
        return None
    # 精确匹配
    if alias in CNTV_ALIASES:
        return CNTV_ALIASES[alias]
    # 模糊匹配
    alias_lower = alias.lower().strip()
    for key, value in CNTV_ALIASES.items():
        if key.lower() == alias_lower or key.lower() in alias_lower:
            return value
    return None

def get_cctv_short_name(standard_name: str) -> Optional[str]:
    """根据标准名获取简写"""
    if not standard_name:
        return None
    return CNTV_STANDARD_TO_SHORT.get(standard_name)

def clean_channel_name(channel_name: str) -> str:
    """标准化清洗频道名称（保留画质标识）"""
    if not channel_name:
        return ""
    
    # 优先匹配央视别名
    channel_name_lower = channel_name.lower().strip()
    for alias, standard_name in CNTV_ALIASES.items():
        if alias.lower() == channel_name_lower or alias in channel_name:
            # 保留画质标识
            quality_suffix = ""
            for kw in ['超清', '4K', 'HD', 'FHD', 'UHD', '高清']:
                if kw in channel_name:
                    quality_suffix = kw
                    break
            return standard_name + (quality_suffix if quality_suffix else "")
    
    # 通用清洗
    clean_name = re.sub(r'[^\u4e00-\u9fff0-9a-zA-Z+]', '', channel_name)
    clean_name = re.sub(r'(\d+)频道', r'\1', clean_name)
    clean_name = re.sub(r'高清|超清|4K|HD|FHD|UHD', '', clean_name).strip()
    
    # 恢复画质标识
    quality_tags = []
    for kw in ['超清', '4K', 'HD', 'FHD', 'UHD', '高清']:
        if kw in channel_name:
            quality_tags.append(kw)
    
    return clean_name + (''.join(quality_tags) if quality_tags else "")

def analyze_quality_from_text(text: str) -> Tuple[int, bool, List[str]]:
    """从文本（URL/频道名）分析画质等级"""
    if not text:
        return 0, False, []
    
    text_upper = text.upper()
    text_lower = text.lower()
    quality_level = 0
    quality_tags = []
    
    # 匹配画质关键词
    for level, keywords in QUALITY_KEYWORDS.items():
        for kw in keywords:
            if kw in text or kw.upper() in text_upper or kw.lower() in text_lower:
                if level > quality_level:
                    quality_level = level
                quality_tags.append(kw)
    
    # 从分辨率提取
    res_match = re.search(r'(\d+)p', text, re.IGNORECASE)
    if res_match:
        res_num = int(res_match.group(1))
        if res_num >= 2160:
            quality_level = 4
            quality_tags.append('4K')
        elif res_num >= 1080:
            quality_level = 3
            quality_tags.append('1080p')
        elif res_num >= 720:
            quality_level = 2
            quality_tags.append('720p')
        elif res_num >= 480:
            quality_level = 1
            quality_tags.append('480p')
    
    is_hd = quality_level >= 2
    return quality_level, is_hd, quality_tags

def is_ipv6(url: str) -> bool:
    """判断URL是否为IPv6"""
    return '[' in url and ']' in url

def find_similar_name(target: str, candidates: List[str], cutoff: float = None) -> Optional[str]:
    """模糊匹配频道名"""
    if not target or not candidates:
        return None
    cutoff = cutoff or get_config_value("MATCH_CUTOFF")
    matches = difflib.get_close_matches(target, candidates, n=1, cutoff=cutoff)
    return matches[0] if matches else None

# ===================== 模板解析 =====================
def parse_template_file(file_path: str) -> OrderedDict:
    """解析模板文件，返回分类→频道名列表"""
    template_channels = OrderedDict()
    current_category = None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # 匹配分类行：分类名,#genre#
            if ',#genre#' in line:
                current_category = line.split(',#genre#')[0].strip()
                template_channels[current_category] = []
            elif current_category and line.endswith(','):
                # 匹配频道行：频道名,
                channel_name = line.rstrip(',').strip()
                if channel_name:
                    template_channels[current_category].append(channel_name)
    
    except FileNotFoundError:
        logger.error(f"模板文件未找到：{file_path}")
    except Exception as e:
        logger.error(f"解析模板文件失败：{e}")
    
    return template_channels

# ===================== 直播源抓取 =====================
def fetch_m3u_content(url: str) -> Optional[str]:
    """抓取M3U内容（支持GitHub镜像）"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    # 处理GitHub blob链接转为raw链接
    if 'github.com/blob/' in url:
        url = url.replace('github.com/blob/', 'raw.githubusercontent.com/').split('#')[0]
    
    # 尝试原始链接
    try:
        response = requests.get(url, headers=headers, timeout=30, verify=False)
        if response.status_code == 200:
            return response.text
    except Exception as e:
        logger.warning(f"抓取原始链接失败 {url}：{e}")
    
    # 尝试GitHub镜像
    for mirror in GITHUB_MIRRORS:
        if 'raw.githubusercontent.com' in url:
            mirror_url = url.replace('raw.githubusercontent.com', mirror)
            try:
                response = requests.get(mirror_url, headers=headers, timeout=30, verify=False)
                if response.status_code == 200:
                    logger.info(f"使用镜像成功：{mirror_url}")
                    return response.text
            except:
                continue
    
    # 尝试代理前缀
    for proxy in PROXY_PREFIXES:
        proxy_url = proxy + url
        try:
            response = requests.get(proxy_url, headers=headers, timeout=30, verify=False)
            if response.status_code == 200:
                logger.info(f"使用代理成功：{proxy_url}")
                return response.text
        except:
            continue
    
    logger.error(f"所有方式均无法抓取：{url}")
    return None

def parse_m3u_content(content: str, source_url: str) -> Dict[str, List[str]]:
    """解析M3U内容，返回频道名→URL列表"""
    channel_urls = {}
    current_extinf = ""
    current_channel = ""
    
    lines = content.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 匹配EXTINF行
        if line.startswith('#EXTINF:'):
            current_extinf = line
            # 提取频道名
            match = re.search(r',([^,]+)$', line)
            if match:
                current_channel = match.group(1).strip()
            else:
                current_channel = ""
        # 匹配URL行
        elif line.startswith(('http://', 'https://')) and current_channel:
            url = line
            # 过滤黑名单
            blacklist = get_config_value("URL_BLACKLIST")
            if any(black in url for black in blacklist):
                continue
            
            # 清洗频道名
            clean_name = clean_channel_name(current_channel)
            if not clean_name:
                clean_name = current_channel
            
            # 存储URL
            if clean_name not in channel_urls:
                channel_urls[clean_name] = []
            if url not in channel_urls[clean_name]:
                channel_urls[clean_name].append(url)
            
            # 缓存元信息
            channel_meta_cache[url] = ChannelMeta(
                url=url,
                raw_extinf=current_extinf,
                channel_name=current_channel,
                clean_channel_name=clean_name,
                source_url=source_url,
                has_hd_tag=any(kw in current_channel for kw in ['高清', '超清', '4K', 'HD', 'FHD'])
            )
    
    return channel_urls

def fetch_all_sources() -> Dict[str, List[str]]:
    """抓取所有源并合并"""
    all_channels = {}
    source_urls = get_config_value("SOURCE_URLS")
    
    for source_url in source_urls:
        logger.info(f"开始抓取源：{source_url}")
        content = fetch_m3u_content(source_url)
        if not content:
            continue
        
        channel_urls = parse_m3u_content(content, source_url)
        # 合并URL
        for channel_name, urls in channel_urls.items():
            if channel_name not in all_channels:
                all_channels[channel_name] = []
            # 去重
            for url in urls:
                if url not in all_channels[channel_name]:
                    all_channels[channel_name].append(url)
    
    logger.info(f"总共抓取到 {len(all_channels)} 个频道，{sum(len(v) for v in all_channels.values())} 个URL")
    return all_channels

# ===================== 异步测速 =====================
async def test_url_latency(session: aiohttp.ClientSession, url: str, timeout: int) -> SpeedTestResult:
    """测试单个URL延迟"""
    result = SpeedTestResult(url=url)
    start_time = time.time()
    
    try:
        # 分析画质
        quality_level, is_hd, quality_tags = analyze_quality_from_text(url)
        result.quality_level = quality_level
        result.is_hd = is_hd
        result.quality_tags = quality_tags
        
        # 测试连接
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout), verify_ssl=False) as response:
            if response.status == 200:
                # 读取少量数据验证
                await response.content.read(1024)
                latency = (time.time() - start_time) * 1000  # 转毫秒
                result.latency = round(latency, 2)
                result.success = True
    except Exception as e:
        result.error = str(e)
        result.success = False
    
    return result

async def batch_test_latency(urls: List[str]) -> Dict[str, SpeedTestResult]:
    """批量测速"""
    results = {}
    timeout = get_config_value("TIMEOUT")
    concurrent_limit = get_config_value("CONCURRENT_LIMIT")
    
    # 去重
    unique_urls = list(set(urls))
    logger.info(f"开始测速 {len(unique_urls)} 个URL，并发数：{concurrent_limit}")
    
    semaphore = asyncio.Semaphore(concurrent_limit)
    
    async def bounded_test(url):
        async with semaphore:
            for retry in range(get_config_value("RETRY_TIMES")):
                result = await test_url_latency(session, url, timeout)
                if result.success:
                    return (url, result)
                await asyncio.sleep(0.1)
            return (url, result)
    
    async with aiohttp.ClientSession() as session:
        tasks = [bounded_test(url) for url in unique_urls]
        # 进度显示
        processed = 0
        for task in asyncio.as_completed(tasks):
            url, result = await task
            results[url] = result
            processed += 1
            if processed % get_config_value("PROGRESS_INTERVAL") == 0:
                logger.info(f"测速进度：{processed}/{len(unique_urls)}")
    
    # 统计
    success_count = sum(1 for r in results.values() if r.success)
    logger.info(f"测速完成：成功 {success_count}/{len(unique_urls)}")
    return results

# ===================== 频道匹配 =====================
def match_channels(template_channels: OrderedDict, all_channels: Dict[str, List[str]]) -> OrderedDict:
    """匹配频道（优先高清）"""
    matched_channels = OrderedDict()
    unmatched_channels = []
    all_online_names = list(all_channels.keys())
    
    # 优先匹配超清/4K分类
    for category, template_names in template_channels.items():
        matched_channels[category] = OrderedDict()
        
        # 超清/4K分类优先处理
        if "超清" in category or "4K" in category:
            for channel_name in template_names:
                clean_template_name = clean_channel_name(channel_name)
                matched_name = None
                
                # 优先精确匹配
                if channel_name in all_online_names:
                    matched_name = channel_name
                elif clean_template_name in all_online_names:
                    matched_name = clean_template_name
                # 模糊匹配
                else:
                    matched_name = find_similar_name(channel_name, all_online_names)
                
                if matched_name:
                    matched_channels[category][channel_name] = all_channels[matched_name]
                    logger.debug(f"超清频道匹配成功：{channel_name} → {matched_name}")
                else:
                    unmatched_channels.append(channel_name)
        else:
            # 普通分类
            for channel_name in template_names:
                clean_template_name = clean_channel_name(channel_name)
                matched_name = None
                
                if channel_name in all_online_names:
                    matched_name = channel_name
                elif clean_template_name in all_online_names:
                    matched_name = clean_template_name
                else:
                    matched_name = find_similar_name(channel_name, all_online_names)
                
                if matched_name:
                    matched_channels[category][channel_name] = all_channels[matched_name]
                    logger.debug(f"匹配成功：{channel_name} → {matched_name}")
                else:
                    unmatched_channels.append(channel_name)
    
    # 统计
    total_template = sum(len(v) for v in template_channels.values())
    matched_count = total_template - len(unmatched_channels)
    
    # 超清频道统计
    hd_matched = 0
    hd_total = 0
    for category, names in template_channels.items():
        if "超清" in category or "4K" in category:
            hd_total += len(names)
            for name in names:
                if name in matched_channels.get(category, {}):
                    hd_matched += 1
    
    logger.info(f"\n=== 频道匹配统计 ===")
    logger.info(f"模板总频道数：{total_template}")
    logger.info(f"匹配成功数：{matched_count} ({matched_count/total_template*100:.1f}%)")
    logger.info(f"未匹配数：{len(unmatched_channels)}")
    if hd_total > 0:
        logger.info(f"超清/4K频道匹配：{hd_matched}/{hd_total} ({hd_matched/hd_total*100:.1f}%)")
    
    return matched_channels

# ===================== URL排序过滤 =====================
def sort_and_filter_urls(
    urls: List[str], 
    written_urls: set, 
    latency_results: Dict[str, SpeedTestResult]
) -> List[str]:
    """排序过滤URL（高清优先）"""
    if not urls:
        return []
    
    filtered_urls = []
    blacklist = get_config_value("URL_BLACKLIST")
    latency_threshold = get_config_value("LATENCY_THRESHOLD")
    hd_bonus = get_config_value("HD_LATENCY_BONUS")
    
    # 分离高清和普通URL
    hd_urls = []
    normal_urls = []
    
    for url in urls:
        url = url.strip()
        if not url or url in written_urls:
            continue
        
        # 黑名单过滤
        if any(black in url for black in blacklist):
            continue
        
        # 延迟过滤
        keep = True
        result = latency_results.get(url, SpeedTestResult(url=url))
        if result.success and result.latency is not None:
            # 高清频道放宽阈值
            actual_threshold = latency_threshold + (hd_bonus if result.is_hd else 0)
            if result.latency > actual_threshold:
                keep = False
        elif not result.success:
            keep = False
        
        if keep:
            if result.is_hd:
                hd_urls.append(url)
            else:
                normal_urls.append(url)
    
    # 按延迟排序
    def get_latency(url):
        res = latency_results.get(url, SpeedTestResult(url=url))
        return res.latency if (res.success and res.latency) else 9999
    
    hd_urls.sort(key=get_latency)
    normal_urls.sort(key=get_latency)
    
    # IP版本优先级
    ip_priority = get_config_value("IP_VERSION_PRIORITY")
    if ip_priority == "ipv6":
        hd_urls.sort(key=lambda u: (is_ipv4(u), get_latency(u)))
        normal_urls.sort(key=lambda u: (is_ipv4(u), get_latency(u)))
    else:
        hd_urls.sort(key=lambda u: (is_ipv6(u), get_latency(u)))
        normal_urls.sort(key=lambda u: (is_ipv6(u), get_latency(u)))
    
    # 合并：高清优先
    filtered_urls = hd_urls + normal_urls
    written_urls.update(filtered_urls)
    
    return filtered_urls

def is_ipv4(url: str) -> bool:
    """判断是否IPv4"""
    return re.search(r'\d+\.\d+\.\d+\.\d+', url) is not None

# ===================== 生成M3U文件 =====================
def generate_m3u(matched_channels: OrderedDict, latency_results: Dict[str, SpeedTestResult]):
    """生成最终的M3U文件"""
    # 准备输出内容
    m3u_header = "#EXTM3U x-tvg-url=\"{}\"\n".format(",".join(get_config_value("EPG_URLS")))
    written_urls = set()
    
    # 输出文件路径
    ipv4_file = OUTPUT_FOLDER / "live_ipv4.m3u"
    ipv6_file = OUTPUT_FOLDER / "live_ipv6.m3u"
    
    ipv4_content = [m3u_header]
    ipv6_content = [m3u_header]
    
    # 添加公告栏
    announcements = get_config_value("ANNOUNCEMENTS")
    for ann in announcements:
        category = ann.get("channel", "公告栏")
        ipv4_content.append(f"\n#EXTGRP:{category}\n")
        ipv6_content.append(f"\n#EXTGRP:{category}\n")
        
        for entry in ann.get("entries", []):
            name = entry.get("name", "")
            url = entry.get("url", "")
            logo = entry.get("logo", "")
            
            extinf = f"#EXTINF:-1 tvg-id=\"{name}\" tvg-logo=\"{logo}\",{name}"
            ipv4_content.append(extinf)
            ipv4_content.append(url if url else "")
            ipv6_content.append(extinf)
            ipv6_content.append(url if url else "")
    
    # 生成频道内容
    for category, channels in matched_channels.items():
        logger.info(f"生成分类：{category}")
        
        # 添加分类标识
        ipv4_content.append(f"\n#EXTGRP:{category}\n")
        ipv6_content.append(f"\n#EXTGRP:{category}\n")
        
        for channel_name, urls in channels.items():
            # 排序过滤URL
            filtered_urls = sort_and_filter_urls(urls, written_urls, latency_results)
            if not filtered_urls:
                continue
            
            # 获取台标
            short_name = get_cctv_short_name(clean_channel_name(channel_name)) or channel_name
            logo_base = get_config_value("GITHUB_LOGO_BASE_URL")
            logo_url = f"{logo_base}/{short_name}.png" if logo_base else ""
            
            # 生成EXTINF行
            extinf = f"#EXTINF:-1 tvg-id=\"{channel_name}\" tvg-logo=\"{logo_url}\",{channel_name}"
            
            # 分离IPv4/IPv6
            for url in filtered_urls:
                if is_ipv6(url):
                    ipv6_content.append(extinf)
                    ipv6_content.append(url)
                else:
                    ipv4_content.append(extinf)
                    ipv4_content.append(url)
    
    # 写入文件
    try:
        with open(ipv4_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(ipv4_content))
        logger.info(f"IPv4文件生成完成：{ipv4_file}")
        
        with open(ipv6_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(ipv6_content))
        logger.info(f"IPv6文件生成完成：{ipv6_file}")
    except Exception as e:
        logger.error(f"写入文件失败：{e}")

# ===================== 生成测速报告 =====================
def generate_speed_report(latency_results: Dict[str, SpeedTestResult]):
    """生成测速报告"""
    report_path = OUTPUT_FOLDER / "speed_test_report.txt"
    
    # 统计
    total = len(latency_results)
    success = sum(1 for r in latency_results.values() if r.success)
    hd_success = sum(1 for r in latency_results.values() if r.success and r.is_hd)
    hd_total = sum(1 for r in latency_results.values() if r.is_hd)
    
    # 按画质分组
    quality_groups = {
        0: "未知画质",
        1: "标清",
        2: "高清",
        3: "超清",
        4: "4K"
    }
    
    report = [
        f"=== IPTV测速报告 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===",
        f"总测试URL数：{total}",
        f"成功数：{success} ({success/total*100:.1f}%)",
        f"高清及以上URL数：{hd_total} (成功：{hd_success})",
        "",
        "=== 各画质统计 ==="
    ]
    
    for level, name in quality_groups.items():
        urls = [r for r in latency_results.values() if r.quality_level == level]
        success_urls = [r for r in urls if r.success]
        avg_latency = sum(r.latency for r in success_urls if r.latency) / len(success_urls) if success_urls else 0
        report.append(f"{name}：{len(success_urls)}/{len(urls)} (平均延迟：{avg_latency:.1f}ms)")
    
    # 延迟分布
    report.append("\n=== 延迟分布 ===")
    latency_ranges = [
        (0, 200, "0-200ms"),
        (200, 500, "200-500ms"),
        (500, 1000, "500-1000ms"),
        (1000, float('inf'), ">1000ms")
    ]
    
    for min_lat, max_lat, label in latency_ranges:
        count = sum(1 for r in latency_results.values() if r.success and r.latency >= min_lat and r.latency < max_lat)
        report.append(f"{label}：{count} 个URL")
    
    # 详细列表（前50个高清URL）
    hd_urls = sorted(
        [r for r in latency_results.values() if r.success and r.is_hd],
        key=lambda x: x.latency or 9999
    )[:50]
    
    report.append("\n=== 前50个高清URL（按延迟排序）===")
    for i, res in enumerate(hd_urls, 1):
        report.append(f"{i}. {res.channel_name or '未知频道'} - {res.latency}ms - {res.url[:100]}...")
    
    # 写入文件
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(report))
        logger.info(f"测速报告生成完成：{report_path}")
    except Exception as e:
        logger.error(f"生成报告失败：{e}")

# ===================== 主函数 =====================
def main():
    """主执行函数"""
    logger.info("=== 开始IPTV直播源处理 ===")
    start_time = time.time()
    
    try:
        # 1. 解析模板
        template_file = get_config_value("TEMPLATE_FILE")
        template_channels = parse_template_file(template_file)
        if not template_channels:
            logger.error("模板解析失败，退出")
            return
        
        # 2. 抓取所有源
        all_channels = fetch_all_sources()
        if not all_channels:
            logger.error("未抓取到任何源，退出")
            return
        
        # 3. 频道匹配
        matched_channels = match_channels(template_channels, all_channels)
        
        # 4. 收集所有URL用于测速
        all_test_urls = []
        for category, channels in matched_channels.items():
            for urls in channels.values():
                all_test_urls.extend(urls)
        
        # 5. 异步测速
        latency_results = asyncio.run(batch_test_latency(all_test_urls))
        
        # 6. 生成M3U文件
        generate_m3u(matched_channels, latency_results)
        
        # 7. 生成测速报告
        generate_speed_report(latency_results)
        
        # 统计耗时
        elapsed = time.time() - start_time
        logger.info(f"\n=== 处理完成 ===")
        logger.info(f"总耗时：{elapsed:.2f} 秒")
        logger.info(f"输出目录：{OUTPUT_FOLDER.absolute()}")
        
    except Exception as e:
        logger.error(f"程序执行失败：{e}", exc_info=True)

if __name__ == "__main__":
    main()
