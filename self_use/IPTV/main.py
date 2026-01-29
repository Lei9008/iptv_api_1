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
    # 新增：完整EXTINF哈希字段，用于精准去重
    extinf_signature: str = ""

channel_meta_cache: Dict[str, ChannelMeta] = {}
url_source_mapping: Dict[str, str] = {}
# 新增：EXTINF签名缓存，用于优先按EXTINF去重
extinf_signature_cache: Set[str] = set()

# ===================== 工具函数（核心优化：EXTINF提取与去重） =====================
def clean_group_title(group_title: Optional[str], channel_name: Optional[str] = "") -> str:
    """
    清洗分类名称（直接返回有效分类，默认"未分类"）
    """
    group_title = group_title or ""
    channel_name = channel_name or ""
    # 直接清洗分类名称：仅保留中文、字母、数字、下划线、括号
    final_title = ''.join(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9_\(\)]+', group_title.strip())).strip() or "未分类"
    # 限制长度，返回有效分类（默认"未分类"避免空分类）
    return final_title[:20] if final_title else "未分类"

def generate_extinf_signature(meta: ChannelMeta) -> str:
    """
    生成EXTINF签名（用于精准去重）
    包含核心字段：tvg-id、tvg-name、tvg-logo、group-title
    """
    signature_parts = [
        meta.tvg_id or "",
        meta.tvg_name or "",
        meta.tvg_logo or "",
        meta.group_title or ""
    ]
    return "|".join([part.strip() for part in signature_parts])

