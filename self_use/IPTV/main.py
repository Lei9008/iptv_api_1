import re
import requests
import logging
import warnings
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set, OrderedDict as OrderedDictType

# 导入配置文件（确保config.py与当前脚本在同一目录）
import config
import os

# ===================== 基础配置 =====================
warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)
OUTPUT_FOLDER = Path("output")
OUTPUT_FOLDER.mkdir(exist_ok=True)

# 支持的GitHub镜像域名
GITHUB_MIRRORS = [
    "raw.githubusercontent.com",
    "raw.kkgithub.com",
    "raw.githubusercontents.com",
    "raw.fgit.cf",
    "raw.fgithub.de"
]

# 支持的GitHub代理前缀
PROXY_PREFIXES = [
    "https://ghproxy.com/",
    "https://mirror.ghproxy.com/",
    "https://gh.api.99988866.xyz/"
]

# 扩展：支持的直播源协议（解决RTSP被过滤的问题）
SUPPORTED_PROTOCOLS = (
    "http://",
    "https://",
    "rtsp://",
    "rtmp://",
    "m3u8://",
    "hls://"
)

LOG_FILE_PATH = OUTPUT_FOLDER / "live_source_extract.log"
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

# ===================== 数据结构 =====================
@dataclass
class ChannelMeta:
    url: str
    raw_extinf: str = ""
    tvg_id: Optional[str] = None
    tvg_name: Optional[str] = None
    tvg_logo: Optional[str] = None
    group_title: Optional[str] = None
    channel_name: Optional[str] = None
    source_url: str = ""
    protocol: str = ""  # 保留协议记录（仅用于内部，不输出到M3U）

channel_meta_cache: Dict[str, ChannelMeta] = {}
url_source_mapping: Dict[str, str] = {}

# ===================== 工具函数 =====================
def get_url_protocol(url: str) -> str:
    """提取URL的协议类型，返回标准化协议名称（内部使用）"""
    if not url:
        return "未知协议"
    for proto in SUPPORTED_PROTOCOLS:
        if url.lower().startswith(proto.lower()):
            return proto[:-3].upper()  # 去除"://"，转为大写（如HTTP、RTSP）
    return "未知协议"

def clean_group_title(group_title: Optional[str], channel_name: Optional[str] = "") -> str:
    """
    清洗分类名称（集成config中的分类映射标准化，返回有效分类）
    """
    group_title = group_title or ""
    channel_name = channel_name or ""
    
    # 第一步：通过config中的反向映射实现分类标准化（优先匹配）
    if group_title.strip() in config.group_title_reverse_mapping:
        group_title = config.group_title_reverse_mapping[group_title.strip()]
    
    # 第二步：清洗特殊字符，仅保留中文、字母、数字、下划线、括号
    final_title = ''.join(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9_\(\)]+', group_title.strip())).strip() or "未分类"
    
    # 第三步：限制长度，避免分类名称过长影响播放器显示
    return final_title[:20] if final_title else "未分类"

def global_replace_cctv_name(content: str) -> str:
    """批量替换文本中的CCTV频道名称为标准名称"""
    if not content:
        return content
    all_mappings = {}
    all_mappings.update(config.cntvNamesReverse)
    all_mappings.update(config.cctv_alias)
    
    # 按名称长度降序排序，避免短名称覆盖长名称（如先匹配"CCTV5+"再匹配"CCTV5"）
    sorted_mappings = sorted(all_mappings.items(), key=lambda x: (-len(x[0]), x[0]))
    replaced_content = content
    
    for old_name, new_name in sorted_mappings:
        if old_name in replaced_content:
            replaced_content = replaced_content.replace(old_name, new_name)
    
    return replaced_content

def standardize_cctv_name(channel_name: Optional[str]) -> str:
    """标准化单个CCTV频道名称"""
    if not channel_name:
        return ""
    
    # 精准匹配反向映射和别名
    if channel_name in config.cntvNamesReverse:
        return config.cntvNamesReverse[channel_name]
    if channel_name in config.cctv_alias:
        return config.cctv_alias[channel_name]
    
    # 模糊匹配（包含关系）
    normalized_name = channel_name.strip()
    for raw_name, standard_name in config.cntvNamesReverse.items():
        if raw_name in normalized_name:
            return standard_name
    for alias_name, standard_name in config.cctv_alias.items():
        if alias_name in normalized_name:
            return standard_name
    
    # 无匹配则返回原名称（清洗前后空格）
    return normalized_name

