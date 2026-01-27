import re
import requests
import logging
import warnings
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set
import config
import os

# ===================== 基础配置 =====================
warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

OUTPUT_FOLDER = Path("output")
OUTPUT_FOLDER.mkdir(exist_ok=True)

# GitHub 镜像和代理（保持原有配置）
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

# 日志配置
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
    url: str  # 播放URL
    raw_extinf: str = ""  # 完整的原始#EXTINF行
    tvg_id: Optional[str] = None  # 原始tvg-id
    tvg_name: Optional[str] = None  # 原始tvg-name
    tvg_logo: Optional[str] = None  # 原始tvg-logo
    group_title: Optional[str] = None  # 原始group-title
    channel_name: Optional[str] = None  # 原始频道名
    source_url: str = ""  # 来源URL

# 全局存储（新增channel_url_map用于智能去重）
channel_meta_cache: Dict[str, ChannelMeta] = {}  # key: url
url_source_mapping: Dict[str, str] = {}  # url -> 来源URL
channel_url_map: Dict[str, Set[str]] = {}  # key: 频道名+URL主体, value: 完整URL集合（用于去重）

# ===================== 核心工具函数 =====================
def get_url_main_body(url: str) -> str:
    """提取URL主体（去除动态参数，保留核心路径）"""
    if "?" in url:
        # 保留协议、域名、路径，去除查询参数
        main_body = url.split("?", 1)[0]
        # 处理m3u8的动态路径（如包含timestamp、msisdn等参数的情况）
        main_body = re.sub(r'/[0-9a-fA-F]{32,}/', '/[动态ID]/', main_body)
        main_body = re.sub(r'/index\.m3u8$', '', main_body)
        return main_body
    return url

def is_duplicate_channel_url(channel_name: str, url: str) -> bool:
    """智能判断是否为重复频道URL（同一频道+同一URL主体视为重复）"""
    if not channel_name or not url:
        return False
    
    url_body = get_url_main_body(url)
    # 生成去重键：频道名+URL主体（统一小写避免大小写问题）
    dedup_key = f"{channel_name.lower()}_{url_body.lower()}"
    
    # 检查是否已存在
    if dedup_key in channel_url_map:
        # 若已存在相同主体的URL，视为重复
        return True
    
    # 不存在则添加到映射
    channel_url_map[dedup_key] = {url}
    return False

