import re
import requests
import logging
import warnings
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set, OrderedDict as OrderedDictType

# 导入配置文件（确保config.py与当前脚本在同一目录）
try:
    import config
except ImportError as e:
    raise ImportError("未找到config.py配置文件，请确保其与当前脚本在同一目录下") from e

import os

# ===================== 基础配置（优化：常量大写规范化、配置更清晰） =====================
warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

# 输出目录配置
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# 日志文件配置
LOG_FILE = OUTPUT_DIR / "live_source_extract.log"

# 支持的GitHub镜像域名（优化：去重，保留高效镜像）
GITHUB_MIRRORS = (
    "raw.githubusercontent.com",
    "raw.kkgithub.com",
    "raw.githubusercontents.com",
    "raw.fgit.cf",
    "raw.fgithub.de",
)

# 支持的GitHub代理前缀（优化：保留常用高效代理）
GITHUB_PROXY_PREFIXES = (
    "https://ghproxy.com/",
    "https://mirror.ghproxy.com/",
    "https://gh.api.99988866.xyz/",
)

# 支持的直播源协议（优化：元组固化，避免运行时修改）
SUPPORTED_PROTOCOLS = (
    "http://",
    "https://",
    "rtsp://",
    "rtmp://",
    "m3u8://",
    "hls://",
)

# HTTP请求配置（优化：抽离可配置参数，方便调整）
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
REQUEST_TIMEOUTS = (5, 10, 15, 15, 15)  # 重试超时时间递增序列
MAX_CANDIDATE_URLS = 5  # 最大候选URL数量

# ===================== 日志配置（优化：更清晰的格式，支持DEBUG调试） =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE, "w", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("IPTV_Source_Processor")

# ===================== 数据结构（优化：增加默认值，字段注释更清晰，缓存自动初始化） =====================
@dataclass
class ChannelMeta:
    """频道元信息数据类（封装单个频道的完整信息）"""
    url: str  # 直播源URL（唯一标识，用于去重）
    source_url: str = ""  # 该频道的原始来源URL（用于追溯）
    raw_extinf: str = ""  # 原始EXTINF行（M3U格式专用）
    tvg_id: Optional[str] = None  # EPG指南对应的频道ID
    tvg_name: Optional[str] = None  # 标准化后的频道名称
    tvg_logo: Optional[str] = None  # 频道图标URL
    group_title: Optional[str] = None  # 标准化后的分类名称
    channel_name: Optional[str] = None  # 频道显示名称
    protocol: str = ""  # 直播源协议类型（内部记录，不输出到最终文件）

# 全局缓存（优化：使用注解，初始化更清晰，避免全局变量混乱）
CHANNEL_META_CACHE: Dict[str, ChannelMeta] = {}  # URL -> ChannelMeta
URL_SOURCE_MAPPING: Dict[str, str] = {}  # URL -> 原始来源URL

# ===================== 工具函数（优化：性能提升、健壮性增强、代码更简洁） =====================
def get_url_protocol(url: str) -> str:
    """
    提取URL的协议类型，返回标准化协议名称（内部使用）
    优化：提前小写转换，减少多次lower()调用，提升匹配效率
    """
    if not isinstance(url, str) or not url.strip():
        return "未知协议"
    
    url_lower = url.strip().lower()
    for proto in SUPPORTED_PROTOCOLS:
        if url_lower.startswith(proto.lower()):
            return proto[:-3].upper()  # 去除"://"，转为大写（如HTTP、RTSP）
    
    return "未知协议"

def clean_group_title(group_title: Optional[str], channel_name: Optional[str] = None) -> str:
    """
    清洗分类名称（集成config中的分类映射标准化，返回有效分类）
    优化：
    1. 处理None值更优雅，避免冗余判断
    2. 正则编译复用，提升匹配效率
    3. 简化逻辑，减少临时变量
    """
    # 初始化默认值
    group_title = (group_title or "").strip()
    channel_name = (channel_name or "").strip()
    
    # 第一步：通过config中的反向映射实现分类标准化（优先匹配）
    reverse_mapping = getattr(config, 'group_title_reverse_mapping', {})
    if group_title in reverse_mapping:
        group_title = reverse_mapping[group_title]
    
    # 第二步：清洗特殊字符（正则预编译，提升多次调用效率）
    valid_char_pattern = re.compile(r'[\u4e00-\u9fa5a-zA-Z0-9_\(\)]')
    final_title = ''.join(valid_char_pattern.findall(group_title)).strip()
    
    # 第三步：兜底处理+长度限制
    return (final_title[:20] or "未分类").strip()