def replace_github_domain(url: str) -> List[str]:
    """生成GitHub URL的多个候选地址（镜像+代理），提升抓取成功率"""
    if not url or "github" not in url.lower():
        return [url]
    
    candidate_urls = [url]
    # 替换GitHub镜像域名
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
                if proxy_url not in proxy_urls:
                    proxy_urls.append(proxy_url)
    
    # 去重并保留前5个候选地址（避免过多重试耗时）
    unique_urls = list(dict.fromkeys(candidate_urls + proxy_urls))
    return unique_urls[:5]

def fetch_url_with_retry(url: str, timeout: int = 15) -> Optional[str]:
    """带重试机制的URL内容抓取，支持GitHub镜像/代理自动切换"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    original_url = url
    
    # 转换GitHub blob地址为raw原始文件地址
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    
    # 获取候选地址列表
    candidate_urls = replace_github_domain(url)
    timeouts = [5, 10, 15, 15, 15]  # 超时时间逐步递增
    
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
            response.raise_for_status()  # 抛出HTTP状态码异常（4xx/5xx）
            response.encoding = response.apparent_encoding or 'utf-8'  # 自动识别编码
            return response.text
        except requests.RequestException as e:
            logger.warning(f"抓取失败 [{idx+1}/{len(candidate_urls)}]: {candidate} | {str(e)[:50]}")
            continue
    
    logger.error(f"所有候选地址均抓取失败：{original_url}")
    return None

def extract_m3u_meta(content: str, source_url: str) -> Tuple[OrderedDictType[str, List[Tuple[str, str]]], List[ChannelMeta]]:
    """解析标准M3U格式内容，提取频道元信息和分类（支持多种直播协议）"""
    # 匹配EXTINF行和后续的直播URL
    m3u_pattern = re.compile(
        r"(#EXTINF:-?\d+.*?)\n\s*([^#\n\r\s].*?)(?=\s|#|$)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE
    )
    # 匹配EXTINF中的属性（如tvg-id、group-title）
    attr_pattern = re.compile(r'(\w+)-(\w+)="([^"]*)"')
    
    categorized_channels = OrderedDict()
    meta_list = []
    seen_urls = set()  # 去重（按URL）
    matches = m3u_pattern.findall(content)
    
    logger.info(f"M3U格式匹配到 {len(matches)} 个候选条目")
    
    for raw_extinf, url in matches:
        url = url.strip()
        raw_extinf = raw_extinf.strip()
        
        # 优化：过滤无效URL（非支持协议、已重复、空URL）
        if not url or not url.startswith(SUPPORTED_PROTOCOLS) or url in seen_urls:
            continue
        seen_urls.add(url)
        url_source_mapping[url] = source_url
        
        # 提取EXTINF中的属性
        tvg_id, tvg_name, tvg_logo, group_title = None, None, None, None
        channel_name = ""
        attr_matches = attr_pattern.findall(raw_extinf)
        
        for attr1, attr2, value in attr_matches:
            full_attr = f"{attr1}-{attr2}"
            if full_attr == "tvg-id":
                tvg_id = value
            elif full_attr == "tvg-name":
                tvg_name = standardize_cctv_name(value)
            elif full_attr == "tvg-logo":
                tvg_logo = value
            elif full_attr == "group-title":
                group_title = value
        
        # 提取频道名称（EXTINF行末尾的,后内容）
        name_match = re.search(r',\s*(.+?)\s*$', raw_extinf)
        if name_match:
            channel_name = standardize_cctv_name(name_match.group(1).strip())
        
        # 清洗分类名称
        group_title = clean_group_title(group_title, channel_name)
        
        # 提取协议类型（内部使用，不输出）
        protocol = get_url_protocol(url)
        
        # 封装频道元信息
        meta = ChannelMeta(
            url=url,
            raw_extinf=raw_extinf,
            tvg_id=tvg_id,
            tvg_name=tvg_name,
            tvg_logo=tvg_logo,
            group_title=group_title,
            channel_name=channel_name,
            source_url=source_url,
            protocol=protocol
        )
        meta_list.append(meta)
        channel_meta_cache[url] = meta
        
        # 按分类整理频道
        if group_title not in categorized_channels:
            categorized_channels[group_title] = []
        categorized_channels[group_title].append((channel_name, url))
    
    logger.info(f"M3U格式提取有效频道数：{len(meta_list)}（支持协议：{SUPPORTED_PROTOCOLS}）")
    return categorized_channels, meta_list

def extract_channels_from_content(content: str, source_url: str) -> OrderedDictType[str, List[Tuple[str, str]]]:
    """兼容解析M3U格式和自定义文本格式的直播源（支持多种直播协议）"""
    categorized_channels = OrderedDict()
    
    # 优先处理标准M3U格式
    if "#EXTM3U" in content:
        m3u_categorized, _ = extract_m3u_meta(content, source_url)
        categorized_channels = m3u_categorized
    else:
        # 处理自定义文本格式
        lines = content.split('\n')
        current_group = ""
        seen_urls = set()
        
        for line in lines:
            line = line.strip()
            
            # 识别分类行（注释中的分类标记）
            if not line or line.startswith(("//", "#", "/*", "*/")):
                if any(keyword in line.lower() for keyword in ['#分类', '#genre', '分类:', 'genre:', '==', '---']):
                    # 提取分类名称
                    group_match = re.search(r'[：:=](\S+)', line)
                    if group_match:
                        current_group = group_match.group(1).strip()
                    else:
                        current_group = re.sub(r'[#分类:genre:==\-—]', '', line).strip() or ""
                continue
            
            # 匹配"名称,URL"或"名称|URL"格式的行
            pattern = r'([^,|#$]+)[,|#$]\s*(' + '|'.join([p[:-3] for p in SUPPORTED_PROTOCOLS]) + r':\/\/[^\s,|#$]+)'
            matches = re.findall(pattern, line, re.IGNORECASE)
            
            if matches:
                for name, url in matches:
                    name = name.strip()
                    url = url.strip()
                    
                    # 过滤无效URL（已重复、非支持协议）
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    url_source_mapping[url] = source_url
                    
                    # 标准化频道名称和分类
                    standard_name = standardize_cctv_name(name)
                    group_title = clean_group_title(current_group, standard_name)
                    
                    # 提取协议类型（内部使用，不输出）
                    protocol = get_url_protocol(url)
                    
                    # 构造标准EXTINF行
                    raw_extinf = f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{standard_name}\" tvg-logo=\"\" group-title=\"{group_title}\",{standard_name}"
                    meta = ChannelMeta(
                        url=url,
                        raw_extinf=raw_extinf,
                        tvg_id="",
                        tvg_name=standard_name,
                        tvg_logo="",
                        group_title=group_title,
                        channel_name=standard_name,
                        source_url=source_url,
                        protocol=protocol
                    )
                    channel_meta_cache[url] = meta
                    
                    # 按分类整理频道
                    if group_title not in categorized_channels:
                        categorized_channels[group_title] = []
                    categorized_channels[group_title].append((standard_name, url))
        
        valid_channel_count = sum(len(v) for v in categorized_channels.values())
        logger.info(f"自定义文本格式提取有效频道数：{valid_channel_count}（支持协议：{SUPPORTED_PROTOCOLS}）")
    
    # 过滤空分类（无有效频道的分类）
    categorized_channels = OrderedDict([(k, v) for k, v in categorized_channels.items() if v])
    return categorized_channels

def merge_channels(target: OrderedDictType[str, List[Tuple[str, str]]], source: OrderedDictType[str, List[Tuple[str, str]]]):
    """合并多个来源的频道，仅按URL去重，保留所有有效分类和频道"""
    # 先收集目标字典中的所有URL（用于去重）
    url_set = set()
    for category_name, ch_list in target.items():
        for _, url in ch_list:
            url_set.add(url)
    
    # 遍历源字典，合并新频道（去重）
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
    :param demo_path: demo.txt文件路径
    :return: 有序字典，key=分类名称，value=该分类下允许的频道名称集合
    """
    demo_channel_mapping = OrderedDict()
    if not demo_path.exists():
        logger.warning(f"未找到demo.txt文件（路径：{demo_path.absolute()}），跳过筛选配对，保留所有频道")
        return demo_channel_mapping
    
    try:
        with open(demo_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
        
        current_category = None
        for line in lines:
            # 匹配分类行：┃分类名称,#genre#
            if line.startswith("┃") and ",#genre#" in line:
                # 提取分类名称（去除┃、,#genre#）
                current_category = line.replace("┃", "").replace(",#genre#", "").strip()
                if current_category and current_category not in demo_channel_mapping:
                    demo_channel_mapping[current_category] = set()  # 用集合存储，方便后续快速匹配
                continue
            
            # 匹配频道行：频道名称,（以逗号结尾，提取逗号前的频道名称）
            if current_category and line.endswith(","):
                channel_name = line[:-1].strip()  # 去除末尾逗号和前后空格
                if channel_name:
                    demo_channel_mapping[current_category].add(channel_name)
        
        # 过滤空分类（无有效频道的分类）
        demo_channel_mapping = OrderedDict([
            (cat, chan_set) for cat, chan_set in demo_channel_mapping.items()
            if chan_set
        ])
        
        logger.info(f"成功解析demo.txt：提取到 {len(demo_channel_mapping)} 个分类，共 {sum(len(s) for s in demo_channel_mapping.values())} 个允许的频道")
        for cat, chan_set in demo_channel_mapping.items():
            logger.debug(f"  - 【{cat}】：{list(chan_set)}")
        
    except Exception as e:
        logger.error(f"解析demo.txt失败，跳过筛选配对：{str(e)}", exc_info=True)
        demo_channel_mapping = OrderedDict()
    
    return demo_channel_mapping

def filter_channels_by_demo(all_channels: OrderedDictType[str, List[Tuple[str, str]]],
                           demo_mapping: OrderedDictType[str, Set[str]]) -> OrderedDictType[str, List[Tuple[str, str]]]:
    """
    根据demo.txt的映射关系，筛选符合条件的频道（仅保留demo中存在的分类和频道）
    :param all_channels: 原始合并后的所有频道
    :param demo_mapping: demo.txt解析后的「分类-频道名称」映射
    :return: 筛选后的有序频道字典
    """
    # 若demo_mapping为空（无demo.txt或解析失败），直接返回原始频道
    if not demo_mapping:
        return all_channels
    
    filtered_channels = OrderedDict()
    # 遍历demo.txt中的分类（保留demo的分类顺序）
    for demo_category, demo_channel_set in demo_mapping.items():
        # 遍历原始频道的所有分类，匹配频道名称（忽略分类名称差异，只匹配频道名）
        matched_channel_list = []
        seen_urls = set()  # 去重，避免同一频道重复匹配
        
        for original_category, original_channel_list in all_channels.items():
            for channel_name, url in original_channel_list:
                # 关键：频道名称匹配（demo中的频道名 与 原始频道名 精准匹配，忽略前后空格）
                standard_demo_channel_names = {name.strip() for name in demo_channel_set}
                standard_original_name = channel_name.strip()
                
                if (standard_original_name in standard_demo_channel_names 
                    and url not in seen_urls):
                    seen_urls.add(url)
                    matched_channel_list.append((channel_name, url))
        
        # 若该分类下有匹配到的频道，加入筛选结果（使用demo中的分类名称）
        if matched_channel_list:
            filtered_channels[demo_category] = matched_channel_list
    
    logger.info(f"筛选完成：保留 {len(filtered_channels)} 个分类，共 {sum(len(l) for l in filtered_channels.values())} 个频道（符合demo.txt规则）")
    return filtered_channels

# ===================== 生成输出文件 =====================
def generate_summary(all_channels: OrderedDictType[str, List[Tuple[str, str]]]):
    """生成汇总TXT文件和纯净版M3U文件（无协议标注，可直接导入播放器）"""
    if not all_channels:
        logger.warning("无有效频道可输出，跳过文件生成")
        return
    
    # 定义输出文件路径
    summary_path = OUTPUT_FOLDER / "live_source_summary.txt"
    m3u_path = OUTPUT_FOLDER / "live_source_merged.m3u"
    generate_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    total_channels = sum(len(ch_list) for _, ch_list in all_channels.items())
    total_categories = len(all_channels)
    
    try:
        # 生成易读的汇总TXT（可选保留协议标注，方便人工查看）
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("IPTV直播源汇总（自动提取+标准化+多协议支持+demo筛选）\n")
            f.write("="*80 + "\n")
            f.write(f"生成时间：{generate_time}\n")
            f.write(f"总频道数：{total_channels}\n")
            f.write(f"分类数：{total_categories}\n")
            f.write(f"支持协议：{', '.join([p[:-3].upper() for p in SUPPORTED_PROTOCOLS])}\n")
            f.write("="*80 + "\n\n")
            
            # 按分类写入频道详情
            for group_title, channel_list in all_channels.items():
                f.write(f"【{group_title}】（{len(channel_list)}个频道）\n")
                for idx, (name, url) in enumerate(channel_list, 1):
                    source = url_source_mapping.get(url, "未知来源")
                    protocol = get_url_protocol(url)
                    f.write(f"{idx:>3}. {name:<20} [{protocol}] {url}\n")
                    f.write(f"      来源：{source}\n")
                f.write("\n")
        
        # 生成纯净版M3U文件（无协议标注，优化解析兼容性）
        with open(m3u_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U x-tvg-url=\"\"\n")
            f.write(f"# IPTV直播源合并文件 | 生成时间：{generate_time}\n")
            f.write(f"# 总频道数：{total_channels} | 总分类数：{total_categories}（已按demo.txt筛选）\n\n")
            
            # 按分类写入M3U内容（无协议标注）
            for group_title, channel_list in all_channels.items():
                f.write(f"# ===== {group_title}（{len(channel_list)}个频道） =====\n")
                for name, url in channel_list:
                    meta = channel_meta_cache.get(url)
                    
                    if meta and meta.raw_extinf:
                        standard_extinf = meta.raw_extinf
                        # 确保分类名称为标准化后的名称（demo中的分类名称）
                        if 'group-title="' in standard_extinf:
                            start_idx = standard_extinf.find('group-title="') + len('group-title="')
                            end_idx = standard_extinf.find('"', start_idx)
                            if end_idx > start_idx:
                                standard_extinf = standard_extinf[:start_idx] + group_title + standard_extinf[end_idx:]
                        # 转义特殊字符，避免播放器解析异常（去除协议标注）
                        if ',' in standard_extinf:
                            extinf_part, old_name = standard_extinf.rsplit(',', 1)
                            safe_name = name.replace('\\', '\\\\').replace('$', '\\$')
                            standard_extinf = extinf_part + ',' + safe_name
                        f.write(standard_extinf + "\n")
                    else:
                        # 无元信息时构造默认EXTINF行（无协议标注）
                        safe_name = name.replace('\\', '\\\\').replace('$', '\\$')
                        f.write(f"#EXTINF:-1 tvg-name=\"{safe_name}\" group-title=\"{group_title}\",{safe_name}\n")
                    f.write(url + "\n\n")
        
        logger.info(f"文件生成完成：")
        logger.info(f"  - 汇总TXT：{summary_path.absolute()}")
        logger.info(f"  - 纯净版M3U：{m3u_path.absolute()}")
        
    except Exception as e:
        logger.error(f"生成输出文件失败：{str(e)}", exc_info=True)

# ===================== 主程序入口 =====================
def main():
    try:
        # 初始化全局缓存
        global channel_meta_cache, url_source_mapping
        channel_meta_cache = {}
        url_source_mapping = {}
        
        logger.info("="*60)
        logger.info("开始处理IPTV直播源（提取→标准化→合并→筛选→生成）")
        logger.info(f"支持的直播协议：{', '.join([p[:-3].upper() for p in SUPPORTED_PROTOCOLS])}")
        logger.info("="*60)
        
        # 从配置文件读取源URL列表
        source_urls = getattr(config, 'SOURCE_URLS', [])
        if not source_urls:
            logger.error("配置文件中未设置有效SOURCE_URLS，程序终止")
            return
        logger.info(f"读取到待处理的源URL数：{len(source_urls)}")
        
        # 初始化全局频道字典（保留顺序）
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
        
        # ---------------------- 新增：筛选配对功能 ----------------------
        # 1. 解析demo.txt，获取允许的频道映射
        demo_mapping = parse_demo_file(Path("demo.txt"))
        # 2. 根据demo.txt筛选频道
        filtered_channels = filter_channels_by_demo(all_channels, demo_mapping)
        # ----------------------------------------------------------------
        
        # 输出处理完成统计
        logger.info(f"\n===== 处理完成统计 =====")
        total_channels = sum(len(ch_list) for _, ch_list in filtered_channels.items())
        total_categories = len(filtered_channels)
        logger.info(f"  - 源URL总数：{len(source_urls)}")
        logger.info(f"  - 抓取失败源数：{len(failed_urls)}")
        logger.info(f"  - 最终有效频道数：{total_channels}（符合demo.txt规则）")
        logger.info(f"  - 最终有效分类数：{total_categories}")
        if filtered_channels:
            logger.info(f"  - 分类列表：{list(filtered_channels.keys())}")
        if failed_urls:
            logger.warning(f"  - 失败的源URL列表：{failed_urls}")
        
        # 生成输出文件（传入筛选后的频道）
        generate_summary(filtered_channels)
        
        logger.info("\n===== 所有操作执行完毕 =====")
        logger.info(f"输出文件存放目录：{OUTPUT_FOLDER.absolute()}")
        
    except Exception as e:
        logger.critical(f"程序运行过程中出现致命异常：{str(e)}", exc_info=True)

if __name__ == "__main__":
    main()
