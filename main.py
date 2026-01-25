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
    group_title: Optional[str] = None  # 【修改1】移除默认值，保留原始分类（可为None）
    tvg_name: str = ""  # TVG名称
    tvg_id: str = ""  # TVG ID
    tvg_logo: str = ""  # 【新增】台标URL
    other_attrs: Dict[str, str] = None  # 其他属性
    latency: float = 9999.0  # 新增：存储测速延迟，默认9999ms

    def __post_init__(self):
        if self.other_attrs is None:
            self.other_attrs = {}
        # 【修改2】确保group_title为字符串（None转为空字符串）
        self.group_title = self.group_title if self.group_title is not None else ""
        # 【新增】自动生成台标URL（如果未指定）
        if not self.tvg_logo and self.name and hasattr(config, 'logo_url') and config.logo_url:
            logo_type = getattr(config, 'logo_type', 'png')
            # 清理频道名用于台标文件名
            clean_logo_name = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]', '', self.name)
            self.tvg_logo = f"{config.logo_url.rstrip('/')}/{clean_logo_name}.{logo_type}"

# ===================== 初始化配置 =====================
# 确保 output 文件夹存在
OUTPUT_FOLDER = Path("output")
OUTPUT_FOLDER.mkdir(exist_ok=True)

# 标准化M3U文件路径（核心新增）
STANDARD_M3U_PATH = OUTPUT_FOLDER / "live_standard.m3u"

# 测速配置（放宽门槛，保留更多URL）
CONFIG_DEFAULTS = {
    "LATENCY_THRESHOLD": 1000,  # 延迟阈值从500ms→1000ms
    "CONCURRENT_LIMIT": 20,
    "TIMEOUT": 20,               # 超时从15s→20s
    "RETRY_TIMES": 2,            # 重试次数降为2，节省时间
    "IP_VERSION_PRIORITY": "ipv4",
    "URL_BLACKLIST": [],
    "TEMPLATE_FILE": "demo.txt",
    "EPG_URLS": [],
    "ANNOUNCEMENTS": [],
    "SOURCE_URLS": []
}

# 支持的播放协议（扩展）
SUPPORTED_PROTOCOLS = [
    "http://", "https://", "rtmp://", "rtsp://", "udp://", "tcp://",
    "mms://", "hls://", "dash://", "rtp://", "srt://"
]

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

# 【新增函数】生成台标URL
def generate_logo_url(channel_name: str) -> str:
    """根据频道名生成标准化的台标URL"""
    if not channel_name or not hasattr(config, 'logo_url') or not config.logo_url:
        return ""
    
    logo_type = getattr(config, 'logo_type', 'png')
    # 清理频道名（移除特殊字符，用于文件名）
    clean_name = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]', '', channel_name).strip()
    if not clean_name:
        return ""
    
    # 拼接台标URL
    logo_base = config.logo_url.rstrip('/')
    return f"{logo_base}/{clean_name}.{logo_type}"

# 【新增函数】清洗分类名称（仅移除非法字符，保留原始语义）
def clean_group_title(raw_group: str) -> str:
    """
    轻量清洗分类名称，保留原始语义
    - 移除不可见字符和极端特殊字符
    - 保留空格、中英文符号等原始分类特征
    """
    if not raw_group:
        return ""
    # 仅移除控制字符和非法文件名字符
    cleaned = re.sub(r'[\x00-\x1f\x7f<>:"|?*\\/]', '', raw_group.strip())
    # 连续空格转为单个
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned

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
    """自动转换GitHub URL格式：blob/main → raw.githubusercontent.com"""
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