def _get_cctv_mappings() -> Dict[str, str]:
    """
    获取整合后的CCTV名称映射（内部辅助函数，避免重复构建映射）
    优化：提取公共逻辑，提升代码复用性，减少冗余
    """
    cctv_mappings = {}
    # 安全获取config中的映射配置
    cctv_mappings.update(getattr(config, 'cntvNamesReverse', {}))
    cctv_mappings.update(getattr(config, 'cctv_alias', {}))
    return cctv_mappings

def global_replace_cctv_name(content: str) -> str:
    """
    批量替换文本中的CCTV频道名称为标准名称
    优化：
    1. 提前排序映射，避免重复排序
    2. 处理非字符串输入，提升健壮性
    3. 简化替换逻辑，提升可读性
    """
    if not isinstance(content, str) or not content.strip():
        return content
    
    # 获取整合后的映射并按名称长度降序排序（避免短名称覆盖长名称）
    cctv_mappings = _get_cctv_mappings()
    sorted_mappings = sorted(cctv_mappings.items(), key=lambda x: (-len(x[0]), x[0]))
    
    # 执行批量替换
    replaced_content = content
    for old_name, new_name in sorted_mappings:
        if old_name in replaced_content:
            replaced_content = replaced_content.replace(old_name, new_name)
    
    return replaced_content

def standardize_cctv_name(channel_name: Optional[str]) -> str:
    """
    标准化单个CCTV频道名称
    优化：
    1. 优雅处理None值和空字符串
    2. 减少冗余循环，提升匹配效率
    3. 安全获取config配置，避免导入错误
    """
    channel_name = (channel_name or "").strip()
    if not channel_name:
        return ""
    
    cctv_mappings = _get_cctv_mappings()
    
    # 第一步：精准匹配
    if channel_name in cctv_mappings:
        return cctv_mappings[channel_name]
    
    # 第二步：模糊匹配（包含关系）
    normalized_name = channel_name
    for raw_name, standard_name in cctv_mappings.items():
        if raw_name in normalized_name:
            return standard_name
    
    # 第三步：无匹配返回原名称
    return normalized_name

def generate_github_candidate_urls(url: str) -> List[str]:
    """
    生成GitHub URL的多个候选地址（镜像+代理），提升抓取成功率
    优化：
    1. 提前判断是否为GitHub URL，减少无效处理
    2. 使用集合去重，逻辑更简洁
    3. 限制候选数量，避免过多重试耗时
    """
    if not isinstance(url, str) or "github" not in url.lower():
        return [url]
    
    # 初始化候选URL集合（自动去重）
    candidate_urls = {url}
    
    # 第一步：替换GitHub镜像域名
    for mirror in GITHUB_MIRRORS:
        for original in GITHUB_MIRRORS:
            if original in url:
                candidate_urls.add(url.replace(original, mirror))
    
    # 第二步：添加代理前缀
    for base_url in list(candidate_urls):  # 遍历副本，避免修改原集合
        for proxy in GITHUB_PROXY_PREFIXES:
            if not base_url.startswith(proxy):
                candidate_urls.add(proxy + base_url)
    
    # 第三步：去重并限制数量，返回列表
    return list(candidate_urls)[:MAX_CANDIDATE_URLS]

