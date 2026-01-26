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

# 屏蔽SSL不安全请求警告
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

# ===================== 初始化配置（优化版） =====================
# 确保 output 文件夹存在
OUTPUT_FOLDER = Path("output")
OUTPUT_FOLDER.mkdir(exist_ok=True)

# 初始化 logo 目录
LOGO_DIRS = [Path("./pic/logos"), Path("./pic/logo")]
for dir_path in LOGO_DIRS:
    dir_path.mkdir(parents=True, exist_ok=True)

# 配置默认值
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
    "MATCH_CUTOFF": 0.4,
    "PROGRESS_INTERVAL": 50
}

# 统一读取配置（兼容大小写）
def get_config_value(key: str, default=None):
    """统一读取配置，兼容大小写"""
    # 优先读大写，再读小写，最后用默认值
    upper_val = getattr(config, key.upper(), None)
    lower_val = getattr(config, key.lower(), None)
    
    if upper_val is not None:
        return upper_val
    elif lower_val is not None:
        return lower_val
    else:
        return default or CONFIG_DEFAULTS.get(key.upper())

# 读取核心配置
LATENCY_THRESHOLD = get_config_value("LATENCY_THRESHOLD")
CONCURRENT_LIMIT = get_config_value("CONCURRENT_LIMIT")
TIMEOUT = get_config_value("TIMEOUT")
RETRY_TIMES = get_config_value("RETRY_TIMES")
IP_VERSION_PRIORITY = get_config_value("IP_VERSION_PRIORITY")
URL_BLACKLIST = get_config_value("URL_BLACKLIST")
TEMPLATE_FILE = get_config_value("TEMPLATE_FILE")
EPG_URLS = get_config_value("EPG_URLS")
ANNOUNCEMENTS = get_config_value("ANNOUNCEMENTS")
MATCH_CUTOFF = get_config_value("MATCH_CUTOFF")
PROGRESS_INTERVAL = get_config_value("PROGRESS_INTERVAL")

# 读取SOURCE_URLS（兼容大小写+统一转小写）
source_urls_upper = getattr(config, 'SOURCE_URLS', None)
source_urls_lower = getattr(config, 'source_urls', None)
if source_urls_upper is not None:
    SOURCE_URLS_RAW = source_urls_upper
elif source_urls_lower is not None:
    SOURCE_URLS_RAW = source_urls_lower
else:
    SOURCE_URLS_RAW = CONFIG_DEFAULTS["SOURCE_URLS"]
# 统一转小写并过滤空值
SOURCE_URLS = [url.strip().lower() for url in SOURCE_URLS_RAW if url.strip()]

# 读取GitHub Logo配置
GITHUB_LOGO_BASE_URL = get_config_value("GITHUB_LOGO_BASE_URL", 
                              "https://raw.githubusercontent.com/fanmingming/live/main/tv")
BACKUP_LOGO_BASE_URL = get_config_value("BACKUP_LOGO_BASE_URL",
                              "https://ghproxy.com/https://raw.githubusercontent.com/fanmingming/live/main/tv")
GITHUB_LOGO_API_URLS = get_config_value("GITHUB_LOGO_API_URLS", [
    "https://api.github.com/repos/fanmingming/live/contents/main/tv",
    "https://ghproxy.com/https://api.github.com/repos/fanmingming/live/contents/main/tv"
])

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
def clean_channel_name(channel_name: str) -> str:
    """标准化清洗频道名称"""
    if not channel_name:
        return ""
    
    # 保留特殊标识
    channel_name = re.sub(r'CCTV-?5\+', 'CCTV5+', channel_name)
    channel_name = re.sub(r'CCTV5\+\s*(\S+)', 'CCTV5+', channel_name)
    
    # 港澳台/凤凰卫视特殊处理
    channel_name = channel_name.replace("翡翠台", "TVB翡翠台")
    channel_name = channel_name.replace("凤凰中文", "凤凰卫视中文台")
    channel_name = channel_name.replace("凤凰资讯", "凤凰卫视资讯台")
    channel_name = channel_name.replace("凤凰香港", "凤凰卫视香港台")
    channel_name = channel_name.replace("凤凰卫视", "凤凰卫视中文台")
    channel_name = channel_name.replace("香港卫视", "香港卫视综合台")
    
    # 正则分组修复
    channel_name = re.sub(r'(\w+)二套(\w*)', r'\12套\2', channel_name)
    channel_name = re.sub(r'(\w+)三套(\w*)', r'\13套\2', channel_name)
    
    # 其他名称简化
    channel_name = re.sub(r'经济生活', '经视', channel_name)
    channel_name = re.sub(r'影视', '影视频道', channel_name)
    channel_name = re.sub(r'文旅记录', '文旅', channel_name)
    
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

