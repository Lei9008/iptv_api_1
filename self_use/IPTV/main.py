import re
import requests
import logging
import warnings
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set, OrderedDict as OrderedDictType

# 注意：需确保存在config.py文件，包含对应的配置项
import config
import os

# ===================== 基础配置 =====================
warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)
OUTPUT_FOLDER = Path("output")
OUTPUT_FOLDER.mkdir(exist_ok=True)

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

# ===================== 全局变量（demo.txt映射+顺序+所有频道） =====================
demo_channel_to_group: Dict[str, str] = {}  # 频道→分类
demo_all_groups: Set[str] = set()           # 所有分类
demo_group_order: List[str] = []            # demo.txt中的分类顺序
demo_all_channels: Set[str] = set()         # 新增：存储demo.txt中所有频道，用于快速校验是否存在

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

channel_meta_cache: Dict[str, ChannelMeta] = {}
url_source_mapping: Dict[str, str] = {}

# ===================== 核心优化：解析demo.txt并保存分类顺序+所有频道 =====================
def parse_demo_txt() -> Tuple[Dict[str, str], Set[str], List[str], Set[str]]:
    """
    解析demo.txt，返回：
    - 频道→分类映射
    - 所有分类集合
    - 分类顺序列表（严格按demo.txt中的顺序）
    - 所有频道集合（新增）
    """
    channel_to_group = {}
    all_groups = set()
    group_order = []
    all_channels = set()  # 新增：存储所有demo中的频道
    demo_path = Path(config.DEMO_TXT_PATH)
    
    if not demo_path.exists():
        logger.error(f"demo.txt文件不存在：{demo_path.absolute()}")
        return channel_to_group, all_groups, group_order, all_channels
    
    try:
        with open(demo_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        
        current_group = None
        for line in lines:
            # 匹配分类行
            if line.startswith("┃") and ",#genre#" in line:
                current_group = line.replace("┃", "").replace(",#genre#", "").strip()
                if current_group and current_group not in all_groups:
                    all_groups.add(current_group)
                    group_order.append(current_group)  # 保存分类顺序
                    logger.debug(f"demo.txt分类（顺序{len(group_order)}）：{current_group}")
                continue
            # 匹配频道行
            if current_group and line:
                channel_name = line.rstrip(",").strip()
                if channel_name:
                    channel_to_group[channel_name] = current_group
                    all_channels.add(channel_name)  # 新增：将频道加入集合，用于后续校验
                    logger.debug(f"demo.txt映射：{channel_name} → {current_group}")
        
        logger.info(f"demo.txt解析完成：{len(group_order)}个分类（按顺序），{len(channel_to_group)}个频道映射，{len(all_channels)}个有效频道")
    except Exception as e:
        logger.error(f"解析demo.txt失败：{str(e)}", exc_info=True)
    
    return channel_to_group, all_groups, group_order, all_channels

# 初始化demo映射（包含顺序+所有频道）
demo_channel_to_group, demo_all_groups, demo_group_order, demo_all_channels = parse_demo_txt()

# ===================== 工具函数（核心强化：严格校验demo频道） =====================
def clean_group_title(group_title: Optional[str], channel_name: Optional[str] = "") -> str:
    """
    强化过滤：
    1. 先标准化分类名（基于config中的group_title_reverse_mapping）
    2. 仅保留demo.txt中明确存在的频道对应的分类
    非demo频道直接返回空，后续过滤丢弃
    """
    group_title = group_title or ""
    channel_name = channel_name or ""
    original_title = group_title.strip()
    result_title = original_title

    # 步骤1：分类名标准化（基于config中的映射）
    if original_title in config.group_title_reverse_mapping:
        result_title = config.group_title_reverse_mapping[original_title]
        logger.debug(f"分类名标准化：{original_title} → {result_title}")
    # 模糊匹配（可选，提升匹配率）
    else:
        for original, target in config.group_title_reverse_mapping.items():
            if original in original_title:
                result_title = target
                logger.debug(f"分类名模糊标准化：{original_title} → {result_title}（匹配{original}）")
                break

    # 步骤2：强化三重校验：1.频道名非空 2.频道在demo.txt的频道列表中 3.频道有对应分类
    if channel_name and channel_name in demo_all_channels and channel_name in demo_channel_to_group:
        # 最终以demo.txt中的分类为准（核心规则，不改变）
        final_demo_group = demo_channel_to_group[channel_name]
        logger.debug(f"demo匹配通过：{channel_name} → {final_demo_group}")
        # 过滤非法字符，截断长度避免异常
        final_title = ''.join(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9_\(\)]+', final_demo_group)).strip() or ""
        return final_title[:20] if final_title else ""

    # 非demo匹配的内容返回空（后续过滤），增加日志记录丢弃原因
    if channel_name:
        if channel_name not in demo_all_channels:
            logger.debug(f"非demo频道，直接丢弃：{channel_name}（未在demo.txt中定义）")
        else:
            logger.debug(f"频道无对应分类，直接丢弃：{channel_name}")
    return ""

def global_replace_cctv_name(content: str) -> str:
    if not content:
        return content
    all_mappings = {}
    all_mappings.update(config.cntvNamesReverse)
    all_mappings.update(config.cctv_alias)
    sorted_mappings = sorted(all_mappings.items(), key=lambda x: (-len(x[0]), x[0]))
    replaced_content = content
    for old_name, new_name in sorted_mappings:
        if old_name in replaced_content:
            replaced_content = replaced_content.replace(old_name, new_name)
    return replaced_content

def standardize_cctv_name(channel_name: Optional[str]) -> str:
    if not channel_name:
        return ""
    channel_name = channel_name.strip()
    if channel_name in config.cntvNamesReverse:
        return config.cntvNamesReverse[channel_name]
    if channel_name in config.cctv_alias:
        return config.cctv_alias[channel_name]
    # 模糊匹配标准化
    for raw_name, standard_name in config.cntvNamesReverse.items():
        if raw_name in channel_name:
            return standard_name
    for alias_name, standard_name in config.cctv_alias.items():
        if alias_name in channel_name:
            return standard_name
    return channel_name

def replace_github_domain(url: str) -> List[str]:
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
    # 去重并限制数量，提高抓取效率
    unique_urls = list(dict.fromkeys(candidate_urls + proxy_urls))
    return unique_urls[:5]

def fetch_url_with_retry(url: str, timeout: int = 15) -> Optional[str]:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    original_url = url
    # 转换GitHub blob地址为raw地址，提高抓取成功率
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    candidate_urls = replace_github_domain(url)
    timeouts = [5, 10, 15, 15, 15]
    
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
        except requests.RequestException as e:
            logger.warning(f"抓取失败 [{idx+1}/{len(candidate_urls)}]: {candidate} | {str(e)[:50]}")
            continue
    logger.error(f"所有候选地址均抓取失败：{original_url}")
    return None

def extract_m3u_meta(content: str, source_url: str) -> Tuple[OrderedDictType[str, List[Tuple[str, str]]], List[ChannelMeta]]:
    m3u_pattern = re.compile(
        r"(#EXTINF:-?\d+.*?)\n\s*([^#\n\r\s].*?)(?=\s|#|$)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE
    )
    attr_pattern = re.compile(r'(\w+)-(\w+)="([^"]*)"')
    categorized_channels = OrderedDict()
    meta_list = []
    seen_urls = set()
    matches = m3u_pattern.findall(content)
    logger.info(f"M3U匹配条目数：{len(matches)}")
    
    for raw_extinf, url in matches:
        url = url.strip()
        raw_extinf = raw_extinf.strip()
        # 过滤无效URL和重复URL
        if not url or not url.startswith(("http://", "https://")) or url in seen_urls:
            continue
        seen_urls.add(url)
        url_source_mapping[url] = source_url
        
        tvg_id, tvg_name, tvg_logo, group_title = None, None, None, None
        channel_name = ""
        attr_matches = attr_pattern.findall(raw_extinf)
        
        for attr1, attr2, value in attr_matches:
            if attr1 == "tvg" and attr2 == "id":
                tvg_id = value
            elif attr1 == "tvg" and attr2 == "name":
                tvg_name = standardize_cctv_name(value)
            elif attr1 == "tvg" and attr2 == "logo":
                tvg_logo = value
            elif attr1 == "group" and attr2 == "title":
                group_title = value
        
        # 提取频道名并标准化
        name_match = re.search(r',\s*(.+?)\s*$', raw_extinf)
        if name_match:
            channel_name = standardize_cctv_name(name_match.group(1).strip())
        
        # 标准化分类（严格过滤，仅保留demo匹配频道）
        group_title = clean_group_title(group_title, channel_name)
        if not group_title:  # 无demo匹配，跳过该频道
            continue
        
        # 封装频道元数据并缓存
        meta = ChannelMeta(
            url=url,
            raw_extinf=raw_extinf,
            tvg_id=tvg_id,
            tvg_name=tvg_name,
            tvg_logo=tvg_logo,
            group_title=group_title,
            channel_name=channel_name,
            source_url=source_url
        )
        meta_list.append(meta)
        channel_meta_cache[url] = meta
        
        # 按分类整理频道
        if group_title not in categorized_channels:
            categorized_channels[group_title] = []
        categorized_channels[group_title].append((channel_name, url))
    
    logger.info(f"M3U提取有效demo频道数：{len(meta_list)}")
    return categorized_channels, meta_list

def extract_channels_from_content(content: str, source_url: str) -> OrderedDictType[str, List[Tuple[str, str]]]:
    categorized_channels = OrderedDict()
    if "#EXTM3U" in content:
        m3u_categorized, _ = extract_m3u_meta(content, source_url)
        categorized_channels = m3u_categorized
    else:
        lines = content.split('\n')
        current_group = ""
        seen_urls = set()
        for line in lines:
            line = line.strip()
            # 解析分类行
            if not line or line.startswith(("//", "#", "/*", "*/")):
                if any(keyword in line.lower() for keyword in ['#分类', '#genre', '分类:', 'genre:', '==', '---']):
                    group_match = re.search(r'[：:=](\S+)', line)
                    if group_match:
                        current_group = group_match.group(1).strip()
                    else:
                        current_group = re.sub(r'[#分类:genre:==\-—]', '', line).strip() or ""
                continue
            
            # 解析频道行
            pattern = r'([^,|#$]+)[,|#$]\s*(https?://[^\s,|#$]+)'
            matches = re.findall(pattern, line, re.IGNORECASE)
            if matches:
                for name, url in matches:
                    name = name.strip()
                    url = url.strip()
                    if not url or url in seen_urls:
                        continue
                    standard_name = standardize_cctv_name(name)
                    seen_urls.add(url)
                    url_source_mapping[url] = source_url
                    
                    # 标准化分类（严格过滤，仅保留demo匹配频道）
                    group_title = clean_group_title(current_group, standard_name)
                    if not group_title:  # 无demo匹配，跳过
                        continue
                    
                    # 封装频道元数据并缓存
                    raw_extinf = f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{standard_name}\" tvg-logo=\"\" group-title=\"{group_title}\",{standard_name}"
                    meta = ChannelMeta(
                        url=url,
                        raw_extinf=raw_extinf,
                        tvg_id="",
                        tvg_name=standard_name,
                        tvg_logo="",
                        group_title=group_title,
                        channel_name=standard_name,
                        source_url=source_url
                    )
                    channel_meta_cache[url] = meta
                    
                    # 按分类整理频道
                    if group_title not in categorized_channels:
                        categorized_channels[group_title] = []
                    categorized_channels[group_title].append((standard_name, url))
        
        logger.info(f"智能提取有效demo频道数：{sum(len(v) for v in categorized_channels.values())}")
    
    # 过滤空分类，保证数据整洁
    categorized_channels = OrderedDict([(k, v) for k, v in categorized_channels.items() if v])
    return categorized_channels

def merge_channels(target: OrderedDictType[str, List[Tuple[str, str]]], source: OrderedDictType[str, List[Tuple[str, str]]]):
    """
    合并频道并仅保留demo.txt中的分类和频道（双重保险强化）
    """
    url_set = set()
    # 先记录已存在的URL，避免重复
    for category_name, ch_list in target.items():
        for _, url in ch_list:
            url_set.add(url)
    
    # 仅处理demo.txt中的分类
    for category_name in demo_all_groups:
        if category_name not in source:
            continue
        if category_name not in target:
            target[category_name] = []
        for name, url in source[category_name]:
            # 强化校验：url未重复 + 频道在demo.txt中明确存在
            if url not in url_set and name in demo_all_channels:
                target[category_name].append((name, url))
                url_set.add(url)
                logger.debug(f"合并有效demo频道：{name} → {category_name}")

# ===================== 核心：按demo顺序整理并过滤频道 =====================
def reorder_by_demo(all_channels: OrderedDictType[str, List[Tuple[str, str]]]) -> OrderedDictType[str, List[Tuple[str, str]]]:
    """
    按demo.txt的分类顺序重新整理频道：
    1. 仅保留demo.txt中定义的分类
    2. 严格按demo.txt的分类顺序排列
    3. 过滤空分类
    """
    ordered_channels = OrderedDict()
    
    # 严格按demo.txt的分类顺序遍历，保证输出顺序一致
    for group in demo_group_order:
        if group in all_channels and all_channels[group]:  # 仅保留有内容的分类
            ordered_channels[group] = all_channels[group]
            logger.debug(f"按demo顺序添加分类：{group}（{len(all_channels[group])}个有效频道）")
    
    logger.info(f"按demo顺序整理后分类数：{len(ordered_channels)}")
    return ordered_channels

# ===================== 核心：生成文件（仅保留demo匹配内容+按顺序） =====================
def generate_summary(all_channels: OrderedDictType[str, List[Tuple[str, str]]]):
    """生成按demo.txt顺序排列、仅保留匹配内容的汇总文件"""
    # 先按demo顺序整理频道
    ordered_channels = reorder_by_demo(all_channels)
    if not ordered_channels:
        logger.warning("无demo.txt匹配的有效频道，跳过生成文件")
        return
    
    summary_path = OUTPUT_FOLDER / "live_source_summary.txt"
    m3u_path = OUTPUT_FOLDER / "live_source_merged.m3u"
    
    try:
        # 生成汇总TXT（按demo顺序，包含详细统计信息）
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("IPTV直播源汇总（仅保留demo.txt明确定义的频道+按demo顺序）\n")
            f.write("="*80 + "\n")
            f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"有效demo频道数：{sum(len(ch_list) for _, ch_list in ordered_channels.items())}\n")
            f.write(f"有效分类数：{len(ordered_channels)}\n")
            f.write(f"demo.txt分类总数：{len(demo_group_order)}\n")
            f.write(f"demo.txt频道总数：{len(demo_all_channels)}\n")
            f.write("="*80 + "\n\n")
            
            # 严格按demo顺序写入每个分类的频道
            for group_title, channel_list in ordered_channels.items():
                f.write(f"【{group_title}】（{len(channel_list)}个频道）\n")
                for idx, (name, url) in enumerate(channel_list, 1):
                    source = url_source_mapping.get(url, "未知来源")
                    f.write(f"{idx:>3}. {name:<20} {url}\n")
                    f.write(f"      来源：{source}\n")
                f.write("\n")
        
        # 生成M3U文件（按demo顺序，可直接导入IPTV播放器）
        with open(m3u_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U x-tvg-url=\"\"\n")
            f.write(f"# 仅保留demo.txt明确定义的频道 | 按demo.txt分类顺序排列\n")
            f.write(f"# 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 有效demo频道数：{sum(len(ch_list) for _, ch_list in ordered_channels.items())}\n\n")
            
            # 严格按demo顺序写入每个分类的频道
            for group_title, channel_list in ordered_channels.items():
                f.write(f"# ===== {group_title}（{len(channel_list)}个频道） =====\n")
                for name, url in channel_list:
                    meta = channel_meta_cache.get(url)
                    if meta and meta.raw_extinf:
                        standard_extinf = meta.raw_extinf
                        # 确保group-title为demo.txt中定义的分类
                        if 'group-title="' in standard_extinf:
                            start_idx = standard_extinf.find('group-title="') + len('group-title="')
                            end_idx = standard_extinf.find('"', start_idx)
                            if end_idx > start_idx:
                                standard_extinf = standard_extinf[:start_idx] + group_title + standard_extinf[end_idx:]
                        # 确保频道名标准化且格式安全
                        if ',' in standard_extinf:
                            extinf_part, old_name = standard_extinf.rsplit(',', 1)
                            safe_name = name.replace('\\', '\\\\').replace('$', '\\$')
                            standard_extinf = extinf_part + ',' + safe_name
                        f.write(standard_extinf + "\n")
                    else:
                        f.write(f"#EXTINF:-1 tvg-name=\"{name}\" group-title=\"{group_title}\",{name}\n")
                    f.write(url + "\n\n")
        
        logger.info(f"文件生成完成：")
        logger.info(f"  - 汇总TXT：{summary_path.absolute()}")
        logger.info(f"  - 合并M3U：{m3u_path.absolute()}")
        
    except Exception as e:
        logger.error(f"生成文件失败：{str(e)}", exc_info=True)