def fetch_url_with_retry(url: str) -> Optional[str]:
    """
    带重试机制的URL内容抓取，支持GitHub镜像/代理自动切换
    优化：
    1. 抽离请求配置，逻辑更清晰
    2. 优化异常捕获，只捕获相关请求异常
    3. 自动转换blob地址为raw地址，提升抓取成功率
    4. 简化超时时间赋值，减少冗余判断
    """
    if not isinstance(url, str) or not url.strip():
        logger.error("无效的URL，无法进行抓取")
        return None
    
    original_url = url.strip()
    current_url = original_url
    
    # 转换GitHub blob地址为raw原始文件地址（关键优化，避免抓取网页而非原始文件）
    if "github.com" in current_url and "/blob/" in current_url:
        current_url = current_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    
    # 获取候选地址列表
    candidate_urls = generate_github_candidate_urls(current_url)
    if not candidate_urls:
        logger.error(f"无法生成有效候选地址，抓取失败：{original_url}")
        return None
    
    # 遍历候选地址进行抓取
    for idx, candidate in enumerate(candidate_urls):
        try:
            # 选择对应超时时间
            timeout = REQUEST_TIMEOUTS[idx] if idx < len(REQUEST_TIMEOUTS) else REQUEST_TIMEOUTS[-1]
            
            # 发送HTTP请求
            response = requests.get(
                candidate,
                headers=REQUEST_HEADERS,
                timeout=timeout,
                verify=False,
                allow_redirects=True
            )
            response.raise_for_status()  # 抛出HTTP状态码异常（4xx/5xx）
            
            # 自动识别编码，避免中文乱码
            response.encoding = response.apparent_encoding or 'utf-8'
            logger.debug(f"抓取成功 [{idx+1}/{len(candidate_urls)}]：{candidate}")
            return response.text
        
        except requests.RequestException as e:
            logger.warning(f"抓取失败 [{idx+1}/{len(candidate_urls)}]：{candidate} | 异常信息：{str(e)[:50]}")
            continue
    
    # 所有候选地址均失败
    logger.error(f"所有候选地址均抓取失败：{original_url}")
    return None

def extract_m3u_meta(content: str, source_url: str) -> Tuple[OrderedDictType[str, List[Tuple[str, str]]], List[ChannelMeta]]:
    """
    解析标准M3U格式内容，提取频道元信息和分类（支持多种直播协议）
    优化：
    1. 正则预编译，提升多次匹配效率
    2. 简化数据处理逻辑，减少临时变量
    3. 增强无效数据过滤，提升结果纯净度
    4. 优化日志输出，信息更精准
    """
    # 预编译正则表达式（提升多次调用效率）
    m3u_pattern = re.compile(
        r"(#EXTINF:-?\d+.*?)\n\s*([^#\n\r\s].*?)(?=\s|#|$)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE
    )
    attr_pattern = re.compile(r'(\w+)-(\w+)="([^"]*)"')
    channel_name_pattern = re.compile(r',\s*(.+?)\s*$')
    
    # 初始化返回数据
    categorized_channels = OrderedDict()
    meta_list = []
    seen_urls = set()  # 用于URL去重，避免重复频道
    
    # 匹配M3U条目
    matches = m3u_pattern.findall(content)
    logger.info(f"M3U格式匹配到 {len(matches)} 个候选条目")
    
    for raw_extinf, url in matches:
        # 清洗数据并过滤无效条目
        url = url.strip()
        raw_extinf = raw_extinf.strip()
        
        if not url or not url.startswith(SUPPORTED_PROTOCOLS) or url in seen_urls:
            continue
        
        # 标记已处理URL，避免重复
        seen_urls.add(url)
        URL_SOURCE_MAPPING[url] = source_url
        
        # 提取EXTINF中的属性
        tvg_id = tvg_name = tvg_logo = group_title = None
        channel_name = ""
        
        for attr1, attr2, value in attr_pattern.findall(raw_extinf):
            full_attr = f"{attr1}-{attr2}"
            if full_attr == "tvg-id":
                tvg_id = value
            elif full_attr == "tvg-name":
                tvg_name = standardize_cctv_name(value)
            elif full_attr == "tvg-logo":
                tvg_logo = value
            elif full_attr == "group-title":
                group_title = value
        
        # 提取频道名称
        name_match = channel_name_pattern.search(raw_extinf)
        if name_match:
            channel_name = standardize_cctv_name(name_match.group(1))
        
        # 清洗分类名称
        group_title = clean_group_title(group_title, channel_name)
        
        # 提取协议类型
        protocol = get_url_protocol(url)
        
        # 封装频道元信息
        channel_meta = ChannelMeta(
            url=url,
            source_url=source_url,
            raw_extinf=raw_extinf,
            tvg_id=tvg_id,
            tvg_name=tvg_name,
            tvg_logo=tvg_logo,
            group_title=group_title,
            channel_name=channel_name,
            protocol=protocol
        )
        meta_list.append(channel_meta)
        CHANNEL_META_CACHE[url] = channel_meta
        
        # 按分类整理频道
        if group_title not in categorized_channels:
            categorized_channels[group_title] = []
        categorized_channels[group_title].append((channel_name, url))
    
    # 输出有效频道统计
    valid_channel_count = len(meta_list)
    logger.info(f"M3U格式提取有效频道数：{valid_channel_count}（支持协议：{', '.join(p[:-3].upper() for p in SUPPORTED_PROTOCOLS)}）")
    
    return categorized_channels, meta_list