def find_similar_name(target_name: str, name_list: List[str], cutoff: float = None) -> Optional[str]:
    """模糊匹配最相似的频道名"""
    if not target_name or not name_list:
        return None
    
    cutoff = cutoff or MATCH_CUTOFF
    name_set = set(name_list)
    
    # 精确匹配
    if target_name in name_set:
        return target_name
    
    # 简化名匹配
    simplified_target = re.sub(r'卫视|频道|综合|台', '', target_name)
    simplified_names = {re.sub(r'卫视|频道|综合|台', '', n): n for n in name_list}
    if simplified_target in simplified_names:
        return simplified_names[simplified_target]
    
    # 模糊匹配
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=cutoff)
    if matches:
        return matches[0]
    
    # 进一步降低阈值
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=cutoff-0.1)
    return matches[0] if matches else None

def filter_blacklist_urls(urls: List[str]) -> List[str]:
    """独立的URL黑名单过滤函数（仅在生成最终M3U时调用）"""
    if not urls or not URL_BLACKLIST:
        return urls
    
    # 预处理黑名单关键词
    url_blacklist = [kw.strip().lower() for kw in URL_BLACKLIST if kw.strip()]
    if not url_blacklist:
        return urls
    
    filtered_urls = []
    blacklist_count = 0
    
    for url in urls:
        url = url.strip()
        if not url:
            continue
        
        # 检查是否命中黑名单
        url_lower = url.lower()
        hit_kw = [kw for kw in url_blacklist if kw in url_lower]
        if hit_kw:
            blacklist_count += 1
            logger.debug(f"URL命中黑名单：{url[:80]} | 关键词：{','.join(hit_kw)}")
            continue
        
        filtered_urls.append(url)
    
    if blacklist_count > 0:
        logger.info(f"黑名单过滤完成：共过滤 {blacklist_count} 个URL")
    
    return filtered_urls

def sort_and_filter_urls(
    urls: List[str], 
    written_urls: set, 
    latency_results: Dict[str, SpeedTestResult], 
    latency_threshold: float
) -> List[str]:
    """排序和过滤URL（移除黑名单过滤，仅保留延迟/IP版本过滤）"""
    if not urls:
        return []
    
    filtered_urls = []
    
    for url in urls:
        url = url.strip()
        if not url or url in written_urls:
            continue
        
        # 仅保留延迟过滤
        if latency_results:
            result = latency_results.get(url)
            if not result or not result.success or result.latency is None or result.latency > latency_threshold:
                continue
        
        filtered_urls.append(url)
    
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
            
            logger.info(f"成功获取GitHub logo列表，共{len(logo_files)}个文件（来源：{api_url}）")
            break
        except Exception as e:
            logger.warning(f"获取GitHub logo列表失败（{api_url}）：{str(e)[:50]}")
            continue
    
    # 兜底
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
    """生成logo URL（修复超长文件名问题）"""
    if not channel_name:
        return ""
    
    clean_logo_name = clean_channel_name(channel_name)
    
    # 关键修复1：限制文件名长度（最大100个字符）
    MAX_FILENAME_LENGTH = 100
    if len(clean_logo_name) > MAX_FILENAME_LENGTH:
        # 截取前97个字符 + 省略号
        clean_logo_name = clean_logo_name[:MAX_FILENAME_LENGTH-3] + "..."
    
    logo_filename = f"{clean_logo_name}.png"
    
    # 优先使用M3U提取的logo
    for meta in channel_meta_cache.values():
        if meta.clean_channel_name == clean_logo_name and meta.tvg_logo:
            return meta.tvg_logo
    
    # 关键修复2：异常捕获，避免文件系统错误中断程序
    try:
        # 本地logo
        for logo_dir in LOGO_DIRS:
            local_logo_path = logo_dir / logo_filename
            # 增加长度检查，避免系统错误
            if len(str(local_logo_path)) < 255 and local_logo_path.exists():
                return local_logo_path.as_posix()
    except OSError as e:
        logger.debug(f"检查本地logo失败（文件名过长/系统错误）：{logo_filename} | 错误：{str(e)[:30]}")
        # 直接返回GitHub logo，跳过本地检查
        pass
    
    # GitHub logo
    try:
        github_logo_files = get_github_logo_list()
        if logo_filename in github_logo_files:
            return f"{BACKUP_LOGO_BASE_URL}/{logo_filename}"
    except Exception as e:
        logger.debug(f"检查GitHub logo失败：{logo_filename} | 错误：{str(e)[:30]}")
    
    # 特殊匹配
    special_mapping = {
        "TVB翡翠台.png": "翡翠台.png",
        "凤凰卫视中文台.png": ["凤凰中文.png", "凤凰卫视.png"],
        "凤凰卫视资讯台.png": ["凤凰资讯.png", "凤凰卫视.png"],
        "香港卫视综合台.png": ["香港卫视.png"]
    }
    try:
        for target_logo, aliases in special_mapping.items():
            if logo_filename == target_logo:
                for alias in aliases:
                    if alias in github_logo_files:
                        return f"{BACKUP_LOGO_BASE_URL}/{alias}"
    except Exception as e:
        logger.debug(f"特殊匹配logo失败：{logo_filename} | 错误：{str(e)[:30]}")
    
    # 模糊匹配（增加异常保护）
    try:
        candidate_names = [f.replace(".png", "") for f in github_logo_files]
        similar_logo = find_similar_name(clean_logo_name, candidate_names, cutoff=0.5)
        if similar_logo:
            return f"{BACKUP_LOGO_BASE_URL}/{similar_logo}.png"
    except Exception as e:
        logger.debug(f"模糊匹配logo失败：{clean_logo_name} | 错误：{str(e)[:30]}")
    
    return ""