# ========== 核心新增：生成标准化M3U文件（去重+规范格式） ==========
def generate_standard_m3u(channels: List[ChannelInfo], output_path: Path) -> List[str]:
    """
    生成标准化M3U文件（核心新增）
    - 深度去重：移除URL中的随机参数，保证同链接不同参数也能去重
    - 规范格式：严格遵循M3U行业标准
    - 有序整理：按分类+频道名排序
    - 【修改3】保留原始group_title，空分类显示为"未分类"
    - 【新增】添加tvg-logo属性
    返回：去重后的URL列表（用于后续测速）
    """
    # 第一步：深度去重（按URL去重，保留第一个出现的频道信息）
    unique_channels = {}
    for channel in channels:
        # 统一URL格式（移除参数中的随机值，增强去重效果）
        url = channel.url.strip()
        # 移除URL中常见的随机参数（token/expires/timestamp等）
        url = re.sub(r'(&|\?)?[a-zA-Z0-9]+=[a-zA-Z0-9]+', '', url)
        url = re.sub(r'(&|\?)?token=[^&]+', '', url)
        url = re.sub(r'(&|\?)?expires=[^&]+', '', url)
        url = re.sub(r'(&|\?)?t=\d+', '', url)
        
        if url not in unique_channels:
            unique_channels[url] = channel
    
    # 转换为有序列表（按分类+名称排序，空分类排最后）
    sorted_channels = sorted(
        unique_channels.values(),
        key=lambda x: (x.group_title if x.group_title else "zzz未分类", x.name)
    )
    
    # 第二步：生成标准M3U格式文件
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            # M3U文件头（标准格式）
            epg_urls = getattr(config, 'epg_urls', [])
            epg_str = ",".join(epg_urls) if epg_urls else ""
            f.write(f"#EXTM3U x-tvg-url=\"{epg_str}\"\n")
            f.write(f"# 标准化M3U文件 - 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 总频道数：{len(sorted_channels)}（已去重）\n\n")
            
            # 按分类分组写入
            current_group = ""
            for channel in sorted_channels:
                # 获取显示用的分类名（空分类显示为"未分类"）
                display_group = channel.group_title if channel.group_title else "未分类"
                
                # 分类分隔符
                if display_group != current_group:
                    current_group = display_group
                    f.write(f"\n# 分类：{current_group}\n")
                
                # 标准EXTINF行
                extinf_parts = [f"#EXTINF:-1"]
                if channel.tvg_name:
                    extinf_parts.append(f'tvg-name="{channel.tvg_name}"')
                if channel.tvg_id:
                    extinf_parts.append(f'tvg-id="{channel.tvg_id}"')
                # 【新增】添加tvg-logo属性
                if channel.tvg_logo:
                    extinf_parts.append(f'tvg-logo="{channel.tvg_logo}"')
                # 【修改4】写入原始group_title（空值则不写）
                if channel.group_title:
                    extinf_parts.append(f'group-title="{channel.group_title}"')
                
                extinf_line = ' '.join(extinf_parts) + f',{channel.name}'
                f.write(f"{extinf_line}\n")
                f.write(f"{channel.url}\n")
        
        logger.info(f"✅ 标准化M3U文件已生成：{output_path}")
        logger.info(f"✅ 去重后总频道数：{len(sorted_channels)}（原始：{len(channels)}）")
        
        # 返回去重后的URL列表（用于后续测速）
        return [channel.url for channel in sorted_channels]
    
    except Exception as e:
        logger.error(f"生成标准化M3U文件失败：{str(e)}")
        # 降级返回原始URL（去重）
        return list(unique_channels.keys())