def replace_github_domain(url: str) -> List[str]:
    """替换GitHub域名（保持原有逻辑）"""
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
    """带重试的URL抓取（保持原有逻辑）"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    original_url = url
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        logger.info(f"自动修复GitHub URL：{original_url} → {url}")
    
    candidate_urls = replace_github_domain(url)
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

def extract_m3u_meta(content: str, source_url: str) -> Tuple[OrderedDict, List[ChannelMeta]]:
    """M3U精准提取（优化去重逻辑）"""
    m3u_pattern = re.compile(
        r"(#EXTINF:-?\d+.*?)\n\s*([^#\n\r\s].*?)(?=\s|#|$)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE
    )
    attr_pattern = re.compile(r'(\w+)-(\w+)="([^"]*)"')
    
    categorized_channels = OrderedDict()
    meta_list = []
    seen_raw_urls = set()  # 保留原始URL去重（完全重复的URL仍需过滤）
    
    matches = m3u_pattern.findall(content)
    logger.info(f"从M3U内容中匹配到 {len(matches)} 个原始条目")
    
    for raw_extinf, url in matches:
        url = url.strip()
        raw_extinf = raw_extinf.strip()
        
        # 跳过无效URL或完全重复的URL
        if not url or not url.startswith(("http://", "https://")) or url in seen_raw_urls:
            continue
        seen_raw_urls.add(url)
        
        # 解析频道属性
        tvg_id = None
        tvg_name = None
        tvg_logo = None
        group_title = None
        channel_name = "未知频道"
        
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
        
        # 提取频道名（优先用tvg-name，无则用EXTINF逗号后内容）
        name_match = re.search(r',\s*(.+?)\s*$', raw_extinf)
        if tvg_name:
            channel_name = tvg_name.strip()
        elif name_match:
            channel_name = name_match.group(1).strip()
        
        group_title = group_title if group_title else "未分类"
        
        # 智能去重：同一频道+同一URL主体视为重复，否则保留（多线路）
        if is_duplicate_channel_url(channel_name, url):
            logger.debug(f"跳过重复线路：频道[{channel_name}] URL[{url[:50]}...]")
            continue
        
        # 创建元信息对象
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
        url_source_mapping[url] = source_url
        
        # 添加到分类字典
        if group_title not in categorized_channels:
            categorized_channels[group_title] = []
        categorized_channels[group_title].append((channel_name, url))
    
    logger.info(f"M3U精准提取完成：{len(meta_list)}个有效频道（含多线路）")
    logger.info(f"识别的M3U分类：{list(categorized_channels.keys())}")
    
    return categorized_channels, meta_list

def extract_channels_from_content(content: str, source_url: str) -> OrderedDict:
    """智能提取频道（优先M3U格式）"""
    categorized_channels = OrderedDict()
    
    # 优先处理M3U格式
    if "#EXTM3U" in content:
        m3u_categorized, _ = extract_m3u_meta(content, source_url)
        categorized_channels = m3u_categorized
    else:
        # 普通文本处理（保持原有逻辑，添加智能去重）
        lines = content.split('\n')
        current_group = "默认分类"
        seen_raw_urls = set()
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith(("//", "#", "/*", "*/")):
                if any(keyword in line.lower() for keyword in ['#分类', '#genre', '分类:', 'genre:', '==', '---']):
                    group_match = re.search(r'[：:=](\S+)', line)
                    if group_match:
                        current_group = group_match.group(1).strip()
                    else:
                        current_group = re.sub(r'[#分类:genre:==\-—]', '', line).strip() or "默认分类"
                    current_group = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9_()]', '', current_group)
                    logger.debug(f"智能识别分类：{current_group}")
                continue
            
            pattern = r'([^,|#$]+)[,|#$]\s*(https?://[^\s,|#$]+)'
            matches = re.findall(pattern, line, re.IGNORECASE)
            if matches:
                for name, url in matches:
                    name = name.strip()
                    url = url.strip()
                    if not url or url in seen_raw_urls:
                        continue
                    seen_raw_urls.add(url)
                    
                    # 智能分类推断
                    group_title = current_group
                    if any(keyword in name for keyword in ['CCTV', '央视', '中央']):
                        group_title = "央视频道"
                    elif any(keyword in name for keyword in ['卫视', '江苏', '浙江', '湖南', '东方']):
                        group_title = "卫视频道"
                    elif any(keyword in name for keyword in ['电影', '影视']):
                        group_title = "电影频道"
                    elif any(keyword in name for keyword in ['体育', 'CCTV5']):
                        group_title = "体育频道"
                    
                    # 智能去重
                    if is_duplicate_channel_url(name, url):
                        logger.debug(f"跳过重复线路：频道[{name}] URL[{url[:50]}...]")
                        continue
                    
                    # 创建元信息
                    raw_extinf = f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{name}\" tvg-logo=\"\" group-title=\"{group_title}\",{name}"
                    meta = ChannelMeta(
                        url=url,
                        raw_extinf=raw_extinf,
                        tvg_id="",
                        tvg_name=name,
                        tvg_logo="",
                        group_title=group_title,
                        channel_name=name,
                        source_url=source_url
                    )
                    channel_meta_cache[url] = meta
                    url_source_mapping[url] = source_url
                    
                    if group_title not in categorized_channels:
                        categorized_channels[group_title] = []
                    categorized_channels[group_title].append((name, url))
        
        logger.info(f"智能识别完成：{sum(len(v) for v in categorized_channels.values())}个有效频道（含多线路）")
        logger.info(f"智能识别的分类：{list(categorized_channels.keys())}")
    
    if not categorized_channels:
        categorized_channels["未分类频道"] = []
    
    return categorized_channels

def merge_channels(target: OrderedDict, source: OrderedDict):
    """合并频道（保持智能去重逻辑）"""
    for category_name, channel_list in source.items():
        if category_name not in target:
            target[category_name] = []
        
        for name, url in channel_list:
            # 复用智能去重逻辑，避免跨源重复
            if not is_duplicate_channel_url(name, url):
                target[category_name].append((name, url))

def generate_summary(all_channels: OrderedDict):
    """生成汇总文件（展示多线路）"""
    summary_path = OUTPUT_FOLDER / "live_source_summary.txt"
    m3u_path = OUTPUT_FOLDER / "live_source_merged.m3u"
    
    try:
        # 生成汇总TXT
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("IPTV直播源汇总（保留多线路，智能去重）\n")
            f.write("="*80 + "\n")
            f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"总频道数（去重后）：{len(channel_url_map)}\n")
            f.write(f"总线路数（含多线路）：{sum(len(ch_list) for _, ch_list in all_channels.items())}\n")
            f.write(f"分类数：{len(all_channels)}\n")
            f.write("="*80 + "\n\n")
            
            # 按分类写入，标注线路数
            for group_title, channel_list in all_channels.items():
                # 统计每个频道的线路数
                channel_line_count = {}
                for name, _ in channel_list:
                    channel_line_count[name] = channel_line_count.get(name, 0) + 1
                
                f.write(f"【{group_title}】（共{len(channel_list)}条线路，{len(channel_line_count)}个频道）\n")
                for idx, (name, url) in enumerate(channel_list, 1):
                    source = url_source_mapping.get(url, "未知来源")
                    line_num = channel_line_count[name]
                    f.write(f"{idx:>3}. {name:<20} 线路{line_num} | {url}\n")
                    f.write(f"      来源：{source}\n")
                f.write("\n")
        
        # 生成合并后的M3U文件（保留所有有效线路）
        with open(m3u_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U x-tvg-url=\"\"\n")
            f.write(f"# IPTV直播源合并文件（保留多线路，智能去重）\n")
            f.write(f"# 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 总线路数：{sum(len(ch_list) for _, ch_list in all_channels.items())}\n\n")
            
            for group_title, channel_list in all_channels.items():
                f.write(f"# ===== {group_title}（{len(channel_list)}条线路） =====\n")
                for name, url in channel_list:
                    meta = channel_meta_cache.get(url)
                    if meta and meta.raw_extinf:
                        f.write(meta.raw_extinf + "\n")
                    f.write(url + "\n\n")
        
        logger.info(f"\n汇总文件生成完成：")
        logger.info(f"  - 汇总信息：{summary_path}")
        logger.info(f"  - 合并M3U：{m3u_path}")
        
    except Exception as e:
        logger.error(f"生成汇总文件失败：{str(e)}", exc_info=True)

# ===================== 主程序 =====================
def main():
    """主函数：抓取、提取、智能去重、汇总"""
    try:
        # 清空缓存
        global channel_meta_cache, url_source_mapping, channel_url_map
        channel_meta_cache = {}
        url_source_mapping = {}
        channel_url_map = {}
        
        logger.info("===== 开始处理直播源（支持多线路版本） =====")
        
        # 从config.py获取源URL列表
        source_urls = getattr(config, 'SOURCE_URLS', [])
        if not source_urls:
            logger.error("config.py中未配置SOURCE_URLS，程序终止")
            return
        logger.info(f"从配置中读取到 {len(source_urls)} 个源URL")
        
        all_channels = OrderedDict()
        failed_urls = []
        
        # 遍历所有源URL
        for idx, url in enumerate(source_urls, 1):
            logger.info(f"\n===== 处理第 {idx}/{len(source_urls)} 个源：{url} =====")
            
            content = fetch_url_with_retry(url)
            if content is None:
                failed_urls.append(url)
                continue
            
            extracted_channels = extract_channels_from_content(content, url)
            merge_channels(all_channels, extracted_channels)
        
        # 统计结果
        total_lines = sum(len(ch_list) for _, ch_list in all_channels.items())
        total_unique_channels = len(channel_url_map)
        logger.info(f"\n===== 处理完成统计 =====")
        logger.info(f"  - 源URL总数：{len(source_urls)}")
        logger.info(f"  - 失败源数：{len(failed_urls)}")
        logger.info(f"  - 总线路数（含多线路）：{total_lines}")
        logger.info(f"  - 独特频道数（去重后）：{total_unique_channels}")
        logger.info(f"  - 分类数：{len(all_channels)}")
        logger.info(f"  - 分类列表：{list(all_channels.keys())}")
        
        if failed_urls:
            logger.info(f"  - 失败的源：{', '.join(failed_urls)}")
        
        # 生成汇总文件
        if total_lines > 0:
            generate_summary(all_channels)
        
        logger.info("\n===== 所有操作完成 =====")
        
    except Exception as e:
        logger.critical(f"程序执行异常：{str(e)}", exc_info=True)

if __name__ == "__main__":
    main()
