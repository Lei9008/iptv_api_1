import re
import requests
import logging
import warnings
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set, OrderedDict as OrderedDictType
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

# ===================== 工具函数（修改：移除demo.txt相关逻辑） =====================
def clean_group_title(group_title: Optional[str], channel_name: Optional[str] = "") -> str:
    """
    清洗分类名称（不再依赖demo.txt，直接返回有效分类）
    """
    group_title = group_title or ""
    channel_name = channel_name or ""
    # 直接清洗分类名称：仅保留中文、字母、数字、下划线、括号
    final_title = ''.join(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9_\(\)]+', group_title.strip())).strip() or "未分类"
    # 限制长度，返回有效分类（默认"未分类"避免空分类）
    return final_title[:20] if final_title else "未分类"

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
    if channel_name in config.cntvNamesReverse:
        return config.cntvNamesReverse[channel_name]
    if channel_name in config.cctv_alias:
        return config.cctv_alias[channel_name]
    normalized_name = channel_name.strip()
    for raw_name, standard_name in config.cntvNamesReverse.items():
        if raw_name in normalized_name:
            return standard_name
    for alias_name, standard_name in config.cctv_alias.items():
        if alias_name in normalized_name:
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
    unique_urls = list(dict.fromkeys(candidate_urls + proxy_urls))
    return unique_urls[:5]

def fetch_url_with_retry(url: str, timeout: int = 15) -> Optional[str]:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    original_url = url
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
    logger.error(f"抓取失败：{original_url}")
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
        
        name_match = re.search(r',\s*(.+?)\s*$', raw_extinf)
        if name_match:
            channel_name = standardize_cctv_name(name_match.group(1).strip())
        
        # 清洗分类名称（不再过滤，直接返回有效分类）
        group_title = clean_group_title(group_title, channel_name)
        
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
        
        if group_title not in categorized_channels:
            categorized_channels[group_title] = []
        categorized_channels[group_title].append((channel_name, url))
    
    logger.info(f"M3U提取有效频道数：{len(meta_list)}")
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
            if not line or line.startswith(("//", "#", "/*", "*/")):
                if any(keyword in line.lower() for keyword in ['#分类', '#genre', '分类:', 'genre:', '==', '---']):
                    group_match = re.search(r'[：:=](\S+)', line)
                    if group_match:
                        current_group = group_match.group(1).strip()
                    else:
                        current_group = re.sub(r'[#分类:genre:==\-—]', '', line).strip() or ""
                continue
            
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
                    
                    # 清洗分类名称（不再过滤，直接返回有效分类）
                    group_title = clean_group_title(current_group, standard_name)
                    
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
                    
                    if group_title not in categorized_channels:
                        categorized_channels[group_title] = []
                    categorized_channels[group_title].append((standard_name, url))
        
        logger.info(f"智能提取有效频道数：{sum(len(v) for v in categorized_channels.values())}")
    
    # 过滤空分类
    categorized_channels = OrderedDict([(k, v) for k, v in categorized_channels.items() if v])
    return categorized_channels

def merge_channels(target: OrderedDictType[str, List[Tuple[str, str]]], source: OrderedDictType[str, List[Tuple[str, str]]]):
    """合并频道（移除demo.txt相关校验，仅去重）"""
    url_set = set()
    for category_name, ch_list in target.items():
        for _, url in ch_list:
            url_set.add(url)
    
    # 遍历所有源分类，直接合并（不去除任何分类）
    for category_name, ch_list in source.items():
        if category_name not in target:
            target[category_name] = []
        for name, url in ch_list:
            if url not in url_set:  # 仅去重，无其他校验
                target[category_name].append((name, url))
                url_set.add(url)