def parse_extinf_priority(extinf_line: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    优先提取EXTINF字段，优先级：tvg-name > group-title > tvg-id > tvg-logo > 频道名称
    返回：(tvg_id, tvg_name, tvg_logo, group_title, channel_name)
    """
    if not extinf_line:
        return (None, None, None, None, None)
    
    # 预编译正则（优先匹配核心字段）
    tvg_id_pattern = re.compile(r'tvg-id="([^"]+)"', re.IGNORECASE)
    tvg_name_pattern = re.compile(r'tvg-name="([^"]+)"', re.IGNORECASE)
    tvg_logo_pattern = re.compile(r'tvg-logo="([^"]+)"', re.IGNORECASE)
    group_title_pattern = re.compile(r'group-title="([^"]+)"', re.IGNORECASE)
    channel_name_pattern = re.compile(r',\s*([^#\n\r]+)$', re.IGNORECASE)
    
    # 1. 优先提取核心字段（tvg-name、group-title）
    tvg_name = tvg_name_pattern.search(extinf_line)
    group_title = group_title_pattern.search(extinf_line)
    
    # 2. 提取扩展字段（tvg-id、tvg-logo）
    tvg_id = tvg_id_pattern.search(extinf_line)
    tvg_logo = tvg_logo_pattern.search(extinf_line)
    
    # 3. 提取频道名称（EXTINF末尾逗号后内容）
    channel_name = channel_name_pattern.search(extinf_line)
    
    # 格式化返回结果
    return (
        tvg_id.group(1).strip() if tvg_id else None,
        tvg_name.group(1).strip() if tvg_name else None,
        tvg_logo.group(1).strip() if tvg_logo else None,
        group_title.group(1).strip() if group_title else None,
        channel_name.group(1).strip() if channel_name else None
    )

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
    categorized_channels = OrderedDict()
    meta_list = []
    seen_urls = set()
    
    matches = m3u_pattern.findall(content)
    logger.info(f"M3U匹配条目数：{len(matches)}")
    
    for raw_extinf, url in matches:
        url = url.strip()
        raw_extinf = raw_extinf.strip()
        
        # 基础过滤：无效URL跳过
        if not url or not url.startswith(("http://", "https://")):
            continue
        
        # 1. 优先解析EXTINF字段（按优先级提取）
        tvg_id, tvg_name, tvg_logo, group_title, channel_name = parse_extinf_priority(raw_extinf)
        
        # 2. 标准化频道名称和分类（补全缺失值）
        channel_name = standardize_cctv_name(channel_name) or tvg_name or "未知频道"
        tvg_name = tvg_name or channel_name  # 核心字段补全：tvg-name缺失用频道名称填充
        group_title = clean_group_title(group_title, channel_name)
        
        # 3. 构建ChannelMeta并生成EXTINF签名（用于精准去重）
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
        meta.extinf_signature = generate_extinf_signature(meta)
        
        # 4. 优化去重：先按EXTINF签名去重，再按URL去重
        if meta.extinf_signature in extinf_signature_cache or url in seen_urls:
            logger.debug(f"重复频道跳过：{channel_name}（签名/URL已存在）")
            continue
        extinf_signature_cache.add(meta.extinf_signature)
        seen_urls.add(url)
        url_source_mapping[url] = source_url
        
        # 5. 缓存并整理分类
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
                    
                    # 标准化信息，补全EXTINF核心字段
                    standard_name = standardize_cctv_name(name) or "未知频道"
                    group_title = clean_group_title(current_group, standard_name)
                    
                    # 构建模拟EXTINF（普通文本格式补全核心字段）
                    raw_extinf = f"#EXTINF:-1 tvg-name=\"{standard_name}\" group-title=\"{group_title}\",{standard_name}"
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
                    meta.extinf_signature = generate_extinf_signature(meta)
                    
                    # 去重：先EXTINF签名，再URL
                    if meta.extinf_signature in extinf_signature_cache or url in seen_urls:
                        logger.debug(f"重复频道跳过：{standard_name}（签名/URL已存在）")
                        continue
                    extinf_signature_cache.add(meta.extinf_signature)
                    seen_urls.add(url)
                    url_source_mapping[url] = source_url
                    
                    # 缓存并整理分类
                    channel_meta_cache[url] = meta
                    if group_title not in categorized_channels:
                        categorized_channels[group_title] = []
                    categorized_channels[group_title].append((standard_name, url))
        
        logger.info(f"智能提取有效频道数：{sum(len(v) for v in categorized_channels.values())}")
    
    # 过滤空分类
    categorized_channels = OrderedDict([(k, v) for k, v in categorized_channels.items() if v])
    return categorized_channels

def merge_channels(target: OrderedDictType[str, List[Tuple[str, str]]], source: OrderedDictType[str, List[Tuple[str, str]]]):
    """合并频道（优先按EXTINF签名去重，再按URL去重）"""
    # 构建当前目标的URL和EXTINF签名缓存
    current_urls = set()
    current_extinf_signatures = set()
    for category_name, ch_list in target.items():
        for _, url in ch_list:
            current_urls.add(url)
            meta = channel_meta_cache.get(url)
            if meta:
                current_extinf_signatures.add(meta.extinf_signature)
    
    # 遍历所有源分类，进行合并
    for category_name, ch_list in source.items():
        if category_name not in target:
            target[category_name] = []
        for name, url in ch_list:
            meta = channel_meta_cache.get(url)
            if not meta:
                continue
            # 双重去重：EXTINF签名 + URL
            if meta.extinf_signature in current_extinf_signatures or url in current_urls:
                continue
            target[category_name].append((name, url))
            current_urls.add(url)
            current_extinf_signatures.add(meta.extinf_signature)

# ===================== 生成文件 =====================
def generate_summary(all_channels: OrderedDictType[str, List[Tuple[str, str]]]):
    """生成汇总文件（包含所有有效频道，优先保留完整EXTINF信息）"""
    if not all_channels:
        logger.warning("无有效频道，跳过生成文件")
        return
    
    summary_path = OUTPUT_FOLDER / "live_source_summary.txt"
    m3u_path = OUTPUT_FOLDER / "live_source_merged.m3u"
    
    try:
        # 生成汇总TXT（包含所有分类和频道）
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("IPTV直播源汇总（所有有效频道，优先保留EXTINF完整信息）\n")
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
                    meta = channel_meta_cache.get(url)
                    extinf_info = meta.extinf_signature if meta else "未知EXTINF信息"
                    f.write(f"{idx:>3}. {name:<20} {url}\n")
                    f.write(f"      来源：{source}\n")
                    f.write(f"      EXTINF信息：{extinf_info}\n")
                f.write("\n")
        
        # 生成M3U文件（包含所有有效频道，还原完整EXTINF）
        with open(m3u_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U x-tvg-url=\"\"\n")
            f.write(f"# 所有有效直播源 | 优先保留EXTINF完整信息（tvg-name/group-title/tvg-id/tvg-logo）\n")
            f.write(f"# 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 总频道数：{sum(len(ch_list) for _, ch_list in all_channels.items())}\n\n")
            
            # 遍历所有分类写入M3U
            for group_title, channel_list in all_channels.items():
                f.write(f"# ===== {group_title}（{len(channel_list)}个频道） =====\n")
                for name, url in channel_list:
                    meta = channel_meta_cache.get(url)
                    if meta and meta.raw_extinf:
                        # 优先使用原始EXTINF，确保信息完整
                        standard_extinf = meta.raw_extinf
                        # 补全group-title（确保分类一致）
                        if 'group-title="' in standard_extinf:
                            start_idx = standard_extinf.find('group-title="') + len('group-title="')
                            end_idx = standard_extinf.find('"', start_idx)
                            if end_idx > start_idx:
                                standard_extinf = standard_extinf[:start_idx] + group_title + standard_extinf[end_idx:]
                        # 补全频道名称（确保显示一致）
                        if ',' in standard_extinf:
                            extinf_part, old_name = standard_extinf.rsplit(',', 1)
                            safe_name = name.replace('\\', '\\\\').replace('$', '\\$')
                            standard_extinf = extinf_part + ',' + safe_name
                        f.write(standard_extinf + "\n")
                    else:
                        # 模拟完整EXTINF，优先填充核心字段
                        f.write(f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{name}\" tvg-logo=\"\" group-title=\"{group_title}\",{name}\n")
                    f.write(url + "\n\n")
        
        logger.info(f"文件生成完成：")
        logger.info(f"  - 汇总TXT：{summary_path}")
        logger.info(f"  - 合并M3U：{m3u_path}")
        
    except Exception as e:
        logger.error(f"生成文件失败：{str(e)}", exc_info=True)

# ===================== 主程序 =====================
def main():
    try:
        global channel_meta_cache, url_source_mapping, extinf_signature_cache
        channel_meta_cache = {}
        url_source_mapping = {}
        extinf_signature_cache = set()  # 初始化EXTINF签名缓存
        logger.info("===== 开始处理直播源（优先提取EXTINF核心字段，精准去重） =====")
        
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
        
        # 直接使用合并后的所有频道
        final_channels = all_channels
        
        # 统计结果
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