# ===================== 主程序 =====================
def main():
    try:
        global channel_meta_cache, url_source_mapping
        # 初始化缓存，避免多次运行时数据残留
        channel_meta_cache = {}
        url_source_mapping = {}
        logger.info("===== 开始处理直播源（仅保留demo.txt明确定义的频道） =====")
        
        # 读取配置的源URL列表
        source_urls = getattr(config, 'SOURCE_URLS', [])
        if not source_urls:
            logger.error("未配置SOURCE_URLS，程序终止")
            return
        logger.info(f"读取源URL数：{len(source_urls)}")
        
        all_channels = OrderedDict()
        failed_urls = []
        
        # 遍历每个源URL，逐个处理
        for idx, url in enumerate(source_urls, 1):
            logger.info(f"\n===== 处理第 {idx}/{len(source_urls)} 个源：{url} =====")
            content = fetch_url_with_retry(url)
            if content is None:
                failed_urls.append(url)
                continue
            # 全局替换CCTV频道名，提高匹配率
            content = global_replace_cctv_name(content)
            # 提取有效demo频道
            extracted_channels = extract_channels_from_content(content, url)
            # 合并到全局频道字典
            merge_channels(all_channels, extracted_channels)
        
        # 按demo顺序整理最终频道列表
        final_channels = reorder_by_demo(all_channels)
        
        # 输出处理结果统计
        total_channels = sum(len(ch_list) for _, ch_list in final_channels.items())
        logger.info(f"\n===== 处理完成统计 =====")
        logger.info(f"  - 源URL总数：{len(source_urls)}")
        logger.info(f"  - 失败源数：{len(failed_urls)}")
        logger.info(f"  - 有效demo频道数：{total_channels}")
        logger.info(f"  - 有效demo分类数：{len(final_channels)}")
        logger.info(f"  - 最终分类顺序：{list(final_channels.keys())}")
        
        # 生成最终文件
        generate_summary(final_channels)
        logger.info("\n===== 所有操作完成 =====")
        
    except Exception as e:
        logger.critical(f"程序异常终止：{str(e)}", exc_info=True)

if __name__ == "__main__":
    main()

