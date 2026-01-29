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
    "https://ghfast.top/",  # 新增：补充可用的GitHub代理（原文档中有效）
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
    extinf_signature: str = ""  # 用于精准去重的EXTINF签名

channel_meta_cache: Dict[str, ChannelMeta] = {}
url_source_mapping: Dict[str, str] = {}
extinf_signature_cache: Set[str] = set()  # EXTINF签名缓存（去重用）

# ===================== 工具函数 =====================
def clean_group_title(group_title: Optional[str], channel_name: Optional[str] = "") -> str:
    """清洗分类名称，默认返回"未分类""""
    group_title = group_title or ""
    # 仅保留中文、字母、数字、下划线、括号，限制长度20
    final_title = ''.join(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9_\(\)]+', group_title.strip())).strip()
    return final_title[:20] if final_title else "未分类"

def generate_extinf_signature(meta: ChannelMeta) -> str:
    """生成EXTINF签名（tvg-id + tvg-name + tvg-logo + group-title），用于去重"""
    signature_parts = [
        meta.tvg_id or "",
        meta.tvg_name or "",
        meta.tvg_logo or "",
        meta.group_title or ""
    ]
    return "|".join([part.strip() for part in signature_parts])

def parse_extinf_priority(extinf_line: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """优先提取EXTINF核心字段：tvg-name > group-title > tvg-id > tvg-logo > 频道名称"""
    if not extinf_line:
        return (None, None, None, None, None)
    
    # 正则匹配各字段（不区分大小写）
    tvg_id = re.search(r'tvg-id="([^"]+)"', extinf_line, re.IGNORECASE)
    tvg_name = re.search(r'tvg-name="([^"]+)"', extinf_line, re.IGNORECASE)
    tvg_logo = re.search(r'tvg-logo="([^"]+)"', extinf_line, re.IGNORECASE)
    group_title = re.search(r'group-title="([^"]+)"', extinf_line, re.IGNORECASE)
    channel_name = re.search(r',\s*([^#\n\r]+)$', extinf_line, re.IGNORECASE)
    
    # 格式化返回结果
    return (
        tvg_id.group(1).strip() if tvg_id else None,
        tvg_name.group(1).strip() if tvg_name else None,
        tvg_logo.group(1).strip() if tvg_logo else None,
        group_title.group(1).strip() if group_title else None,
        channel_name.group(1).strip() if channel_name else None
    )

def global_replace_cctv_name(content: str) -> str:
    """标准化CCTV频道名称（兼容配置文件映射）"""
    if not content:
        return content
    all_mappings = {}
    # 兼容config中可能的映射配置（若未定义则不报错）
    if hasattr(config, 'cntvNamesReverse'):
        all_mappings.update(config.cntvNamesReverse)
    if hasattr(config, 'cctv_alias'):
        all_mappings.update(config.cctv_alias)
    # 按字段长度排序，避免短字段覆盖长字段
    sorted_mappings = sorted(all_mappings.items(), key=lambda x: (-len(x[0]), x[0]))
    for old_name, new_name in sorted_mappings:
        if old_name in content:
            content = content.replace(old_name, new_name)
    return content

def standardize_cctv_name(channel_name: Optional[str]) -> str:
    """标准化CCTV频道名称（单独处理频道名）"""
    if not channel_name:
        return ""
    channel_name = channel_name.strip()
    # 兼容config配置
    if hasattr(config, 'cntvNamesReverse') and channel_name in config.cntvNamesReverse:
        return config.cntvNamesReverse[channel_name]
    if hasattr(config, 'cctv_alias') and channel_name in config.cctv_alias:
        return config.cctv_alias[channel_name]
    # 模糊匹配
    if hasattr(config, 'cntvNamesReverse'):
        for raw_name, standard_name in config.cntvNamesReverse.items():
            if raw_name in channel_name:
                return standard_name
    if hasattr(config, 'cctv_alias'):
        for alias_name, standard_name in config.cctv_alias.items():
            if alias_name in channel_name:
                return standard_name
    return channel_name

def replace_github_domain(url: str) -> List[str]:
    """替换GitHub域名为镜像+代理，提升可访问性"""
    if not url or "github" not in url.lower():
        return [url]
    candidate_urls = [url]
    # 替换镜像域名
    for mirror in GITHUB_MIRRORS:
        for original in GITHUB_MIRRORS:
            if original in url:
                new_url = url.replace(original, mirror)
                if new_url not in candidate_urls:
                    candidate_urls.append(new_url)
    # 增加代理前缀
    proxy_urls = []
    for base_url in candidate_urls:
        for proxy in PROXY_PREFIXES:
            if not base_url.startswith(proxy):
                proxy_url = proxy + base_url
                if proxy_url not in proxy_urls:
                    proxy_urls.append(proxy_url)
    # 去重并限制最大数量
    unique_urls = list(dict.fromkeys(candidate_urls + proxy_urls))
    return unique_urls[:5]

def fetch_url_with_retry(url: str, timeout: int = 15) -> Optional[str]:
    """带重试机制的URL抓取（兼容GitHub源）"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    original_url = url
    # GitHub blob地址转raw地址
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    candidate_urls = replace_github_domain(url)
    timeouts = [5, 10, 15, 15, 15]  # 递增超时时间
    
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
            response.raise_for_status()  # 抛出HTTP错误
            response.encoding = response.apparent_encoding or 'utf-8'
            return response.text
        except requests.RequestException as e:
            logger.warning(f"抓取失败 [{idx+1}/{len(candidate_urls)}]: {candidate} | {str(e)[:50]}")
            continue
    logger.error(f"所有候选URL均抓取失败：{original_url}")
    return None

def extract_m3u_meta(content: str, source_url: str) -> Tuple[OrderedDictType[str, List[Tuple[str, str]]], List[ChannelMeta]]:
    """提取M3U元信息（核心修复：兼容RTSP协议）"""
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
        
        # 核心修复：允许 HTTP/HTTPS/RTSP 协议（增加RTSP支持）
        if not url or not url.startswith(("http://", "https://", "rtsp://")):
            logger.debug(f"跳过不支持的URL协议：{url}")
            continue
        
        # 优先解析EXTINF字段
        tvg_id, tvg_name, tvg_logo, group_title, channel_name = parse_extinf_priority(raw_extinf)
        
        # 字段补全与标准化
        channel_name = standardize_cctv_name(channel_name) or tvg_name or "未知频道"
        tvg_name = tvg_name or channel_name  # tvg-name缺失时用频道名填充
        group_title = clean_group_title(group_title, channel_name)
        
        # 构建频道元信息并生成去重签名
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
        
        # 双重去重：先按EXTINF签名，再按URL
        if meta.extinf_signature in extinf_signature_cache or url in seen_urls:
            logger.debug(f"重复频道跳过：{channel_name}（签名/URL已存在）")
            continue
        extinf_signature_cache.add(meta.extinf_signature)
        seen_urls.add(url)
        url_source_mapping[url] = source_url
        
        # 缓存并分类
        meta_list.append(meta)
        channel_meta_cache[url] = meta
        if group_title not in categorized_channels:
            categorized_channels[group_title] = []
        categorized_channels[group_title].append((channel_name, url))
    
    logger.info(f"M3U提取有效频道数：{len(meta_list)}")
    return categorized_channels, meta_list

def extract_channels_from_content(content: str, source_url: str) -> OrderedDictType[str, List[Tuple[str, str]]]:
    """提取频道（兼容M3U和普通文本格式）"""
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
            # 跳过注释行，提取分类标识
            if not line or line.startswith(("//", "#", "/*", "*/")):
                if any(keyword in line.lower() for keyword in ['#分类', '#genre', '分类:', 'genre:', '==', '---']):
                    group_match = re.search(r'[：:=](\S+)', line)
                    current_group = group_match.group(1).strip() if group_match else ""
                    current_group = re.sub(r'[#分类:genre:==\-—]', '', current_group).strip()
                continue
            
            # 匹配普通文本格式的频道（名称,URL）
            pattern = r'([^,|#$]+)[,|#$]\s*(https?://|rtsp://[^\s,|#$]+)'  # 支持RTSP
            matches = re.findall(pattern, line, re.IGNORECASE)
            if matches:
                for name, url in matches:
                    name = name.strip()
                    url = url.strip()
                    if not url or url in seen_urls:
                        continue
                    
                    # 标准化信息
                    standard_name = standardize_cctv_name(name) or "未知频道"
                    group_title = clean_group_title(current_group, standard_name)
                    
                    # 构建元信息
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
                    
                    # 去重
                    if meta.extinf_signature in extinf_signature_cache or url in seen_urls:
                        logger.debug(f"重复频道跳过：{standard_name}")
                        continue
                    extinf_signature_cache.add(meta.extinf_signature)
                    seen_urls.add(url)
                    url_source_mapping[url] = source_url
                    
                    # 分类存储
                    if group_title not in categorized_channels:
                        categorized_channels[group_title] = []
                    categorized_channels[group_title].append((standard_name, url))
        
        logger.info(f"普通文本提取有效频道数：{sum(len(v) for v in categorized_channels.values())}")
    
    # 过滤空分类
    categorized_channels = OrderedDict([(k, v) for k, v in categorized_channels.items() if v])
    return categorized_channels

def merge_channels(target: OrderedDictType[str, List[Tuple[str, str]]], source: OrderedDictType[str, List[Tuple[str, str]]]):
    """合并多个源的频道（去重）"""
    current_urls = set()
    current_extinf_signatures = set()
    # 收集已有频道的URL和签名
    for category, ch_list in target.items():
        for _, url in ch_list:
            current_urls.add(url)
            meta = channel_meta_cache.get(url)
            if meta:
                current_extinf_signatures.add(meta.extinf_signature)
    
    # 合并新源频道
    for category, ch_list in source.items():
        if category not in target:
            target[category] = []
        for name, url in ch_list:
            meta = channel_meta_cache.get(url)
            if not meta:
                continue
            # 双重去重
            if meta.extinf_signature in current_extinf_signatures or url in current_urls:
                continue
            target[category].append((name, url))
            current_urls.add(url)
            current_extinf_signatures.add(meta.extinf_signature)

def generate_summary(all_channels: OrderedDictType[str, List[Tuple[str, str]]]):
    """生成汇总TXT和M3U文件"""
    if not all_channels:
        logger.warning("无有效频道，跳过生成文件")
        return
    
    summary_path = OUTPUT_FOLDER / "live_source_summary.txt"
    m3u_path = OUTPUT_FOLDER / "live_source_merged.m3u"
    
    try:
        # 生成汇总TXT
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("IPTV直播源汇总（支持HTTP/HTTPS/RTSP协议）\n")
            f.write("="*80 + "\n")
            f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"总频道数：{sum(len(ch_list) for _, ch_list in all_channels.items())}\n")
            f.write(f"分类数：{len(all_channels)}\n")
            f.write("="*80 + "\n\n")
            
            for group, ch_list in all_channels.items():
                f.write(f"【{group}】（{len(ch_list)}个频道）\n")
                for idx, (name, url) in enumerate(ch_list, 1):
                    source = url_source_mapping.get(url, "未知来源")
                    f.write(f"{idx:>3}. {name:<20} {url}\n")
                    f.write(f"      来源：{source}\n")
                f.write("\n")
        
        # 生成M3U文件（兼容播放器）
        with open(m3u_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U x-tvg-url=\"\"\n")
            f.write(f"# 支持HTTP/HTTPS/RTSP协议 | 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 总频道数：{sum(len(ch_list) for _, ch_list in all_channels.items())}\n\n")
            
            for group, ch_list in all_channels.items():
                f.write(f"# ===== {group}（{len(ch_list)}个频道） =====\n")
                for name, url in ch_list:
                    meta = channel_meta_cache.get(url)
                    if meta and meta.raw_extinf:
                        # 保留原始EXTINF信息，补全group-title
                        extinf = meta.raw_extinf
                        if 'group-title="' in extinf:
                            start = extinf.find('group-title="') + len('group-title="')
                            end = extinf.find('"', start)
                            if end > start:
                                extinf = extinf[:start] + group + extinf[end:]
                        # 补全频道名称
                        if ',' in extinf:
                            extinf_part, old_name = extinf.rsplit(',', 1)
                            extinf = extinf_part + ',' + name
                        f.write(extinf + "\n")
                    else:
                        f.write(f"#EXTINF:-1 tvg-name=\"{name}\" group-title=\"{group}\",{name}\n")
                    f.write(url + "\n\n")
        
        logger.info(f"文件生成完成：\n  - 汇总TXT：{summary_path}\n  - 合并M3U：{m3u_path}")
    except Exception as e:
        logger.error(f"生成文件失败：{str(e)}", exc_info=True)

# ===================== 主程序 =====================
def main():
    try:
        global channel_meta_cache, url_source_mapping, extinf_signature_cache
        # 初始化缓存（避免跨运行残留）
        channel_meta_cache = {}
        url_source_mapping = {}
        extinf_signature_cache = set()
        logger.info("===== 开始处理直播源（支持HTTP/HTTPS/RTSP协议） =====")
        
        # 读取配置的源URL（兼容无config的情况）
        source_urls = getattr(config, 'SOURCE_URLS', [])
        if not source_urls:
            logger.error("未配置SOURCE_URLS，程序终止（请在config.py中定义SOURCE_URLS列表）")
            return
        logger.info(f"读取源URL数：{len(source_urls)}")
        
        all_channels = OrderedDict()
        failed_urls = []
        
        # 遍历所有源URL处理
        for idx, url in enumerate(source_urls, 1):
            logger.info(f"\n===== 处理第 {idx}/{len(source_urls)} 个源：{url} =====")
            content = fetch_url_with_retry(url)
            if content is None:
                failed_urls.append(url)
                continue
            # 标准化CCTV频道名称
            content = global_replace_cctv_name(content)
            # 提取频道
            extracted = extract_channels_from_content(content, url)
            # 合并频道（去重）
            merge_channels(all_channels, extracted)
        
        # 统计结果
        total_channels = sum(len(ch_list) for _, ch_list in all_channels.items())
        logger.info(f"\n===== 处理完成统计 =====")
        logger.info(f"  - 源URL总数：{len(source_urls)}")
        logger.info(f"  - 失败源数：{len(failed_urls)}")
        logger.info(f"  - 有效频道数：{total_channels}")
        logger.info(f"  - 有效分类数：{len(all_channels)}")
        logger.info(f"  - 分类列表：{list(all_channels.keys())}")
        
        # 生成文件
        generate_summary(all_channels)
        logger.info("\n===== 所有操作完成 =====")
    except Exception as e:
        logger.critical(f"程序异常终止：{str(e)}", exc_info=True)

if __name__ == "__main__":
    main()
