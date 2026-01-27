import re
import requests
import logging
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set
import warnings

# ===================== 配置导入 =====================
# 导入优化后的配置文件
try:
    import config1 as config
    # 执行配置验证
    if hasattr(config, 'validate_config'):
        config.validate_config()
except ImportError:
    # 如果没有config1.py，创建默认配置类
    class config:
        # 基础默认配置
        PROGRAM_NAME = "IPTV源处理工具"
        LOG_LEVEL = "INFO"
        ENCODING = "utf-8"
        
        # 路径默认配置
        OUTPUT_DIR = Path("output")
        OUTPUT_FILE_PREFIX = "iptv"
        LOG_FILE_NAME = "iptv_process.log"
        
        # 网络默认配置
        FETCH_TIMEOUT = 15
        RETRY_TIMES = 3
        REQUEST_HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        SSL_VERIFY = False
        
        # GitHub默认配置
        GITHUB_MIRRORS = [
            "raw.githubusercontent.com",
            "raw.kkgithub.com",
            "raw.githubusercontents.com",
            "raw.fgit.cf",
            "raw.fgithub.de"
        ]
        GITHUB_PROXIES = [
            "https://ghproxy.com/",
            "https://mirror.ghproxy.com/",
            "https://gh.api.99988866.xyz/"
        ]
        
        # M3U处理默认配置
        KEEP_RAW_EXTINF = True
        URL_NORMALIZE_RULES = {
            "remove_params": True,
            "remove_anchor": True,
            "remove_suffix": True,
            "to_lowercase": True,
        }
        CATEGORY_KEYWORDS = {
            "央视频道": ["CCTV", "央视", "中央"],
            "卫视频道": ["卫视", "江苏", "浙江", "湖南"],
            "电影频道": ["电影", "影视"],
            "体育频道": ["体育", "CCTV5"],
            "少儿频道": ["少儿", "卡通"],
            "未分类频道": [],
        }
        DEFAULT_CATEGORY = "未分类频道"
        
        # 去重默认配置
        GLOBAL_DEDUPLICATION = True
        SORT_BY_CATEGORY = True
        
        # 源URL默认配置
        SOURCE_URLS = []
        SOURCE_BLACKLIST = []
        
        # 高级默认配置
        GENERATE_DETAILED_REPORT = True
        GENERATE_TXT_BACKUP = True
        MAX_CHANNELS = 0
        CHANNEL_NAME_CLEAN_PATTERNS = {
            "remove_special_chars": r'[$「」()（）\s-]',
            "normalize_numbers": r'(\D*)(\d+)(\D*)',
            "keep_special_marks": r'CCTV-?5\+',
        }
        
        # 配置获取辅助函数
        @staticmethod
        def get_config(key, default=None):
            return getattr(config, key, default)
    
    logging.warning("未找到config1.py，使用内置默认配置")

# ===================== 全局设置 =====================
# 屏蔽SSL不安全请求警告
warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