def extract_channels_from_content(content: str, source_url: str) -> OrderedDictType[str, List[Tuple[str, str]]]:
    """
    兼容解析M3U格式和自定义文本格式的直播源（支持多种直播协议）
    优化：
    1. 提前判断内容类型，减少无效处理
    2. 正则预编译，提升匹配效率
    3. 简化自定义文本解析逻辑，提升可读性
    4. 增强数据过滤，提升结果纯净度
    """
    if not isinstance(content, str) or not content.strip():
        logger.warning("无效的内容，无法提取频道")
        return OrderedDict()
    
    # 优先处理标准M3U格式
    if "#EXTM3U" in content:
        m3u_categorized, _ = extract_m3u_meta(content, source_url)
        return m3u_categorized
    
    # 处理自定义文本格式
    categorized_channels = OrderedDict()
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    current_group = ""
    seen_urls = set()
    
    # 预编译正则表达式
    category_pattern = re.compile(r'[：:=](\S+)')
    invalid_line_pattern = re.compile(r'^(\/\/|#|\/\*|\*\/)')
    channel_pattern = re.compile(
        r'([^,|#$]+)[,|#$]\s*(' + '|'.join([p[:-3] for p in SUPPORTED_PROTOCOLS]) + r':\/\/[^\s,|#$]+)',
        re.IGNORECASE
    )
    
    for line in lines:
        # 跳过注释行，识别分类行
        if invalid_line_pattern.match(line):
            if any(keyword in line.lower() for keyword in ['#分类', '#genre', '分类:', 'genre:', '==', '---']):
                # 提取分类名称
                group_match = category_pattern.search(line)
                if group_match:
                    current_group = group_match.group(1).strip()
                else:
                    current_group = re.sub(r'[#分类:genre:==\-—]', '', line).strip() or ""
            continue
        
        # 匹配频道行（名称,URL 或 名称|URL）
        for name, url in channel_pattern.findall(line):
            name = name.strip()
            url = url.strip()
            
            # 过滤无效URL
            if not url or url in seen_urls:
                continue
            
            # 标准化处理
            seen_urls.add(url)
            URL_SOURCE_MAPPING[url] = source_url
            standard_name = standardize_cctv_name(name)
            group_title = clean_group_title(current_group, standard_name)
            protocol = get_url_protocol(url)
            
            # 封装频道元信息
            raw_extinf = f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{standard_name}\" tvg-logo=\"\" group-title=\"{group_title}\",{standard_name}"
            channel_meta = ChannelMeta(
                url=url,
                source_url=source_url,
                raw_extinf=raw_extinf,
                tvg_name=standard_name,
                group_title=group_title,
                channel_name=standard_name,
                protocol=protocol
            )
            CHANNEL_META_CACHE[url] = channel_meta
            
            # 按分类整理频道
            if group_title not in categorized_channels:
                categorized_channels[group_title] = []
            categorized_channels[group_title].append((standard_name, url))
    
    # 输出统计信息
    valid_channel_count = sum(len(v) for v in categorized_channels.values())
    logger.info(f"自定义文本格式提取有效频道数：{valid_channel_count}（支持协议：{', '.join(p[:-3].upper() for p in SUPPORTED_PROTOCOLS)}）")
    
    # 过滤空分类
    return OrderedDict([(k, v) for k, v in categorized_channels.items() if v])

def merge_channels(target: OrderedDictType[str, List[Tuple[str, str]]], 
                   source: OrderedDictType[str, List[Tuple[str, str]]]) -> None:
    """
    合并多个来源的频道，仅按URL去重，保留所有有效分类和频道
    优化：
    1. 改为原地修改target，减少内存占用
    2. 简化去重逻辑，提升效率
    3. 增强参数类型检查，提升健壮性
    """
    if not isinstance(target, OrderedDict) or not isinstance(source, OrderedDict):
        logger.warning("无效的频道字典，无法进行合并")
        return
    
    # 收集目标字典中的所有URL，用于去重
    url_set = set()
    for ch_list in target.values():
        for _, url in ch_list:
            url_set.add(url)
    
    # 遍历源字典，合并新频道
    for category_name, ch_list in source.items():
        if category_name not in target:
            target[category_name] = []
        
        for name, url in ch_list:
            if url not in url_set:
                target[category_name].append((name, url))
                url_set.add(url)