# ===================== 核心修改：完整保留原始M3U元信息 =====================
def generate_basic_m3u(all_channels: OrderedDict):
    """
    抓取完成后立即生成基础M3U文件（100%保留原始M3U元信息，不过滤黑名单）
    :param all_channels: 所有抓取到的频道数据 {group-title: [(频道名, URL), ...]}
    """
    # 基础M3U文件路径
    basic_m3u_path = OUTPUT_FOLDER / "live_basic.m3u"
    basic_txt_path = OUTPUT_FOLDER / "live_basic.txt"
    
    try:
        with open(basic_m3u_path, "w", encoding="utf-8", buffering=1024*1024) as f_m3u, \
             open(basic_txt_path, "w", encoding="utf-8", buffering=1024*1024) as f_txt:
            
            # 写入M3U头部（保留原始EPG配置）
            epg_str = ",".join(f'"{url}"' for url in EPG_URLS) if EPG_URLS else ""
            f_m3u.write(f"#EXTM3U x-tvg-url={epg_str}\n")
            f_m3u.write(f"# 基础版直播源（保留原始/智能提取的元信息，未测速/黑名单筛选）\n")
            f_m3u.write(f"# 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f_m3u.write(f"# 总频道数：{sum(len(ch_list) for _, ch_list in all_channels.items())}\n")
            f_m3u.write(f"# 分类数：{len(all_channels)}\n\n")
            
            # 按原始group-title分类写入所有频道
            total_written = 0
            category_stats = {}
            
            for group_title, channel_list in all_channels.items():
                # 统计分类频道数
                category_stats[group_title] = len(channel_list)
                
                # 写入分类标记
                f_m3u.write(f"# ===== 分类：{group_title}（{len(channel_list)}个频道） =====\n")
                f_txt.write(f"{group_title},#genre#\n")
                
                for _, url in channel_list:
                    if not url or not url.startswith(("http://", "https://")):
                        continue
                    
                    # 获取完整的原始#EXTINF信息
                    meta = channel_meta_cache.get(url)
                    if meta and meta.raw_extinf:
                        # 100%使用原始的#EXTINF行
                        f_m3u.write(meta.raw_extinf + "\n")
                    else:
                        # 对于非M3U格式的URL，生成基础的EXTINF行
                        channel_name = meta.channel_name if (meta and meta.channel_name) else "未知频道"
                        f_m3u.write(
                            f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{channel_name}\" "
                            f"tvg-logo=\"\" group-title=\"{group_title}\",{channel_name}\n"
                        )
                    
                    # 写入播放URL
                    f_m3u.write(url + "\n\n")
                    
                    # 写入TXT文件
                    channel_name = meta.channel_name if (meta and meta.channel_name) else "未知频道"
                    f_txt.write(f"{channel_name},{url}\n")
                    
                    total_written += 1
            
            # 写入统计信息
            f_m3u.write(f"\n# ===== 分类统计 =====\n")
            for cat, count in category_stats.items():
                f_m3u.write(f"# {cat}: {count}个频道\n")
            
            logger.info(f"\n===== 基础M3U文件已生成（保留原始元信息） =====")
            logger.info(f"  - 基础M3U: {basic_m3u_path} (写入{total_written}个频道)")
            logger.info(f"  - 基础TXT: {basic_txt_path}")
            logger.info(f"  - 分类统计：{category_stats}")
            logger.info(f"  - 基础版未过滤黑名单，所有URL均保留\n")
            
    except Exception as e:
        logger.error(f"生成基础M3U文件失败：{str(e)}", exc_info=True)

# ===================== M3U提取函数（完整保留原始元信息） =====================
def extract_m3u_meta(content: str, source_url: str) -> Tuple[OrderedDict, List[ChannelMeta]]:
    """
    提取M3U元信息（完整保留原始#EXTINF行）
    :return: (按原始group-title分类的频道字典, 完整的ChannelMeta列表)
    """
    # 匹配完整的M3U条目：#EXTINF行 + URL
    m3u_pattern = re.compile(
        r"(#EXTINF:-?\d+.*?)\n\s*([^#\n\r\s].*?)(?=\s|#|$)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE
    )
    
    # 匹配#EXTINF中的属性
    attr_pattern = re.compile(r'(\w+)-(\w+)="([^"]*)"')
    
    categorized_channels = OrderedDict()
    meta_list = []
    seen_urls = set()
    
    matches = m3u_pattern.findall(content)
    
    for raw_extinf, url in matches:
        url = url.strip()
        raw_extinf = raw_extinf.strip()
        
        # 跳过无效URL或重复URL
        if not url or not url.startswith(("http://", "https://")) or url in seen_urls:
            continue
        
        seen_urls.add(url)
        url_source_mapping[url] = source_url
        
        # 解析#EXTINF属性
        tvg_id = None
        tvg_name = None
        tvg_logo = None
        group_title = None
        channel_name = "未知频道"
        
        # 提取所有属性
        attr_matches = attr_pattern.findall(raw_extinf)
        for attr1, attr2, value in attr_matches:
            if attr1 == "tvg" and attr2 == "id":
                tvg_id = value
            elif attr1 == "tvg" and attr2 == "name":
                tvg_name = value
            elif attr1 == "tvg" and attr2 == "logo":
                tvg_logo = value
            elif attr1 == "group" and attr2 == "title":
                group_title = value
        
        # 提取逗号后的频道名
        name_match = re.search(r',\s*(.+?)\s*$', raw_extinf)
        if name_match:
            channel_name = name_match.group(1).strip()
        
        # 使用原始group-title，无则设为"未分类"
        group_title = group_title if group_title else "未分类"
        
        # 创建完整的元信息对象
        meta = ChannelMeta(
            url=url,
            raw_extinf=raw_extinf,  # 保存完整的原始#EXTINF行
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
        raw_extinf_mapping[url] = raw_extinf
        
        # 添加到分类字典
        if group_title not in categorized_channels:
            categorized_channels[group_title] = []
        categorized_channels[group_title].append((channel_name, url))
    
    logger.info(f"M3U精准提取：{len(meta_list)}个频道（保留原始元信息）")
    logger.info(f"识别的M3U分类：{list(categorized_channels.keys())}")
    
    return categorized_channels, meta_list

# ===================== 频道提取函数（增强格式兼容） =====================
def extract_channels_from_content(content: str, source_url: str) -> OrderedDict:
    """
    提取频道和URL（增强格式兼容，智能识别分类和元信息）
    :return: 按原始group-title分类的频道字典
    """
    categorized_channels = OrderedDict()
    seen_urls = set()
    
    # 优先处理M3U格式（完整保留元信息）
    if "#EXTM3U" in content:
        m3u_categorized, _ = extract_m3u_meta(content, source_url)
        categorized_channels = m3u_categorized
        # 更新已见URL
        for _, ch_list in m3u_categorized.items():
            for _, url in ch_list:
                seen_urls.add(url)
    else:
        # 增强：从普通文本中提取更多元信息
        lines = content.split('\n')
        current_group = "默认分类"
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith(("//", "#", "/*", "*/")):
                # 识别分类行（支持多种格式）
                if any(keyword in line.lower() for keyword in ['#分类', '#genre', '分类:', 'genre:', '==', '---']):
                    # 提取分类名称
                    group_match = re.search(r'[：:=](\S+)', line)
                    if group_match:
                        current_group = group_match.group(1).strip()
                    else:
                        current_group = re.sub(r'[#分类:genre:==\-—]', '', line).strip() or "默认分类"
                    # 清理特殊字符
                    current_group = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9_()]', '', current_group)
                    logger.debug(f"识别到分类：{current_group}")
                    # 初始化分类
                    if current_group not in categorized_channels:
                        categorized_channels[current_group] = []
                continue
            
            # 匹配频道名,URL格式（增强正则，支持多种分隔符）
            pattern = r'([^,|#$]+)[,|#$]\s*(https?://[^\s,|#$]+)'
            matches = re.findall(pattern, line, re.IGNORECASE)
            if matches:
                for name, url in matches:
                    name = name.strip()
                    url = url.strip()
                    if not url or url in seen_urls:
                        continue
                    
                    seen_urls.add(url)
                    
                    # 智能分类推断
                    group_title = current_group
                    # 根据频道名智能分类
                    if any(keyword in name for keyword in ['CCTV', '央视', '中央']):
                        group_title = "央视频道"
                    elif any(keyword in name for keyword in ['卫视', '江苏', '浙江', '湖南', '东方', '北京', '安徽', '山东', '广东']):
                        group_title = "卫视频道"
                    elif any(keyword in name for keyword in ['电影', '影视', '影院']):
                        group_title = "电影频道"
                    elif any(keyword in name for keyword in ['体育', 'CCTV5', '赛事']):
                        group_title = "体育频道"
                    elif any(keyword in name for keyword in ['少儿', '卡通', '动画', '优漫']):
                        group_title = "少儿频道"
                    elif any(keyword in name for keyword in ['新闻', '资讯']):
                        group_title = "新闻频道"
                    elif any(keyword in name for keyword in ['本地', '市', '县', '省']):
                        group_title = "地方频道"
                    
                    # 生成更丰富的元信息
                    tvg_name = name
                    # 提取数字作为tvg-id
                    tvg_id = re.sub(r'\D', '', name) if re.search(r'\d', name) else ""
                    # 自动匹配logo（增加异常保护）
                    try:
                        tvg_logo = get_channel_logo_url(name)
                    except Exception as e:
                        logger.debug(f"生成logo URL失败（频道：{name[:50]}）：{str(e)[:30]}")
                        tvg_logo = ""
                    
                    raw_extinf = f"#EXTINF:-1 tvg-id=\"{tvg_id}\" tvg-name=\"{tvg_name}\" tvg-logo=\"{tvg_logo}\" group-title=\"{group_title}\",{name}"
                    
                    meta = ChannelMeta(
                        url=url,
                        raw_extinf=raw_extinf,
                        tvg_id=tvg_id,
                        tvg_name=tvg_name,
                        tvg_logo=tvg_logo,
                        group_title=group_title,
                        channel_name=name,
                        clean_channel_name=clean_channel_name(name),
                        source_url=source_url
                    )
                    
                    channel_meta_cache[url] = meta
                    raw_extinf_mapping[url] = raw_extinf
                    
                    # 确保分类存在
                    if group_title not in categorized_channels:
                        categorized_channels[group_title] = []
                    categorized_channels[group_title].append((name, url))
        
        # 处理剩余的单独URL
        pattern3 = r'(https?://[^\s]+)'
        matches3 = re.findall(pattern3, content, re.IGNORECASE | re.MULTILINE)
        for url in matches3:
            url = url.strip()
            if not url or url in seen_urls:
                continue
            
            seen_urls.add(url)
            
            # 从URL中提取频道名
            channel_name = "未知频道"
            url_parts = url.split('/')
            for part in url_parts:
                if part and len(part) > 3 and not part.startswith(('http', 'www', 'live', 'stream', 'cdn', 'api')):
                    channel_name = part
                    break
            
            # 智能分类
            group_title = "其他频道"
            if any(keyword in channel_name for keyword in ['CCTV', '央视']):
                group_title = "央视频道"
            elif any(keyword in channel_name for keyword in ['卫视']):
                group_title = "卫视频道"
            
            raw_extinf = f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{channel_name}\" tvg-logo=\"\" group-title=\"{group_title}\",{channel_name}"
            
            meta = ChannelMeta(
                url=url,
                raw_extinf=raw_extinf,
                tvg_id="",
                tvg_name=channel_name,
                tvg_logo="",
                group_title=group_title,
                channel_name=channel_name,
                clean_channel_name=clean_channel_name(channel_name),
                source_url=source_url
            )
            
            channel_meta_cache[url] = meta
            raw_extinf_mapping[url] = raw_extinf
            
            # 添加到分类字典
            if group_title not in categorized_channels:
                categorized_channels[group_title] = []
            categorized_channels[group_title].append((channel_name, url))
    
    # 确保至少有一个分类
    if not categorized_channels:
        categorized_channels["未分类频道"] = []
    
    logger.info(f"从内容中提取到 {sum(len(v) for v in categorized_channels.values())} 个有效频道")
    logger.info(f"智能识别的分类：{list(categorized_channels.keys())}")
    return categorized_channels

# ===================== 链接处理函数（自动修复GitHub URL） =====================
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
    
    proxy_urls = []
    for base_url in candidate_urls:
        for proxy in PROXY_PREFIXES:
            if not base_url.startswith(proxy):
                proxy_url = proxy + base_url
                if proxy_url not in proxy_urls:
                    proxy_urls.append(proxy_url)
    
    candidate_urls.extend(proxy_urls)
    unique_urls = list(dict.fromkeys(candidate_urls))
    
    return unique_urls[:5]

def fetch_url_with_retry(url: str, timeout: int = 15) -> Optional[str]:
    """带重试的URL抓取（自动修复GitHub URL）"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # 自动修复GitHub blob URL
    original_url = url
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        logger.info(f"自动修复GitHub URL：{original_url} → {url}")
    
    candidate_urls = replace_github_domain(url)
    
    # 分级超时
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
    
    logger.error(f"所有候选链接都抓取失败：{original_url}")
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
                f"测速进度：{self.processed_count}/{self.total_count} "
                f"({self.processed_count/self.total_count*100:.1f}%) | "
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
                await asyncio.sleep(0.5)
        
        # 更新进度
        self._update_progress()
        
        if not result.success:
            logger.debug(f"最终失败 {url[:60]} | 原因: {result.error}")
        
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
        
        logger.info(f"开始批量测速：共{self.total_count}个URL | 并发数：{self.concurrent_limit} | 超时：{self.timeout}s")
        
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
            f"测速完成：成功{success_count}/{self.total_count} "
            f"({success_count/self.total_count*100:.1f}%) | "
            f"平均延迟：{avg_latency:.2f}ms | 总耗时：{elapsed:.1f}s"
        )
        
        return results

# ===================== 模板解析与匹配 =====================
def parse_template(template_file: str) -> OrderedDict:
    """解析模板文件"""
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
    """抓取频道（完整保留原始M3U元信息）"""
    channels = OrderedDict()
    
    try:
        content = fetch_url_with_retry(url)
        if content is None:
            return channels
        
        # 提取频道（保留原始元信息）
        categorized_channels = extract_channels_from_content(content, url)
        channels = categorized_channels
            
    except Exception as e:
        logger.error(f"处理 {url} 时发生异常：{str(e)}", exc_info=True)

    return channels

def merge_channels(target: OrderedDict, source: OrderedDict):
    """合并频道（保留原始分类和元信息）"""
    url_set = set()
    
    # 第一步：收集已有的URL，避免重复
    for category_name, ch_list in target.items():
        for _, url in ch_list:
            url_set.add(url)
    
    # 第二步：合并源数据（保留原始分类）
    for category_name, channel_list in source.items():
        if category_name not in target:
            target[category_name] = []
        
        # 只添加新的URL
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
                logger.debug(f"匹配成功：{channel_name} → {matched_name}")
            else:
                unmatched_channels.append(channel_name)
                logger.warning(f"未匹配到频道：{channel_name}")
    
    # 统计
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
    """过滤源URL"""
    template_channels = parse_template(template_file)
    if not template_channels:
        logger.error("模板解析为空，终止流程")
        return OrderedDict(), OrderedDict()
    
    if not SOURCE_URLS:
        logger.error("未配置source_urls/SOURCE_URLS，终止流程")
        return OrderedDict(), template_channels
    
    all_channels = OrderedDict()
    failed_urls = []
    total_extracted = 0
    
    for url in SOURCE_URLS:
        logger.info(f"\n开始抓取源：{url}")
        fetched_channels = fetch_channels(url)
        
        # 计算抓取到的频道数
        fetched_count = sum(len(ch_list) for _, ch_list in fetched_channels.items())
        
        if fetched_count == 0:
            failed_urls.append(url)
            logger.warning(f"源 {url} 未抓取到任何频道")
            continue
        
        merge_channels(all_channels, fetched_channels)
        total_extracted += fetched_count
        logger.info(f"源 {url} 抓取完成，新增频道数：{fetched_count}")
        logger.info(f"  - 识别分类数：{len(fetched_channels)}")
        logger.info(f"  - 识别分类列表：{list(fetched_channels.keys())}")
    
    # 统计
    total_channels = sum(len(ch_list) for _, ch_list in all_channels.items())
    logger.info(f"\n抓取统计：")
    logger.info(f"  - 总源数：{len(SOURCE_URLS)}")
    logger.info(f"  - 失败源数：{len(failed_urls)}")
    logger.info(f"  - 原始提取频道数：{total_extracted}")
    logger.info(f"  - 去重后频道总数：{total_channels}")
    logger.info(f"  - 最终分类数：{len(all_channels)}")
    logger.info(f"  - 最终分类列表：{list(all_channels.keys())}")
    
    if failed_urls:
        logger.info(f"  - 失败的源：{', '.join(failed_urls)}")
    
    # 生成基础M3U文件（100%保留原始元信息，不过滤黑名单）
    generate_basic_m3u(all_channels)
    
    # 匹配频道
    matched_channels = match_channels(template_channels, all_channels)
    
    return matched_channels, template_channels

# ===================== 文件生成 =====================
def write_to_files(f_m3u, f_txt, category, channel_name, index, url, ip_version, latency):
    """写入文件（优化版）"""
    if not url:
        return
    
    try:
        meta = channel_meta_cache.get(url)
        logo_url = meta.tvg_logo if (meta and meta.tvg_logo) else get_channel_logo_url(channel_name)
        tvg_id = meta.tvg_id if (meta and meta.tvg_id) else str(index)
        tvg_name = meta.tvg_name if (meta and meta.tvg_name) else channel_name
        group_title = meta.group_title if (meta and meta.group_title) else category
        
        # 写入M3U
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
    """更新频道URL到文件（优化版，新增黑名单过滤）"""
    written_urls_ipv4 = set()
    written_urls_ipv6 = set()

    # 文件路径
    ipv4_m3u_path = OUTPUT_FOLDER / "live_ipv4.m3u"
    ipv4_txt_path = OUTPUT_FOLDER / "live_ipv4.txt"
    ipv6_m3u_path = OUTPUT_FOLDER / "live_ipv6.m3u"
    ipv6_txt_path = OUTPUT_FOLDER / "live_ipv6.txt"

    try:
        # 大缓冲区写入
        with open(ipv4_m3u_path, "w", encoding="utf-8", buffering=1024*1024) as f_m3u_ipv4, \
             open(ipv4_txt_path, "w", encoding="utf-8", buffering=1024*1024) as f_txt_ipv4, \
             open(ipv6_m3u_path, "w", encoding="utf-8", buffering=1024*1024) as f_m3u_ipv6, \
             open(ipv6_txt_path, "w", encoding="utf-8", buffering=1024*1024) as f_txt_ipv6:

            # 写入头部
            epg_str = ",".join(f'"{url}"' for url in EPG_URLS) if EPG_URLS else ""
            header_note = f"# 延迟阈值：{LATENCY_THRESHOLD}ms | 黑名单关键词：{URL_BLACKLIST} | 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            f_m3u_ipv4.write(f"#EXTM3U x-tvg-url={epg_str}\n{header_note}")
            f_m3u_ipv6.write(f"#EXTM3U x-tvg-url={epg_str}\n{header_note}")

            # 写入公告频道
            announcement_id = 1
            for group in ANNOUNCEMENTS:
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
                    
                    # 先过滤黑名单
                    entry_url_filtered = filter_blacklist_urls([entry_url])
                    if not entry_url_filtered:
                        continue
                    
                    entry_result = latency_results.get(entry_url)
                    if entry_result and entry_result.success and entry_result.latency and entry_result.latency <= LATENCY_THRESHOLD:
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
                    
                    # 第一步：过滤黑名单（核心修改）
                    urls_after_blacklist = filter_blacklist_urls(raw_urls)
                    
                    # 第二步：分离IPv4/IPv6并过滤延迟
                    ipv4_urls = sort_and_filter_urls(
                        [u for u in urls_after_blacklist if not is_ipv6(u)],
                        written_urls_ipv4,
                        latency_results,
                        LATENCY_THRESHOLD
                    )
                    ipv6_urls = sort_and_filter_urls(
                        [u for u in urls_after_blacklist if is_ipv6(u)],
                        written_urls_ipv6,
                        latency_results,
                        LATENCY_THRESHOLD
                    )
                    
                    # 写入IPv4
                    total_ipv4 = len(ipv4_urls)
                    for idx, url in enumerate(ipv4_urls, start=1):
                        latency = latency_results[url].latency
                        new_url = add_url_suffix(url, idx, total_ipv4, "IPV4", latency)
                        write_to_files(f_m3u_ipv4, f_txt_ipv4, category, channel_name, idx, new_url, "IPV4", latency)
                        ipv4_written += 1
                    
                    # 写入IPv6
                    total_ipv6 = len(ipv6_urls)
                    for idx, url in enumerate(ipv6_urls, start=1):
                        latency = latency_results[url].latency
                        new_url = add_url_suffix(url, idx, total_ipv6, "IPV6", latency)
                        write_to_files(f_m3u_ipv6, f_txt_ipv6, category, channel_name, idx, new_url, "IPV6", latency)
                        ipv6_written += 1

            # 生成报告
            generate_speed_report(latency_results, LATENCY_THRESHOLD)
            
            logger.info(f"\n===== 最终优化版文件生成完成 =====")
            logger.info(f"  - IPv4 M3U: {ipv4_m3u_path} (写入{ipv4_written}个URL)")
            logger.info(f"  - IPv4 TXT: {ipv4_txt_path}")
            logger.info(f"  - IPv6 M3U: {ipv6_m3u_path} (写入{ipv6_written}个URL)")
            logger.info(f"  - IPv6 TXT: {ipv6_txt_path}")
            logger.info(f"  - 延迟阈值：{LATENCY_THRESHOLD}ms")
            logger.info(f"  - 已应用URL黑名单过滤\n")
            
    except Exception as e:
        logger.error(f"生成文件失败：{str(e)}", exc_info=True)

def generate_speed_report(latency_results: Dict[str, SpeedTestResult], latency_threshold: float):
    """生成测速报告"""
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
            f.write(f"延迟阈值：{latency_threshold}ms | 并发数：{CONCURRENT_LIMIT}\n")
            f.write(f"URL黑名单：{URL_BLACKLIST}\n")
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
                for idx, result in enumerate(failed_urls[:50], 1):
                    f.write(f"{idx:<4} {result.error:<15} {result.url[:100]}\n")
                if len(failed_urls) > 50:
                    f.write(f"... 共{len(failed_urls)}个失败URL，仅显示前50个\n")
            else:
                f.write("\n【失败URL列表】\n")
                f.write("无失败URL\n")
        
        logger.info(f"  - 测速报告：{report_path}")
    except Exception as e:
        logger.error(f"生成测速报告失败：{str(e)}", exc_info=True)

# ===================== 主程序 =====================
async def main():
    """主函数"""
    start_total = time.time()
    try:
        # 清空缓存
        global channel_meta_cache, raw_extinf_mapping, url_source_mapping
        channel_meta_cache = {}
        raw_extinf_mapping = {}
        url_source_mapping = {}
        
        logger.info("===== 开始处理直播源（智能提取元信息版本） =====")
        logger.info(f"配置信息：延迟阈值{LATENCY_THRESHOLD}ms | 匹配阈值{MATCH_CUTOFF} | URL黑名单：{URL_BLACKLIST}")
        
        # 预加载logo
        get_github_logo_list()
        
        # 抓取匹配频道
        logger.info("\n===== 1. 抓取并提取直播源频道（智能识别分类） =====")
        channels, template_channels = filter_source_urls(TEMPLATE_FILE)
        if not channels:
            logger.error("无匹配的频道数据，终止流程")
            return
        
        # 收集URL（去重）
        all_urls = set()
        for category in channels.values():
            for urls in category.values():
                all_urls.update(urls)
        for group in ANNOUNCEMENTS:
            for entry in group.get('entries', []):
                url = entry.get('url', '')
                if url:
                    all_urls.add(url)
        
        all_urls = list(all_urls)
        logger.info(f"\n===== 2. 开始批量测速（共{len(all_urls)}个URL） =====")
        
        # 测速
        async with SpeedTester() as tester:
            latency_results = await tester.batch_speed_test(all_urls)
        
        # 生成最终优化版文件
        logger.info("\n===== 3. 生成最终优化版文件（含黑名单过滤） =====")
        updateChannelUrlsM3U(channels, template_channels, latency_results)
        
        # 统计耗时
        total_elapsed = time.time() - start_total
        logger.info(f"\n===== 所有流程执行完成 | 总耗时：{total_elapsed:.1f}s =====")
        logger.info(f"\n文件说明：")
        logger.info(f"  - live_basic.m3u: 基础版（保留原始/智能提取的元信息，未测速/黑名单筛选）")
        logger.info(f"  - live_ipv4.m3u/live_ipv6.m3u: 优化版（黑名单过滤+测速筛选+IP分类）")
        logger.info(f"  - speed_test_report.txt: 详细测速报告（含黑名单信息）")
    
    except Exception as e:
        logger.critical(f"程序执行异常：{str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    # 兼容Windows
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 运行
    asyncio.run(main())