# 确保输出目录存在
OUTPUT_DIR = config.get_config("OUTPUT_DIR", Path("output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ===================== 数据结构 =====================
@dataclass
class ChannelMeta:
    """频道元信息（完整保留原始M3U标签）"""
    url: str  # 必填：播放URL
    raw_extinf: str = ""  # 完整的原始#EXTINF行
    tvg_id: Optional[str] = None  # 原始tvg-id
    tvg_name: Optional[str] = None  # 原始tvg-name
    tvg_logo: Optional[str] = None  # 原始tvg-logo
    group_title: Optional[str] = None  # 原始group-title
    channel_name: Optional[str] = None  # 原始频道名（逗号后部分）
    clean_channel_name: str = ""  # 标准化后的频道名
    source_url: str = ""  # 来源URL
    category: str = ""  # 智能分类

# ===================== 日志配置 =====================
def setup_logging():
    """初始化日志配置"""
    log_level = config.get_config("LOG_LEVEL", "INFO").upper()
    log_file_path = OUTPUT_DIR / config.get_config("LOG_FILE_NAME", "iptv_process.log")
    
    # 配置日志
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file_path, "w", encoding=config.get_config("ENCODING", "utf-8")),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(config.get_config("PROGRAM_NAME", "IPTV_PROCESSOR"))
    logger.info(f"===== {config.get_config('PROGRAM_NAME', 'IPTV源处理工具')} 启动 =====")
    logger.info(f"输出目录：{OUTPUT_DIR.absolute()}")
    logger.info(f"日志级别：{log_level}")
    
    return logger

# 初始化日志
logger = setup_logging()

# 全局存储
channel_meta_cache: Dict[str, ChannelMeta] = {}  # key: normalized_url, value: ChannelMeta
all_categories: Set[str] = set()  # 所有识别到的分类

# ===================== 核心工具函数 =====================
def clean_channel_name(channel_name: str) -> str:
    """标准化清洗频道名称（支持配置自定义规则）"""
    if not channel_name:
        return ""
    
    # 获取清洗规则
    patterns = config.get_config("CHANNEL_NAME_CLEAN_PATTERNS", {})
    
    # 保留特殊标识（如CCTV5+）
    keep_pattern = patterns.get("keep_special_marks", r'CCTV-?5\+')
    channel_name = re.sub(keep_pattern, 'CCTV5+', channel_name)
    
    # 港澳台/凤凰卫视特殊处理
    channel_name = channel_name.replace("翡翠台", "TVB翡翠台")
    channel_name = channel_name.replace("凤凰中文", "凤凰卫视中文台")
    
    # 移除特殊字符
    remove_pattern = patterns.get("remove_special_chars", r'[$「」()（）\s-]')
    cleaned_name = re.sub(remove_pattern, '', channel_name)
    
    # 数字标准化
    number_pattern = patterns.get("normalize_numbers", r'(\D*)(\d+)(\D*)')
    cleaned_name = re.sub(
        number_pattern, 
        lambda m: m.group(1) + str(int(m.group(2))) + m.group(3), 
        cleaned_name
    )
    
    return cleaned_name.upper()

def normalize_url(url: str) -> str:
    """URL标准化（支持配置自定义规则）"""
    if not url:
        return ""
    
    # 获取标准化规则
    rules = config.get_config("URL_NORMALIZE_RULES", {})
    
    # 移除URL参数
    if rules.get("remove_params", True):
        url = url.split('?', 1)[0]
    
    # 移除锚点
    if rules.get("remove_anchor", True):
        url = url.split('#', 1)[0]
    
    # 移除自定义后缀
    if rules.get("remove_suffix", True):
        url = url.split('$', 1)[0]
    
    # 转为小写
    if rules.get("to_lowercase", True):
        url = url.strip().lower()
    else:
        url = url.strip()
    
    return url

def get_intelligent_category(channel_name: str) -> str:
    """基于配置的关键词进行智能分类"""
    if not channel_name:
        return config.get_config("DEFAULT_CATEGORY", "未分类频道")
    
    # 获取分类关键词配置
    category_keywords = config.get_config("CATEGORY_KEYWORDS", {})
    
    # 遍历关键词匹配分类
    for category, keywords in category_keywords.items():
        if any(keyword in channel_name for keyword in keywords):
            return category
    
    return config.get_config("DEFAULT_CATEGORY", "未分类频道")

# ===================== GitHub URL修复 =====================
def replace_github_domain(url: str) -> List[str]:
    """替换GitHub域名（从配置读取镜像列表）"""
    if not url or "github" not in url.lower():
        return [url]
    
    candidate_urls = [url]
    
    # 从配置读取镜像和代理
    github_mirrors = config.get_config("GITHUB_MIRRORS", [])
    github_proxies = config.get_config("GITHUB_PROXIES", [])
    
    # 替换镜像域名
    for mirror in github_mirrors:
        for original in github_mirrors:
            if original in url:
                new_url = url.replace(original, mirror)
                if new_url not in candidate_urls:
                    candidate_urls.append(new_url)
    
    # 添加代理前缀
    proxy_urls = []
    for base_url in candidate_urls:
        for proxy in github_proxies:
            if not base_url.startswith(proxy):
                proxy_url = proxy + base_url
                if proxy_url not in proxy_urls:
                    proxy_urls.append(proxy_url)
    
    candidate_urls.extend(proxy_urls)
    # 去重并限制数量
    unique_urls = list(dict.fromkeys(candidate_urls))
    
    return unique_urls[:config.get_config("RETRY_TIMES", 3) + 2]

def fetch_url_with_retry(url: str) -> Optional[str]:
    """带重试的URL抓取（完全适配配置）"""
    # 从配置读取参数
    fetch_timeout = config.get_config("FETCH_TIMEOUT", 15)
    headers = config.get_config("REQUEST_HEADERS", {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    ssl_verify = config.get_config("SSL_VERIFY", False)
    retry_times = config.get_config("RETRY_TIMES", 3)
    
    # 处理本地文件
    if url.startswith(("file://", "./", "/")):
        try:
            if url.startswith("file://"):
                file_path = Path(url.replace("file://", ""))
            else:
                file_path = Path(url)
            
            logger.info(f"读取本地文件：{file_path.absolute()}")
            with open(file_path, "r", encoding=config.get_config("ENCODING", "utf-8")) as f:
                return f.read()
        except Exception as e:
            logger.error(f"读取本地文件失败：{str(e)}")
            return None
    
    # 自动修复GitHub blob URL
    original_url = url
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        logger.info(f"自动修复GitHub URL：{original_url} → {url}")
    
    candidate_urls = replace_github_domain(url)
    
    # 分级超时
    timeouts = [5, 10, fetch_timeout]
    
    for idx, candidate in enumerate(candidate_urls):
        if idx >= retry_times + 2:  # 限制重试次数
            break
            
        current_timeout = timeouts[min(idx, len(timeouts)-1)]
        try:
            logger.debug(f"尝试抓取 [{idx+1}/{len(candidate_urls)}]: {candidate} (超时：{current_timeout}s)")
            response = requests.get(
                candidate,
                headers=headers,
                timeout=current_timeout,
                verify=ssl_verify,
                allow_redirects=True
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding or config.get_config("ENCODING", "utf-8")
            logger.info(f"成功抓取：{candidate}")
            return response.text
        except requests.RequestException as e:
            logger.warning(f"抓取失败 [{idx+1}/{len(candidate_urls)}]: {candidate} | 原因：{str(e)[:50]}")
            continue
    
    logger.error(f"所有候选链接都抓取失败：{original_url}")
    return None

# ===================== M3U精准提取 =====================
def extract_m3u_meta(content: str, source_url: str) -> Tuple[OrderedDict, List[ChannelMeta]]:
    """M3U精准提取（支持配置控制）"""
    # 匹配完整的M3U条目
    m3u_pattern = re.compile(
        r"(#EXTINF:-?\d+.*?)\n\s*([^#\n\r\s].*?)(?=\s|#|$)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE
    )
    
    # 匹配#EXTINF中的属性
    attr_pattern = re.compile(r'(\w+)-(\w+)="([^"]*)"')
    
    categorized_channels = OrderedDict()
    meta_list = []
    seen_normalized_urls = set()
    
    # 最大频道数限制
    max_channels = config.get_config("MAX_CHANNELS", 0)
    channel_count = 0
    
    matches = m3u_pattern.findall(content)
    logger.info(f"M3U格式检测：发现{len(matches)}个潜在频道条目")
    
    for raw_extinf, url in matches:
        # 检查最大频道数限制
        if max_channels > 0 and channel_count >= max_channels:
            logger.warning(f"达到最大频道数限制({max_channels})，停止提取")
            break
            
        url = url.strip()
        raw_extinf = raw_extinf.strip()
        
        # 跳过无效URL
        if not url or not url.startswith(("http://", "https://")):
            continue
        
        # URL标准化去重
        normalized_url = normalize_url(url)
        if normalized_url in seen_normalized_urls:
            logger.debug(f"URL已存在，跳过重复：{url[:60]}")
            continue
        seen_normalized_urls.add(normalized_url)
        
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
        
        # 确定分类
        group_title = group_title if group_title else config.get_config("DEFAULT_CATEGORY", "未分类频道")
        intelligent_category = get_intelligent_category(channel_name)
        final_category = intelligent_category if intelligent_category != config.get_config("DEFAULT_CATEGORY") else group_title
        
        all_categories.add(final_category)
        
        # 创建元信息对象
        meta = ChannelMeta(
            url=url,
            raw_extinf=raw_extinf if config.get_config("KEEP_RAW_EXTINF", True) else "",
            tvg_id=tvg_id,
            tvg_name=tvg_name,
            tvg_logo=tvg_logo,
            group_title=group_title,
            channel_name=channel_name,
            clean_channel_name=clean_channel_name(channel_name),
            source_url=source_url,
            category=final_category
        )
        
        meta_list.append(meta)
        channel_meta_cache[normalized_url] = meta
        
        # 添加到分类字典
        if final_category not in categorized_channels:
            categorized_channels[final_category] = []
        categorized_channels[final_category].append((channel_name, url))
        
        channel_count += 1
    
    logger.info(f"M3U精准提取完成：{len(meta_list)}个唯一频道")
    logger.info(f"M3U识别的分类：{sorted(list(all_categories))}")
    
    return categorized_channels, meta_list

# ===================== 智能分类识别 =====================
def extract_channels_from_content(content: str, source_url: str) -> OrderedDict:
    """智能提取频道（完全适配配置）"""
    categorized_channels = OrderedDict()
    seen_normalized_urls = set()
    
    # 最大频道数限制
    max_channels = config.get_config("MAX_CHANNELS", 0)
    channel_count = 0
    
    # 优先处理M3U格式
    if "#EXTM3U" in content:
        m3u_categorized, _ = extract_m3u_meta(content, source_url)
        categorized_channels = m3u_categorized
        
        # 更新已见URL和频道计数
        for _, ch_list in m3u_categorized.items():
            for _, url in ch_list:
                seen_normalized_urls.add(normalize_url(url))
                channel_count += 1
    else:
        # 从普通文本中智能提取
        lines = content.split('\n')
        current_group = config.get_config("DEFAULT_CATEGORY", "默认分类")
        
        for line in lines:
            if max_channels > 0 and channel_count >= max_channels:
                break
                
            line = line.strip()
            if not line or line.startswith(("//", "#", "/*", "*/")):
                # 识别分类行
                if any(keyword in line.lower() for keyword in ['#分类', '#genre', '分类:', 'genre:', '==', '---']):
                    group_match = re.search(r'[：:=](\S+)', line)
                    if group_match:
                        current_group = group_match.group(1).strip()
                    else:
                        current_group = re.sub(r'[#分类:genre:==\-—]', '', line).strip() or config.get_config("DEFAULT_CATEGORY")
                    current_group = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9_()]', '', current_group)
                    all_categories.add(current_group)
                    logger.debug(f"智能识别分类：{current_group}")
                continue
            
            # 匹配频道名,URL格式
            pattern = r'([^,|#$]+)[,|#$]\s*(https?://[^\s,|#$]+)'
            matches = re.findall(pattern, line, re.IGNORECASE)
            
            if matches:
                for name, url in matches:
                    if max_channels > 0 and channel_count >= max_channels:
                        break
                        
                    name = name.strip()
                    url = url.strip()
                    
                    # URL去重
                    normalized_url = normalize_url(url)
                    if not url or normalized_url in seen_normalized_urls:
                        continue
                    seen_normalized_urls.add(normalized_url)
                    
                    # 智能分类
                    intelligent_category = get_intelligent_category(name)
                    final_category = intelligent_category if intelligent_category != config.get_config("DEFAULT_CATEGORY") else current_group
                    
                    all_categories.add(final_category)
                    
                    # 创建元信息
                    raw_extinf = f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{name}\" tvg-logo=\"\" group-title=\"{final_category}\",{name}" if config.get_config("KEEP_RAW_EXTINF", True) else ""
                    meta = ChannelMeta(
                        url=url,
                        raw_extinf=raw_extinf,
                        tvg_id="",
                        tvg_name=name,
                        tvg_logo="",
                        group_title=current_group,
                        channel_name=name,
                        clean_channel_name=clean_channel_name(name),
                        source_url=source_url,
                        category=final_category
                    )
                    
                    channel_meta_cache[normalized_url] = meta
                    
                    # 添加到分类字典
                    if final_category not in categorized_channels:
                        categorized_channels[final_category] = []
                    categorized_channels[final_category].append((name, url))
                    
                    channel_count += 1
        
        # 处理剩余的单独URL
        pattern3 = r'(https?://[^\s]+)'
        matches3 = re.findall(pattern3, content, re.IGNORECASE | re.MULTILINE)
        
        for url in matches3:
            if max_channels > 0 and channel_count >= max_channels:
                break
                
            url = url.strip()
            normalized_url = normalize_url(url)
            
            if not url or normalized_url in seen_normalized_urls:
                continue
            seen_normalized_urls.add(normalized_url)
            
            # 从URL提取频道名
            channel_name = "未知频道"
            url_parts = url.split('/')
            for part in url_parts:
                if part and len(part) > 3 and not part.startswith(('http', 'www', 'live', 'stream')):
                    channel_name = part
                    break
            
            # 智能分类
            intelligent_category = get_intelligent_category(channel_name)
            final_category = intelligent_category
            
            all_categories.add(final_category)
            
            # 创建元信息
            raw_extinf = f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{channel_name}\" tvg-logo=\"\" group-title=\"{final_category}\",{channel_name}" if config.get_config("KEEP_RAW_EXTINF", True) else ""
            meta = ChannelMeta(
                url=url,
                raw_extinf=raw_extinf,
                tvg_id="",
                tvg_name=channel_name,
                tvg_logo="",
                group_title="",
                channel_name=channel_name,
                clean_channel_name=clean_channel_name(channel_name),
                source_url=source_url,
                category=final_category
            )
            
            channel_meta_cache[normalized_url] = meta
            
            # 添加到分类字典
            if final_category not in categorized_channels:
                categorized_channels[final_category] = []
            categorized_channels[final_category].append((channel_name, url))
            
            channel_count += 1
    
    # 确保至少有一个分类
    if not categorized_channels:
        default_cat = config.get_config("DEFAULT_CATEGORY", "未分类频道")
        categorized_channels[default_cat] = []
        all_categories.add(default_cat)
    
    logger.info(f"智能提取完成：{sum(len(v) for v in categorized_channels.values())}个唯一频道")
    logger.info(f"智能识别的分类：{sorted(list(all_categories))}")
    
    return categorized_channels

# ===================== URL去重汇总 =====================
def merge_and_deduplicate_channels(all_sources: List[OrderedDict]) -> OrderedDict:
    """合并去重（支持配置控制）"""
    merged_channels = OrderedDict()
    global_seen_urls = set()
    
    # 是否启用全局去重
    global_dedup = config.get_config("GLOBAL_DEDUPLICATION", True)
    # 是否按分类排序
    sort_by_category = config.get_config("SORT_BY_CATEGORY", True)
    
    logger.info("\n开始合并并去重所有频道...")
    logger.info(f"全局去重：{'启用' if global_dedup else '禁用'}")
    logger.info(f"按分类排序：{'启用' if sort_by_category else '禁用'}")
    
    for source_idx, source_channels in enumerate(all_sources):
        logger.info(f"处理第{source_idx+1}个来源，包含{len(source_channels)}个分类")
        
        for group_title, channel_list in source_channels.items():
            if group_title not in merged_channels:
                merged_channels[group_title] = []
            
            for channel_name, url in channel_list:
                normalized_url = normalize_url(url)
                
                # 全局URL去重
                if global_dedup and normalized_url in global_seen_urls:
                    logger.debug(f"全局去重：跳过重复URL {url[:60]}")
                    continue
                
                if global_dedup:
                    global_seen_urls.add(normalized_url)
                merged_channels[group_title].append((channel_name, url))
    
    # 按分类排序
    if sort_by_category:
        sorted_merged = OrderedDict()
        for category in sorted(merged_channels.keys()):
            sorted_merged[category] = merged_channels[category]
        merged_channels = sorted_merged
    
    total_channels = sum(len(v) for v in merged_channels.values())
    logger.info(f"合并去重完成：总计{len(merged_channels)}个分类，{total_channels}个唯一频道")
    logger.info(f"最终分类列表：{sorted(list(merged_channels.keys()))}")
    
    return merged_channels

def generate_output_files(merged_channels: OrderedDict):
    """生成输出文件（完全适配配置）"""
    prefix = config.get_config("OUTPUT_FILE_PREFIX", "iptv")
    encoding = config.get_config("ENCODING", "utf-8")
    
    # 文件路径
    summary_m3u = OUTPUT_DIR / f"{prefix}_summary.m3u"
    summary_txt = OUTPUT_DIR / f"{prefix}_summary.txt"
    summary_report = OUTPUT_DIR / f"{prefix}_report.txt"
    
    try:
        # 写入M3U文件
        with open(summary_m3u, "w", encoding=encoding) as f_m3u:
            f_m3u.write("#EXTM3U x-tvg-url=\"\"\n")
            f_m3u.write(f"# {config.get_config('PROGRAM_NAME', 'IPTV直播源汇总')}\n")
            f_m3u.write(f"# 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f_m3u.write(f"# 总分类数：{len(merged_channels)} | 总频道数：{sum(len(v) for v in merged_channels.values())}\n\n")
            
            for group_title, channel_list in merged_channels.items():
                f_m3u.write(f"# ===== {group_title}（{len(channel_list)}个频道） =====\n")
                
                for channel_name, url in channel_list:
                    normalized_url = normalize_url(url)
                    meta = channel_meta_cache.get(normalized_url)
                    
                    if meta and meta.raw_extinf:
                        f_m3u.write(meta.raw_extinf + "\n")
                    else:
                        f_m3u.write(
                            f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{channel_name}\" "
                            f"tvg-logo=\"\" group-title=\"{group_title}\",{channel_name}\n"
                        )
                    f_m3u.write(url + "\n\n")
        
        logger.info(f"M3U文件生成完成：{summary_m3u}")
        
        # 生成TXT备份（根据配置）
        if config.get_config("GENERATE_TXT_BACKUP", True):
            with open(summary_txt, "w", encoding=encoding) as f_txt:
                for group_title, channel_list in merged_channels.items():
                    f_txt.write(f"{group_title},#genre#\n")
                    for channel_name, url in channel_list:
                        f_txt.write(f"{channel_name},{url}\n")
            logger.info(f"TXT备份生成完成：{summary_txt}")
        
        # 生成详细报告（根据配置）
        if config.get_config("GENERATE_DETAILED_REPORT", True):
            with open(summary_report, "w", encoding=encoding) as f_report:
                f_report.write(f"{config.get_config('PROGRAM_NAME', 'IPTV直播源汇总报告')}\n")
                f_report.write("="*80 + "\n")
                f_report.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f_report.write(f"源URL数量：{len(config.get_config('SOURCE_URLS', []))}\n")
                f_report.write(f"总分类数：{len(merged_channels)}\n")
                f_report.write(f"总唯一频道数：{sum(len(v) for v in merged_channels.values())}\n\n")
                
                f_report.write("分类详情：\n")
                f_report.write("-"*80 + "\n")
                for idx, (category, channels) in enumerate(merged_channels.items(), 1):
                    f_report.write(f"{idx:2d}. {category:<30} {len(channels)}个频道\n")
                
                f_report.write("\n频道详情（按分类）：\n")
                f_report.write("-"*80 + "\n")
                for category, channels in merged_channels.items():
                    f_report.write(f"\n【{category}】\n")
                    for channel_name, url in channels:
                        f_report.write(f"  {channel_name:<25} {url[:80]}\n")
            
            logger.info(f"详细报告生成完成：{summary_report}")
        
    except Exception as e:
        logger.error(f"生成输出文件失败：{str(e)}", exc_info=True)

# ===================== 主程序 =====================
def main():
    """主函数"""
    start_time = time.time()
    
    # 获取源URL列表
    SOURCE_URLS = config.get_config("SOURCE_URLS", [])
    SOURCE_BLACKLIST = config.get_config("SOURCE_BLACKLIST", [])
    
    # 过滤黑名单URL
    if SOURCE_BLACKLIST:
        original_count = len(SOURCE_URLS)
        SOURCE_URLS = [url for url in SOURCE_URLS if url not in SOURCE_BLACKLIST]
        if len(SOURCE_URLS) < original_count:
            logger.info(f"已过滤 {original_count - len(SOURCE_URLS)} 个黑名单URL")
    
    # 去重源URL
    original_count = len(SOURCE_URLS)
    SOURCE_URLS = list(dict.fromkeys(SOURCE_URLS))
    if len(SOURCE_URLS) < original_count:
        logger.info(f"已去重 {original_count - len(SOURCE_URLS)} 个重复源URL")
    
    if not SOURCE_URLS:
        logger.warning("未配置有效SOURCE_URLS，使用测试内容演示...")
        # 演示用测试内容
        test_content = """#EXTM3U
#EXTINF:-1 tvg-id="cctv1" tvg-name="CCTV1" tvg-logo="" group-title="央视频道",CCTV1
http://test.com/cctv1.m3u8
#EXTINF:-1 tvg-id="hunan" tvg-name="湖南卫视" tvg-logo="" group-title="卫视频道",湖南卫视
http://test.com/hunan.m3u8?token=123
#EXTINF:-1 tvg-id="hunan" tvg-name="湖南卫视" tvg-logo="" group-title="卫视频道",湖南卫视
http://test.com/hunan.m3u8$IPv4(100ms)
"""
        test_channels, _ = extract_m3u_meta(test_content, "test_source")
        all_sources = [test_channels]
    else:
        logger.info(f"开始处理 {len(SOURCE_URLS)} 个源URL...")
        all_sources = []
        
        for url in SOURCE_URLS:
            logger.info(f"\n===== 处理源：{url} =====")
            content = fetch_url_with_retry(url)
            if content:
                channels = extract_channels_from_content(content, url)
                all_sources.append(channels)
            else:
                logger.error(f"跳过无效源：{url}")
    
    # 合并去重
    if all_sources:
        merged_channels = merge_and_deduplicate_channels(all_sources)
        # 生成输出文件
        generate_output_files(merged_channels)
    
    # 统计耗时
    elapsed = time.time() - start_time
    logger.info(f"\n===== 处理完成 | 总耗时：{elapsed:.2f}秒 =====")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序执行出错：{str(e)}", exc_info=True)
        raise