def parse_demo_file(demo_path: Path = Path("demo.txt")) -> OrderedDictType[str, Set[str]]:
    """
    解析demo.txt，提取「分类-允许的频道名称列表」映射（保留分类顺序）
    优化：
    1. 增强文件读取健壮性，处理编码错误
    2. 简化解析逻辑，提升可读性
    3. 优化日志输出，信息更精准
    4. 过滤空分类和空频道，提升结果纯净度
    """
    demo_channel_mapping = OrderedDict()
    
    if not demo_path.exists():
        logger.warning(f"未找到demo.txt文件（路径：{demo_path.absolute()}），跳过筛选配对，保留所有频道")
        return demo_channel_mapping
    
    try:
        # 读取文件内容（支持utf-8编码，处理可能的编码错误）
        with open(demo_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
        
        current_category = None
        
        # 预编译正则表达式
        category_line_pattern = re.compile(r'^┃(.+?),#genre#$')
        channel_line_pattern = re.compile(r'^(.+?),$')
        
        for line in lines:
            # 匹配标准分类行
            category_match = category_line_pattern.match(line)
            if category_match:
                current_category = category_match.group(1).strip()
                if current_category and current_category not in demo_channel_mapping:
                    demo_channel_mapping[current_category] = set()
                continue
            
            # 匹配替代格式分类行
            if any(keyword in line.lower() for keyword in ['#分类', '#genre', '分类:', 'genre:', '==', '---']):
                current_category = re.sub(r'[#分类:genre:==\-—┃,]', '', line).strip()
                if current_category and current_category not in demo_channel_mapping:
                    demo_channel_mapping[current_category] = set()
                continue
            
            # 匹配频道行
            channel_match = channel_line_pattern.match(line)
            if channel_match and current_category:
                channel_name = channel_match.group(1).strip()
                if channel_name:
                    demo_channel_mapping[current_category].add(channel_name)
        
        # 过滤空分类（无有效频道的分类）
        demo_channel_mapping = OrderedDict([
            (cat, chan_set) for cat, chan_set in demo_channel_mapping.items()
            if chan_set and len(chan_set) > 0
        ])
        
        # 输出统计信息
        total_categories = len(demo_channel_mapping)
        total_channels = sum(len(s) for s in demo_channel_mapping.values())
        logger.info(f"成功解析demo.txt：提取到 {total_categories} 个分类，共 {total_channels} 个允许的频道")
        
        for cat, chan_set in demo_channel_mapping.items():
            logger.debug(f"  - 【{cat}】：{sorted(list(chan_set))}")
        
    except Exception as e:
        logger.error(f"解析demo.txt失败，跳过筛选配对：{str(e)}", exc_info=True)
        return OrderedDict()
    
    return demo_channel_mapping

def filter_channels_by_demo(all_channels: OrderedDictType[str, List[Tuple[str, str]]],
                           demo_mapping: OrderedDictType[str, Set[str]]) -> OrderedDictType[str, List[Tuple[str, str]]]:
    """
    根据demo.txt的映射关系，筛选符合条件的频道（仅保留demo中存在的分类和频道）
    优化：
    1. 简化匹配逻辑，提升效率
    2. 增强参数类型检查，提升健壮性
    3. 优化日志输出，信息更精准
    4. 保留demo的分类顺序，提升结果一致性
    """
    # 若demo_mapping为空，直接返回原始频道
    if not isinstance(all_channels, OrderedDict) or not isinstance(demo_mapping, OrderedDict) or not demo_mapping:
        return all_channels
    
    filtered_channels = OrderedDict()
    
    # 遍历demo.txt中的分类（保留demo的分类顺序）
    for demo_category, demo_channel_set in demo_mapping.items():
        matched_channel_list = []
        seen_urls = set()  # 去重，避免同一频道重复匹配
        
        # 标准化demo中的频道名称集合
        standard_demo_channels = {name.strip() for name in demo_channel_set if name.strip()}
        if not standard_demo_channels:
            continue
        
        # 遍历原始频道，匹配符合条件的频道
        for original_channel_list in all_channels.values():
            for channel_name, url in original_channel_list:
                standard_original_name = channel_name.strip()
                
                if standard_original_name in standard_demo_channels and url not in seen_urls:
                    seen_urls.add(url)
                    matched_channel_list.append((channel_name, url))
        
        # 加入筛选结果（仅保留有匹配频道的分类）
        if matched_channel_list:
            filtered_channels[demo_category] = matched_channel_list
    
    # 输出统计信息
    total_categories = len(filtered_channels)
    total_channels = sum(len(l) for l in filtered_channels.values())
    logger.info(f"筛选完成：保留 {total_categories} 个分类，共 {total_channels} 个频道（符合demo.txt规则）")
    
    return filtered_channels

# ===================== 生成输出文件（优化：格式更规范，健壮性更强） =====================
def generate_summary(filtered_channels: OrderedDictType[str, List[Tuple[str, str]]]) -> None:
    """
    生成汇总TXT文件和纯净版M3U文件（无协议标注，可直接导入播放器）
    优化：
    1. 简化文件写入逻辑，提升可读性
    2. 增强异常处理，避免单个文件生成失败影响整体流程
    3. 优化输出格式，提升文件可读性和播放器兼容性
    4. 安全获取频道元信息，避免KeyError
    """
    if not isinstance(filtered_channels, OrderedDict) or not filtered_channels:
        logger.warning("无有效频道可输出，跳过文件生成")
        return
    
    # 定义输出文件路径
    summary_file = OUTPUT_DIR / "live_source_summary.txt"
    m3u_file = OUTPUT_DIR / "live_source_merged.m3u"
    generate_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    total_channels = sum(len(ch_list) for ch_list in filtered_channels.values())
    total_categories = len(filtered_channels)
    supported_protocols = ', '.join(p[:-3].upper() for p in SUPPORTED_PROTOCOLS)
    
    # 生成汇总TXT文件
    try:
        with open(summary_file, "w", encoding="utf-8") as f:
            # 写入头部信息
            f.write("IPTV直播源汇总（自动提取+标准化+多协议支持+demo筛选）\n")
            f.write("=" * 80 + "\n")
            f.write(f"生成时间：{generate_time}\n")
            f.write(f"总频道数：{total_channels}\n")
            f.write(f"分类数：{total_categories}\n")
            f.write(f"支持协议：{supported_protocols}\n")
            f.write("=" * 80 + "\n\n")
            
            # 写入分类和频道详情
            for group_title, channel_list in filtered_channels.items():
                f.write(f"【{group_title}】（{len(channel_list)}个频道）\n")
                for idx, (name, url) in enumerate(channel_list, 1):
                    source = URL_SOURCE_MAPPING.get(url, "未知来源")
                    protocol = get_url_protocol(url)
                    f.write(f"{idx:>3}. {name:<20} [{protocol}] {url}\n")
                    f.write(f"      来源：{source}\n")
                f.write("\n")
        
        logger.info(f"汇总TXT文件生成完成：{summary_file.absolute()}")
    except Exception as e:
        logger.error(f"生成汇总TXT文件失败：{str(e)}", exc_info=True)
    
    # 生成纯净版M3U文件
    try:
        with open(m3u_file, "w", encoding="utf-8") as f:
            # 写入M3U头部信息
            f.write("#EXTM3U x-tvg-url=\"\"\n")
            f.write(f"# IPTV直播源合并文件 | 生成时间：{generate_time}\n")
            f.write(f"# 总频道数：{total_channels} | 总分类数：{total_categories}（已按demo.txt筛选）\n\n")
            
            # 写入分类和频道内容
            for group_title, channel_list in filtered_channels.items():
                f.write(f"# ===== {group_title}（{len(channel_list)}个频道） =====\n")
                for name, url in channel_list:
                    # 安全获取频道元信息
                    channel_meta = CHANNEL_META_CACHE.get(url)
                    safe_name = name.replace('\\', '\\\\').replace('$', '\\$')
                    
                    if channel_meta and channel_meta.raw_extinf:
                        # 标准化EXTINF行中的分类名称
                        extinf_line = channel_meta.raw_extinf
                        if 'group-title="' in extinf_line:
                            start_idx = extinf_line.find('group-title="') + len('group-title="')
                            end_idx = extinf_line.find('"', start_idx)
                            if end_idx > start_idx:
                                extinf_line = extinf_line[:start_idx] + group_title + extinf_line[end_idx:]
                        
                        # 标准化频道名称，避免解析异常
                        if ',' in extinf_line:
                            extinf_part, _ = extinf_line.rsplit(',', 1)
                            extinf_line = extinf_part + ',' + safe_name
                        
                        f.write(f"{extinf_line}\n")
                    else:
                        # 构造默认EXTINF行
                        f.write(f"#EXTINF:-1 tvg-name=\"{safe_name}\" group-title=\"{group_title}\",{safe_name}\n")
                    
                    # 写入直播源URL
                    f.write(f"{url}\n\n")
        
        logger.info(f"纯净版M3U文件生成完成：{m3u_file.absolute()}")
    except Exception as e:
        logger.error(f"生成纯净版M3U文件失败：{str(e)}", exc_info=True)

# ===================== 主程序入口（优化：逻辑更清晰，异常处理更完善） =====================
def main() -> None:
    """主程序入口：协调各模块完成IPTV直播源的提取、处理、筛选和生成"""
    # 初始化全局缓存
    global CHANNEL_META_CACHE, URL_SOURCE_MAPPING
    CHANNEL_META_CACHE.clear()
    URL_SOURCE_MAPPING.clear()
    
    try:
        # 打印程序启动信息
        logger.info("=" * 60)
        logger.info("开始处理IPTV直播源（提取→标准化→合并→筛选→生成）")
        logger.info(f"支持的直播协议：{', '.join(p[:-3].upper() for p in SUPPORTED_PROTOCOLS)}")
        logger.info("=" * 60)
        
        # 读取配置文件中的源URL列表
        source_urls = getattr(config, 'SOURCE_URLS', [])
        if not isinstance(source_urls, list) or not source_urls:
            logger.error("配置文件中未设置有效SOURCE_URLS，程序终止")
            return
        
        logger.info(f"读取到待处理的源URL数：{len(source_urls)}")
        
        # 初始化全局频道字典
        all_channels = OrderedDict()
        failed_urls = []
        
        # 遍历所有源URL，逐个处理
        for idx, url in enumerate(source_urls, 1):
            logger.info(f"\n===== 处理第 {idx}/{len(source_urls)} 个源：{url} =====")
            
            # 抓取URL内容
            content = fetch_url_with_retry(url)
            if content is None:
                failed_urls.append(url)
                continue
            
            # 批量替换CCTV频道名称
            content = global_replace_cctv_name(content)
            
            # 提取频道信息
            extracted_channels = extract_channels_from_content(content, url)
            
            # 合并到全局频道字典
            merge_channels(all_channels, extracted_channels)
        
        # 解析demo.txt，筛选频道
        demo_mapping = parse_demo_file(Path("demo.txt"))
        filtered_channels = filter_channels_by_demo(all_channels, demo_mapping)
        
        # 输出处理完成统计信息
        logger.info(f"\n===== 处理完成统计 =====")
        total_channels = sum(len(ch_list) for ch_list in filtered_channels.values())
        total_categories = len(filtered_channels)
        
        logger.info(f"  - 源URL总数：{len(source_urls)}")
        logger.info(f"  - 抓取失败源数：{len(failed_urls)}")
        logger.info(f"  - 最终有效频道数：{total_channels}（符合demo.txt规则）")
        logger.info(f"  - 最终有效分类数：{total_categories}")
        
        if filtered_channels:
            logger.info(f"  - 分类列表：{list(filtered_channels.keys())}")
        if failed_urls:
            logger.warning(f"  - 失败的源URL列表：{failed_urls}")
        
        # 生成输出文件
        generate_summary(filtered_channels)
        
        # 打印程序结束信息
        logger.info("\n===== 所有操作执行完毕 =====")
        logger.info(f"输出文件存放目录：{OUTPUT_DIR.absolute()}")
    
    except Exception as e:
        logger.critical(f"程序运行过程中出现致命异常：{str(e)}", exc_info=True)

if __name__ == "__main__":
    main()