def extract_channels_from_content(content: str) -> List[ChannelInfo]:
    """
    优化：减少过度去重，仅按URL去重（保留更多URL）
    从直播源内容中提取频道信息，优先解析M3U标准字段
    【修改5】完全保留原始group-title，不使用默认分类
    【新增】解析tvg-logo属性并自动生成台标URL
    """
    channels = []
    # 仅按URL去重（放宽去重条件）
    seen_urls = set()
    
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
        if line.startswith(tuple(SUPPORTED_PROTOCOLS)) and current_attrs:
            url = line.strip()
            
            # 新增：绕过简单防盗链
            if "migu" in url or "iptv" in url or "live" in url:
                if "?" in url:
                    url += "&referer=https://www.iptv.com"
                else:
                    url += "?referer=https://www.iptv.com"
            
            # 去重检查（仅按URL）
            if url in seen_urls:
                current_attrs = {}
                continue
            seen_urls.add(url)
            
            # 提取关键属性 - 【修改6】保留原始group-title，不兜底
            tvg_name = current_attrs.get('tvg-name', '')
            # 提取原始group-title并轻量清洗
            raw_group = current_attrs.get('group-title', current_attrs.get('group', ''))
            group_title = clean_group_title(raw_group)
            tvg_id = current_attrs.get('tvg-id', '')
            # 【新增】提取tvg-logo属性
            tvg_logo = current_attrs.get('tvg-logo', '')
            channel_name = current_attrs.get('_channel_name', tvg_name or '未知频道')
            
            # 清洗频道名
            cleaned_name = clean_channel_name(channel_name)
            if not cleaned_name:
                cleaned_name = clean_channel_name(tvg_name) or '未知频道'
            
            # 【新增】如果没有解析到tvg-logo，自动生成
            if not tvg_logo:
                tvg_logo = generate_logo_url(cleaned_name)
            
            # 创建频道信息对象
            channel_info = ChannelInfo(
                name=cleaned_name,
                url=url,
                group_title=group_title,  # 【修改7】传入原始清洗后的分类，无默认值
                tvg_name=tvg_name,
                tvg_id=tvg_id,
                tvg_logo=tvg_logo,  # 【新增】传入台标URL
                other_attrs={k: v for k, v in current_attrs.items() if k not in ['tvg-name', 'group-title', 'tvg-id', 'tvg-logo', '_channel_name']}
            )
            channels.append(channel_info)
            
            # 重置当前属性
            current_attrs = {}
            continue
        
        # 3. 兼容旧格式（频道名,URL）
        if ',' in line and not line.startswith('#'):
            parts = line.split(',', 1)
            if len(parts) == 2 and parts[1].strip().startswith(tuple(SUPPORTED_PROTOCOLS)):
                name_part = parts[0].strip()
                url_part = parts[1].strip()
                
                # 新增：绕过简单防盗链
                if "migu" in url_part or "iptv" in url_part or "live" in url_part:
                    if "?" in url_part:
                        url_part += "&referer=https://www.iptv.com"
                    else:
                        url_part += "?referer=https://www.iptv.com"
                
                # 去重检查（仅按URL）
                if url_part in seen_urls:
                    continue
                seen_urls.add(url_part)
                
                cleaned_name = clean_channel_name(name_part) or '未知频道'
                
                # 【新增】生成台标URL
                tvg_logo = generate_logo_url(cleaned_name)
                
                # 创建兼容模式的频道信息 - 【修改8】旧格式group_title为空字符串
                channel_info = ChannelInfo(
                    name=cleaned_name,
                    url=url_part,
                    group_title="",  # 无分类信息，设为空字符串
                    tvg_logo=tvg_logo  # 【新增】台标URL
                )
                channels.append(channel_info)
                continue
        
        # 4. 单独的URL（无属性）
        if line.startswith(tuple(SUPPORTED_PROTOCOLS)) and not current_attrs:
            url = line.strip()
            
            # 新增：绕过简单防盗链
            if "migu" in url or "iptv" in url or "live" in url:
                if "?" in url:
                    url += "&referer=https://www.iptv.com"
                else:
                    url += "?referer=https://www.iptv.com"
            
            # 去重检查（仅按URL）
            if url in seen_urls:
                continue
            seen_urls.add(url)
            
            # 从URL提取简易名称
            url_parts = url.split('/')
            name_from_url = '未知频道'
            for part in url_parts:
                if part and not part.startswith(('http', 'www', 'live', 'stream')) and len(part) > 2:
                    name_from_url = clean_channel_name(part)
                    break
            
            # 【新增】生成台标URL
            tvg_logo = generate_logo_url(name_from_url)
            
            # 【修改9】单独URL的group_title为空字符串
            channel_info = ChannelInfo(
                name=name_from_url,
                url=url,
                group_title="",
                tvg_logo=tvg_logo  # 【新增】台标URL
            )
            channels.append(channel_info)
    
    logger.info(f"从内容中提取到 {len(channels)} 个有效频道（仅按URL去重）")
    return channels

def filter_invalid_urls(urls: List[str]) -> List[str]:
    """提前过滤明显无效的URL（仅过滤极端情况）"""
    valid = []
    for url in urls:
        url = url.strip()
        if not url.startswith(tuple(SUPPORTED_PROTOCOLS)):
            continue
        # 仅排除明显的测试/占位链接
        if any(k in url.lower() for k in ['placeholder', 'test', 'null', 'example', '127.0.0.1', 'localhost']):
            continue
        valid.append(url)
    logger.info(f"URL过滤前{len(urls)}个，过滤后{len(valid)}个（仅过滤极端无效URL）")
    return valid

def sort_and_filter_urls(
    channel_infos: List[ChannelInfo], 
    written_urls: set, 
    latency_results: Dict[str, SpeedTestResult], 
    latency_threshold: float
) -> List[ChannelInfo]:
    """
    优化：保留所有URL（即使测速失败），仅做排序
    不再过滤失败/超时/超阈值的URL
    """
    if not channel_infos:
        return []
    
    filtered_channels = []
    url_blacklist = getattr(config, 'url_blacklist', [])
    
    for channel in channel_infos:
        url = channel.url.strip()
        if not url or url in written_urls:
            continue
        
        # 仅过滤黑名单URL
        if any(blacklist in url for blacklist in url_blacklist):
            continue
        
        # 保留所有URL，不管测速结果如何
        result = latency_results.get(url)
        if result and result.success and result.latency is not None:
            channel.latency = result.latency
        else:
            channel.latency = 9999.0  # 失败URL标为9999ms
        
        filtered_channels.append(channel)
    
    # 按IP版本优先级排序
    ip_priority = getattr(config, 'ip_version_priority', CONFIG_DEFAULTS["IP_VERSION_PRIORITY"])
    if ip_priority == "ipv6":
        filtered_channels.sort(key=lambda c: is_ipv6(c.url), reverse=True)
    else:
        filtered_channels.sort(key=lambda c: is_ipv6(c.url))
    
    # 按延迟升序排序（失败URL排最后）
    filtered_channels.sort(key=lambda c: c.latency)
    
    # 更新已写入URL集合
    written_urls.update([c.url for c in filtered_channels])
    
    return filtered_channels