# ===================== 生成文件（修改：移除demo.txt相关逻辑） =====================
def generate_summary(all_channels: OrderedDictType[str, List[Tuple[str, str]]]):
    """生成汇总文件（包含所有有效频道，无demo.txt过滤）"""
    if not all_channels:
        logger.warning("无有效频道，跳过生成文件")
        return
    
    summary_path = OUTPUT_FOLDER / "live_source_summary.txt"
    m3u_path = OUTPUT_FOLDER / "live_source_merged.m3u"
    
    try:
        # 生成汇总TXT（包含所有分类和频道）
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("IPTV直播源汇总（所有有效频道）\n")
            f.write("="*80 + "\n")
            f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"总频道数：{sum(len(ch_list) for _, ch_list in all_channels.items())}\n")
            f.write(f"分类数：{len(all_channels)}\n")
            f.write("="*80 + "\n\n")
            
            # 遍历所有提取到的分类（按抓取顺序）
            for group_title, channel_list in all_channels.items():
                f.write(f"【{group_title}】（{len(channel_list)}个频道）\n")
                for idx, (name, url) in enumerate(channel_list, 1):
                    source = url_source_mapping.get(url, "未知来源")
                    f.write(f"{idx:>3}. {name:<20} {url}\n")
                    f.write(f"      来源：{source}\n")
                f.write("\n")
        
        # 生成M3U文件（包含所有有效频道）
        with open(m3u_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U x-tvg-url=\"\"\n")
            f.write(f"# 所有有效直播源 | 按抓取分类顺序排列\n")
            f.write(f"# 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 总频道数：{sum(len(ch_list) for _, ch_list in all_channels.items())}\n\n")
            
            # 遍历所有分类写入M3U
            for group_title, channel_list in all_channels.items():
                f.write(f"# ===== {group_title}（{len(channel_list)}个频道） =====\n")
                for name, url in channel_list:
                    meta = channel_meta_cache.get(url)
                    if meta and meta.raw_extinf:
                        standard_extinf = meta.raw_extinf
                        if 'group-title="' in standard_extinf:
                            start_idx = standard_extinf.find('group-title="') + len('group-title="')
                            end_idx = standard_extinf.find('"', start_idx)
                            if end_idx > start_idx:
                                standard_extinf = standard_extinf[:start_idx] + group_title + standard_extinf[end_idx:]
                        if ',' in standard_extinf:
                            extinf_part, old_name = standard_extinf.rsplit(',', 1)
                            safe_name = name.replace('\\', '\\\\').replace('$', '\\$')
                            standard_extinf = extinf_part + ',' + safe_name
                        f.write(standard_extinf + "\n")
                    else:
                        f.write(f"#EXTINF:-1 tvg-name=\"{name}\" group-title=\"{group_title}\",{name}\n")
                    f.write(url + "\n\n")
        
        logger.info(f"文件生成完成：")
        logger.info(f"  - 汇总TXT：{summary_path}")
        logger.info(f"  - 合并M3U：{m3u_path}")
        
    except Exception as e:
        logger.error(f"生成文件失败：{str(e)}", exc_info=True)

# ===================== 主程序（修改：移除demo.txt相关初始化和排序） =====================
def main():
    try:
        global channel_meta_cache, url_source_mapping
        channel_meta_cache = {}
        url_source_mapping = {}
        logger.info("===== 开始处理直播源（提取所有有效频道） =====")
        
        source_urls = getattr(config, 'SOURCE_URLS', [])
        if not source_urls:
            logger.error("未配置SOURCE_URLS，程序终止")
            return
        logger.info(f"读取源URL数：{len(source_urls)}")
        
        all_channels = OrderedDict()
        failed_urls = []
        
        for idx, url in enumerate(source_urls, 1):
            logger.info(f"\n===== 处理第 {idx}/{len(source_urls)} 个源：{url} =====")
            content = fetch_url_with_retry(url)
            if content is None:
                failed_urls.append(url)
                continue
            content = global_replace_cctv_name(content)
            extracted_channels = extract_channels_from_content(content, url)
            merge_channels(all_channels, extracted_channels)
        
        # 移除demo顺序整理，直接使用合并后的所有频道
        final_channels = all_channels
        
        # 统计结果（移除demo相关统计）
        total_channels = sum(len(ch_list) for _, ch_list in final_channels.items())
        logger.info(f"\n===== 处理完成统计 =====")
        logger.info(f"  - 源URL总数：{len(source_urls)}")
        logger.info(f"  - 失败源数：{len(failed_urls)}")
        logger.info(f"  - 有效频道数：{total_channels}")
        logger.info(f"  - 有效分类数：{len(final_channels)}")
        logger.info(f"  - 分类列表：{list(final_channels.keys())}")
        
        # 生成文件
        generate_summary(final_channels)
        logger.info("\n===== 所有操作完成 =====")
    except Exception as e:
        logger.critical(f"程序异常：{str(e)}", exc_info=True)

if __name__ == "__main__":
    main()