def add_url_suffix(url: str, index: int, total_urls: int, ip_version: str, latency: float) -> str:
    """添加URL后缀，区分IP版本、线路和延迟（失败URL标注失败）"""
    if not url:
        return ""
    base_url = url.split('$', 1)[0] if '$' in url else url
    ip_version = ip_version.lower()
    
    if latency >= 9999.0:
        latency_str = "失败"
    else:
        latency_str = f"{latency:.0f}ms"
    
    if total_urls == 1:
        suffix = f"${ip_version}({latency_str})"
    else:
        suffix = f"${ip_version}•线路{index}({latency_str})"
    
    return f"{base_url}{suffix}"

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

def fetch_url_with_retry(url: str, timeout: int = 20) -> Optional[str]:
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
            
            # 兼容SSL验证配置
            verify = os.environ.get('REQUESTS_VERIFY_SSL', 'False').lower() == 'true'
            response = session.get(
                candidate,
                headers=headers,
                timeout=timeout,
                verify=verify,  # 从环境变量控制
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

# ===================== 测速模块（核心优化：解析m3u8子链接） =====================
class SpeedTester:
    """异步测速器（新增m3u8子链接解析）"""
    def __init__(self):
        self.session = None
        self.concurrent_limit = getattr(config, 'CONCURRENT_LIMIT', CONFIG_DEFAULTS["CONCURRENT_LIMIT"])
        self.timeout = getattr(config, 'TIMEOUT', CONFIG_DEFAULTS["TIMEOUT"])
        self.retry_times = getattr(config, 'RETRY_TIMES', CONFIG_DEFAULTS["RETRY_TIMES"])
    
    async def __aenter__(self):
        """创建异步HTTP会话"""
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.iptv.com"  # 新增：添加referer绕过防盗链
        }
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭异步HTTP会话"""
        if self.session:
            await self.session.close()
    
    async def measure_m3u8_sub_url(self, url: str) -> Optional[SpeedTestResult]:
        """解析m3u8索引文件，获取真实播放链接并测速"""
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    return None
                
                content = await response.content.read(2048)
                # 提取m3u8里的真实播放链接
                sub_urls = re.findall(rb"{}[^\s#]+".format(b'|'.join([proto.encode() for proto in SUPPORTED_PROTOCOLS])), content)
                if not sub_urls:
                    return None
                
                # 取第一个子链接测速
                sub_url = sub_urls[0].decode()
                logger.info(f"解析到m3u8子链接：{sub_url[:60]} (来源：{url[:60]})")
                return await self.measure_latency(sub_url)
        except Exception as e:
            logger.debug(f"解析m3u8子链接失败：{str(e)[:50]}")
            return None
    
    async def measure_latency(self, url: str) -> SpeedTestResult:
        """测量单个URL的延迟和分辨率（新增m3u8子链接解析）"""
        result = SpeedTestResult(url=url)
        
        # 非HTTP协议跳过测速（标记为成功，避免归为失败）
        if not url.startswith(('http://', 'https://')):
            result.success = True
            result.error = "非HTTP协议，无需测速"
            result.latency = 0.0
            logger.debug(f"跳过非HTTP协议测速：{url[:60]}")
            return result
        
        for attempt in range(self.retry_times + 1):
            try:
                start_time = time.time()
                async with self.session.get(url) as response:
                    latency = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        resolution = "unknown"
                        content_type = response.headers.get("Content-Type", "")
                        
                        # 新增：如果是m3u8索引文件，解析子链接
                        if "application/vnd.apple.mpegurl" in content_type:
                            sub_result = await self.measure_m3u8_sub_url(url)
                            if sub_result and sub_result.success:
                                return sub_result
                            
                            # 解析当前m3u8的分辨率
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
        
        # 过滤极端无效URL
        urls = filter_invalid_urls(urls)
        tasks = [worker(url) for url in urls if url.strip()]
        await asyncio.gather(*tasks)
        
        logger.info(f"批量测速完成：共测试{len(results)}个URL，成功{len([r for r in results.values() if r.success])}个")
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
    """
    抓取频道并按group-title分类
    【修改10】移除默认分类，完全按原始group_title分组
    """
    # 按分类存储频道（不再预设默认分类）
    categorized_channels = OrderedDict()
    
    try:
        content = fetch_url_with_retry(url)
        if content is None:
            return categorized_channels
        
        # 提取带完整元数据的频道列表
        channel_list = extract_channels_from_content(content)
        
        # 按原始group_title分类（支持空字符串键）
        for channel in channel_list:
            group = channel.group_title  # 直接使用原始分类，可为空字符串
            if group not in categorized_channels:
                categorized_channels[group] = []
            categorized_channels[group].append(channel)
            
    except Exception as e:
        logger.error(f"处理 {url} 时发生异常：{str(e)}", exc_info=True)

    return categorized_channels

def merge_channels(target: Dict[str, List[ChannelInfo]], source: Dict[str, List[ChannelInfo]]):
    """
    合并分类的频道信息（仅按URL去重）
    【修改11】支持空字符串的group_title合并
    """
    # 先收集所有已存在的URL用于去重
    existing_urls = set()
    for group in target:
        for channel in target[group]:
            existing_urls.add(channel.url)
    
    for group, channels in source.items():
        # 空字符串分类也正常合并
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

def filter_source_urls(template_file: str) -> Tuple[Dict[str, Dict[str, List[ChannelInfo]]], OrderedDict, Dict[str, List[ChannelInfo]], List[ChannelInfo]]:
    """
    优化：返回所有抓取的频道（不局限于模板匹配），并返回扁平化列表
    返回：匹配的频道、模板、所有抓取的频道、扁平化频道列表
    """
    # 解析模板
    template_channels = parse_template(template_file)
    if not template_channels:
        logger.error("模板解析为空，终止流程")
        return {}, OrderedDict(), {}, []
    
    # 获取源URL配置
    source_urls = getattr(config, 'source_urls', CONFIG_DEFAULTS["SOURCE_URLS"])
    if not source_urls:
        logger.error("未配置source_urls，终止流程")
        return {}, template_channels, {}, []
    
    # 抓取并合并所有源（【修改12】不再预设默认分类）
    all_channels = OrderedDict()
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
    # 【修改13】统计空分类数量
    empty_group_count = len([g for g in all_channels if g == ""])
    if empty_group_count > 0:
        logger.info(f"  - 无分类频道数：{len(all_channels.get('', []))}")
    
    if success_urls:
        logger.info(f"  - 成功的源：{', '.join(success_urls[:3])}{'...' if len(success_urls)>3 else ''}")
    if failed_urls:
        logger.info(f"  - 失败的源：{', '.join(failed_urls[:3])}{'...' if len(failed_urls)>3 else ''}")
    
    # 匹配频道
    matched_channels = match_channels(template_channels, all_channels)
    
    # 扁平化所有频道（用于生成标准化M3U）
    flat_channels = []
    for group, channels in all_channels.items():
        flat_channels.extend(channels)
    
    return matched_channels, template_channels, all_channels, flat_channels

# ===================== 文件生成 =====================
def write_to_files(f_m3u, f_txt, category, channel_info: ChannelInfo, index: int, ip_version: str):
    """
    写入带完整元数据的频道信息（标注失败状态）
    【修改14】保留原始group_title，空分类显示为"未分类"
    【新增】添加tvg-logo属性到EXTINF行
    """
    if not channel_info.url:
        return
    
    # 构建M3U属性行
    extinf_parts = [f"#EXTINF:-1"]
    if channel_info.tvg_name:
        extinf_parts.append(f'tvg-name="{channel_info.tvg_name}"')
    if channel_info.tvg_id:
        extinf_parts.append(f'tvg-id="{channel_info.tvg_id}"')
    # 【新增】添加tvg-logo属性
    if channel_info.tvg_logo:
        extinf_parts.append(f'tvg-logo="{channel_info.tvg_logo}"')
    # 【修改15】使用原始group_title（模板匹配时用模板分类，否则用原始）
    if category:
        extinf_parts.append(f'group-title="{category}"')
    elif channel_info.group_title:
        extinf_parts.append(f'group-title="{channel_info.group_title}"')
    
    # 添加频道名（标注延迟/失败）
    if channel_info.latency >= 9999.0:
        channel_display_name = f"{channel_info.name}(失败)"
    else:
        channel_display_name = f"{channel_info.name}"
    
    extinf_line = ' '.join(extinf_parts) + f',{channel_display_name}'
    
    # 生成带后缀的URL
    url_with_suffix = add_url_suffix(
        channel_info.url, 
        index, 
        1, 
        ip_version, 
        channel_info.latency
    )
    
    # 写入M3U
    f_m3u.write(f"{extinf_line}\n")
    f_m3u.write(f"{url_with_suffix}\n")
    
    # 写入TXT（分类,频道名,URL,台标URL）【新增台标URL字段】
    # 【修改16】空分类显示为"未分类"
    display_category = category if category else (channel_info.group_title if channel_info.group_title else "未分类")
    f_txt.write(f"{display_category},{channel_display_name},{url_with_suffix},{channel_info.tvg_logo}\n")

def updateChannelUrlsM3U(matched_channels: Dict[str, Dict[str, List[ChannelInfo]]], 
                         template_channels: OrderedDict,
                         all_channels: Dict[str, List[ChannelInfo]],
                         latency_results: Dict[str, SpeedTestResult]):
    """
    优化：生成带完整M3U元数据的文件
    包含所有抓取的URL（即使未匹配模板/测速失败）
    【修改17】保留原始group_title，空分类单独处理
    【新增】支持tvg-logo属性生成
    """
    latency_threshold = getattr(config, 'LATENCY_THRESHOLD', CONFIG_DEFAULTS["LATENCY_THRESHOLD"])
    written_urls_ipv4 = set()
    written_urls_ipv6 = set()

    # 文件路径
    ipv4_m3u_path = OUTPUT_FOLDER / "live_ipv4.m3u"
    ipv4_txt_path = OUTPUT_FOLDER / "live_ipv4.txt"
    ipv6_m3u_path = OUTPUT_FOLDER / "live_ipv6.m3u"
    ipv6_txt_path = OUTPUT_FOLDER / "live_ipv6.txt"
    all_m3u_path = OUTPUT_FOLDER / "live_all.m3u"  # 新增：所有URL汇总文件

    # 获取EPG和公告配置
    epg_urls = getattr(config, 'epg_urls', CONFIG_DEFAULTS["EPG_URLS"])
    announcements = getattr(config, 'announcements', CONFIG_DEFAULTS["ANNOUNCEMENTS"])

    try:
        with open(ipv4_m3u_path, "w", encoding="utf-8") as f_m3u_ipv4, \
             open(ipv4_txt_path, "w", encoding="utf-8") as f_txt_ipv4, \
             open(ipv6_m3u_path, "w", encoding="utf-8") as f_m3u_ipv6, \
             open(ipv6_txt_path, "w", encoding="utf-8") as f_txt_ipv6, \
             open(all_m3u_path, "w", encoding="utf-8") as f_m3u_all:

            # 写入M3U头部（包含EPG信息）
            epg_str = ",".join(epg_urls) if epg_urls else ""
            header_note = f"# 延迟阈值：{latency_threshold}ms | 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            header_note_all = f"# 包含所有抓取的URL（共{len(latency_results)}个）| 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            f_m3u_ipv4.write(f"#EXTM3U x-tvg-url=\"{epg_str}\"\n{header_note}")
            f_m3u_ipv6.write(f"#EXTM3U x-tvg-url=\"{epg_str}\"\n{header_note}")
            f_m3u_all.write(f"#EXTM3U x-tvg-url=\"{epg_str}\"\n{header_note_all}")

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
                    
                    if not entry_url:
                        continue
                    
                    # 【新增】为公告频道生成台标URL
                    entry_logo = generate_logo_url(entry_name)
                    
                    entry_result = latency_results.get(entry_url)
                    if entry_result:
                        if entry_result.success and entry_result.latency and entry_result.latency <= latency_threshold:
                            latency = entry_result.latency
                        else:
                            latency = 9999.0
                    else:
                        latency = 9999.0
                    
                    if is_ipv6(entry_url):
                        if entry_url not in written_urls_ipv6:
                            written_urls_ipv6.add(entry_url)
                            # 构建公告频道的EXTINF行（新增tvg-logo）
                            if latency >= 9999.0:
                                display_name = f"{entry_name}(失败)"
                            else:
                                display_name = f"{entry_name}({latency:.0f}ms)"
                            extinf_parts = [f"#EXTINF:-1", f'tvg-name="{entry_name}"', f'group-title="{channel_name}"']
                            if entry_logo:
                                extinf_parts.append(f'tvg-logo="{entry_logo}"')
                            extinf = ' '.join(extinf_parts) + f',{display_name}'
                            
                            f_m3u_ipv6.write(f"{extinf}\n{entry_url}\n")
                            f_txt_ipv6.write(f"{channel_name},{display_name},{entry_url},{entry_logo}\n")
                            f_m3u_all.write(f"{extinf}\n{entry_url}\n")
                            announcement_id += 1
                    else:
                        if entry_url not in written_urls_ipv4:
                            written_urls_ipv4.add(entry_url)
                            if latency >= 9999.0:
                                display_name = f"{entry_name}(失败)"
                            else:
                                display_name = f"{entry_name}({latency:.0f}ms)"
                            extinf_parts = [f"#EXTINF:-1", f'tvg-name="{entry_name}"', f'group-title="{channel_name}"']
                            if entry_logo:
                                extinf_parts.append(f'tvg-logo="{entry_logo}"')
                            extinf = ' '.join(extinf_parts) + f',{display_name}'
                            
                            f_m3u_ipv4.write(f"{extinf}\n{entry_url}\n")
                            f_txt_ipv4.write(f"{channel_name},{display_name},{entry_url},{entry_logo}\n")
                            f_m3u_all.write(f"{extinf}\n{entry_url}\n")
                            announcement_id += 1

            # 写入所有抓取的频道（不局限于模板匹配）
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
                        write_to_files(f_m3u_ipv4, f_txt_ipv4, template_group, channel, idx, "IPV4")
                        # 同时写入全量文件
                        write_to_files(f_m3u_all, f_txt_ipv4, template_group, channel, idx, "IPV4")
                    
                    # 写入IPv6频道
                    for idx, channel in enumerate(ipv6_channels, start=1):
                        write_to_files(f_m3u_ipv6, f_txt_ipv6, template_group, channel, idx, "IPV6")
                        # 同时写入全量文件
                        write_to_files(f_m3u_all, f_txt_ipv6, template_group, channel, idx, "IPV6")

            # 写入未匹配模板的频道（【修改18】保留原始group_title）
            # 收集已写入的URL
            all_written_urls = written_urls_ipv4.union(written_urls_ipv6)
            # 遍历所有频道，写入未匹配的
            unmatch_count = 0
            f_m3u_all.write("\n# ===== 未匹配模板的频道 =====\n")
            for group, channels in all_channels.items():
                for channel in channels:
                    if channel.url in all_written_urls:
                        continue
                    unmatch_count += 1
                    # 显示用的分类名（空分类显示为"未分类"）
                    display_group = group if group else "未分类"
                    # 按IP版本分类
                    if is_ipv6(channel.url):
                        if channel.url not in written_urls_ipv6:
                            written_urls_ipv6.add(channel.url)
                            write_to_files(f_m3u_all, f_txt_ipv6, display_group, channel, unmatch_count, "IPV6")
                    else:
                        if channel.url not in written_urls_ipv4:
                            written_urls_ipv4.add(channel.url)
                            write_to_files(f_m3u_all, f_txt_ipv4, display_group, channel, unmatch_count, "IPV4")

        # 生成测速报告
        generate_speed_report(latency_results, latency_threshold)
        
        logger.info(f"\n文件生成完成：")
        logger.info(f"  - IPv4 M3U: {ipv4_m3u_path}（包含完整M3U元数据+台标）")
        logger.info(f"  - IPv4 TXT: {ipv4_txt_path}（分类,频道名,URL,台标URL格式）")
        logger.info(f"  - IPv6 M3U: {ipv6_m3u_path}（包含完整M3U元数据+台标）")
        logger.info(f"  - IPv6 TXT: {ipv6_txt_path}（分类,频道名,URL,台标URL格式）")
        logger.info(f"  - 全量M3U: {all_m3u_path}（包含所有抓取的URL，共{len(latency_results)}个）")
        logger.info(f"  - 标准化M3U: {STANDARD_M3U_PATH}（去重后规范格式+台标）")
        logger.info(f"  - 延迟阈值：{latency_threshold}ms")
        logger.info(f"  - 未匹配模板的频道数：{unmatch_count}")
        # 【新增】台标配置信息
        if hasattr(config, 'logo_url') and config.logo_url:
            logger.info(f"  - 台标库地址：{config.logo_url}")
            logger.info(f"  - 台标文件类型：{getattr(config, 'logo_type', 'png')}")
        
    except Exception as e:
        logger.error(f"生成文件失败：{str(e)}", exc_info=True)

def generate_speed_report(latency_results: Dict[str, SpeedTestResult], latency_threshold: float):
    """生成详细的测速报告（包含失败原因统计）"""
    report_path = OUTPUT_FOLDER / "speed_test_report.txt"
    
    total_urls = len(latency_results)
    success_urls = [r for r in latency_results.values() if r.success]
    valid_urls = [r for r in success_urls if r.latency and r.latency <= latency_threshold]
    failed_urls = [r for r in latency_results.values() if not r.success]
    
    # 统计失败原因
    fail_reasons = {}
    for result in failed_urls:
        reason = result.error or "未知错误"
        fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
    
    # 按延迟排序
    valid_urls.sort(key=lambda x: x.latency)
    success_urls.sort(key=lambda x: x.latency if x.latency else 9999)
    
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("IPTV直播源测速报告（优化版）\n")
            f.write("="*80 + "\n")
            f.write(f"测试时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"延迟阈值：{latency_threshold}ms | 超时时间：{CONFIG_DEFAULTS['TIMEOUT']}s\n")
            # 【新增】台标配置信息
            if hasattr(config, 'logo_url') and config.logo_url:
                f.write(f"台标库地址：{config.logo_url} | 台标类型：{getattr(config, 'logo_type', 'png')}\n")
            f.write(f"总测试URL数：{total_urls}（基于标准化M3U去重后）\n")
            success_rate = f"{len(success_urls)/total_urls*100:.1f}%" if total_urls > 0 else "0.0%"
            f.write(f"测试成功数：{len(success_urls)} ({success_rate})\n")
            valid_rate = f"{len(valid_urls)/total_urls*100:.1f}%" if total_urls > 0 else "0.0%"
            f.write(f"有效URL数（延迟≤{latency_threshold}ms）：{len(valid_urls)} ({valid_rate})\n")
            f.write(f"失败URL数：{len(failed_urls)}\n")
            f.write("="*80 + "\n\n")
            
            # 失败原因统计
            f.write("【失败原因统计】\n")
            for reason, count in fail_reasons.items():
                f.write(f"  {reason}: {count}个 ({count/len(failed_urls)*100:.1f}%)\n")
            f.write("\n")
            
            # 有效URL列表
            if valid_urls:
                f.write("【有效URL列表（按延迟升序）】\n")
                for idx, result in enumerate(valid_urls, 1):
                    f.write(f"{idx:3d}. 延迟：{result.latency:6.2f}ms | 分辨率：{result.resolution:8s} | URL：{result.url[:100]}...\n")
            else:
                f.write("【有效URL列表（按延迟升序）】\n")
                f.write("无有效URL\n")
            
            # 成功但超阈值的URL
            over_threshold = [r for r in success_urls if r.latency and r.latency > latency_threshold]
            if over_threshold:
                f.write("\n【成功但延迟超阈值的URL】\n")
                for idx, result in enumerate(over_threshold, 1):
                    f.write(f"{idx:3d}. 延迟：{result.latency:6.2f}ms | 分辨率：{result.resolution:8s} | URL：{result.url[:100]}...\n")
            
            # 失败URL列表（前50个）
            if failed_urls:
                f.write("\n【失败URL列表（前50个）】\n")
                for idx, result in enumerate(failed_urls[:50], 1):
                    f.write(f"{idx:3d}. 原因：{result.error:10s} | URL：{result.url[:100]}...\n")
                if len(failed_urls) > 50:
                    f.write(f"  ... 共{len(failed_urls)}个失败URL，仅显示前50个\n")
            else:
                f.write("\n【失败URL列表】\n")
                f.write("无失败URL\n")
        
        logger.info(f"  - 详细测速报告：{report_path}")
    except Exception as e:
        logger.error(f"生成测速报告失败：{str(e)}", exc_info=True)

# ===================== 主程序（核心重构：新增M3U标准化汇总步骤） =====================
async def main():
    """主函数（整合所有优化，新增M3U标准化汇总）"""
    try:
        # 配置加载
        template_file = getattr(config, 'TEMPLATE_FILE', CONFIG_DEFAULTS["TEMPLATE_FILE"])
        latency_threshold = getattr(config, 'LATENCY_THRESHOLD', CONFIG_DEFAULTS["LATENCY_THRESHOLD"])
        logger.info("===== 开始处理直播源（优化版-标准化M3U） =====")
        logger.info(f"延迟阈值设置：{latency_threshold}ms | 超时时间：{CONFIG_DEFAULTS['TIMEOUT']}s")
        logger.info(f"⚠️  已启用原始group-title保留模式，不再使用默认分类 ⚠️")
        # 【新增】打印台标配置信息
        if hasattr(config, 'logo_url') and config.logo_url:
            logger.info(f"🎨 台标配置：{config.logo_url} | 文件类型：{getattr(config, 'logo_type', 'png')}")
        
        # 步骤1：抓取并提取所有频道
        logger.info("\n===== 1. 抓取并提取直播源频道 =====")
        matched_channels, template_channels, all_channels, flat_channels = filter_source_urls(template_file)
        if not matched_channels and not all_channels:
            logger.error("无匹配的频道数据，终止流程")
            return
        
        # 步骤2：生成标准化M3U文件（核心新增）
        logger.info("\n===== 2. 生成标准化M3U文件（去重+规范格式+台标） =====")
        # 生成标准化M3U并获取去重后的URL列表
        unique_urls = generate_standard_m3u(flat_channels, STANDARD_M3U_PATH)
        
        # 步骤3：批量测速（基于去重后的URL）
        logger.info(f"\n===== 3. 开始批量测速（共{len(unique_urls)}个URL，基于标准化M3U） =====")
        async with SpeedTester() as tester:
            latency_results = await tester.batch_speed_test(unique_urls)
        
        # 步骤4：生成最终文件（包含测速结果）
        logger.info("\n===== 4. 生成最终文件（包含所有URL+失败标注+台标） =====")
        updateChannelUrlsM3U(matched_channels, template_channels, all_channels, latency_results)
        
        logger.info("\n===== 所有流程执行完成 =====")
        logger.info(f"📊 最终统计：")
        logger.info(f"   - 原始抓取频道数：{len(flat_channels)}")
        logger.info(f"   - 去重后频道数：{len(unique_urls)}")
        logger.info(f"   - 测速成功数：{len([r for r in latency_results.values() if r.success])}")
        logger.info(f"   - 有效URL数：{len([r for r in latency_results.values() if r.success and r.latency and r.latency <= latency_threshold])}")
        logger.info(f"   - 标准化M3U文件：{STANDARD_M3U_PATH}")
    
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
