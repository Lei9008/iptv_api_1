import re
import requests
import logging
import warnings
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, OrderedDict as OrderedDictType

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

# ===================== 标准元信息库（可扩展） =====================
# 格式：{频道名称: {tvg-id: 唯一ID, tvg-logo: 图标URL, group-title: 标准分类}}
STANDARD_CHANNEL_META = {
    "CCTV1": {
        "tvg-id": "cctv1.cctv",
        "tvg-logo": "https://epg.pw/logos/cctv1.png",
        "group-title": "央视频道"
    },
    "CCTV2": {
        "tvg-id": "cctv2.cctv",
        "tvg-logo": "https://epg.pw/logos/cctv2.png",
        "group-title": "央视频道"
    },
    "CCTV5": {
        "tvg-id": "cctv5.cctv",
        "tvg-logo": "https://epg.pw/logos/cctv5.png",
        "group-title": "央视频道"
    },
    "CCTV5+": {
        "tvg-id": "cctv5plus.cctv",
        "tvg-logo": "https://epg.pw/logos/cctv5plus.png",
        "group-title": "央视频道"
    },
    "湖南卫视": {
        "tvg-id": "hunantv.hunan",
        "tvg-logo": "https://epg.pw/logos/hunan.png",
        "group-title": "卫视频道"
    },
    "浙江卫视": {
        "tvg-id": "zhejiangtv.zhejiang",
        "tvg-logo": "https://epg.pw/logos/zhejiang.png",
        "group-title": "卫视频道"
    },
    "北京卫视": {
        "tvg-id": "beijingtv.beijing",
        "tvg-logo": "https://epg.pw/logos/beijing.png",
        "group-title": "卫视频道"
    },
    "东方卫视": {
        "tvg-id": "dongfangtv.shanghai",
        "tvg-logo": "https://epg.pw/logos/dongfang.png",
        "group-title": "卫视频道"
    },
    "广东卫视": {
        "tvg-id": "guangdongtv.guangdong",
        "tvg-logo": "https://epg.pw/logos/guangdong.png",
        "group-title": "卫视频道"
    }
    # 可根据需要扩展更多频道...
}

# 匹配阈值（0-100，越高匹配越严格，原生实现建议70-80）
MATCH_THRESHOLD = 75

# ===================== 日志配置 =====================
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

# ===================== 模板功能实现（新增核心） =====================
def load_template() -> List[str]:
    """
    读取模板文件，返回需要保留的频道列表
    注释行以 # 开头，空行会被自动过滤
    """
    if not config.USE_TEMPLATE:
        logger.info("模板匹配已关闭，跳过模板文件读取")
        return []
    
    template_path = Path(config.TEMPLATE_FILE)
    # 检查模板文件是否存在
    if not template_path.exists():
        logger.warning(f"模板文件不存在：{template_path.absolute()}，自动关闭模板匹配")
        config.USE_TEMPLATE = False
        return []
    
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            # 过滤注释行、空行，去重并保留顺序
            template_channels = []
            seen_template_names = set()
            for line in f.readlines():
                line_content = line.strip()
                # 跳过注释行和空行
                if not line_content or line_content.startswith("#"):
                    continue
                # 去重并添加
                if line_content not in seen_template_names:
                    seen_template_names.add(line_content)
                    template_channels.append(line_content)
        
        logger.info(f"成功读取模板文件，共 {len(template_channels)} 个待匹配频道")
        return template_channels
    except Exception as e:
        logger.error(f"读取模板文件失败：{str(e)}，自动关闭模板匹配", exc_info=True)
        config.USE_TEMPLATE = False
        return []

def filter_channels_by_template(all_channels: OrderedDictType[str, List[Tuple[str, str]]],
                                template_channels: List[str]) -> OrderedDictType[str, List[Tuple[str, str]]]:
    """
    按模板筛选并排序频道，保留模板中匹配的频道，且顺序与模板一致
    """
    if not template_channels or not config.USE_TEMPLATE:
        return all_channels
    
    # 第一步：构建「频道名称→(分类, URL)」的映射表，方便快速查找
    name_to_channel_info = {}
    for group_title, ch_list in all_channels.items():
        for name, url in ch_list:
            # 用标准化名称作为key，保留分类和URL
            if name not in name_to_channel_info:
                name_to_channel_info[name] = []
            name_to_channel_info[name].append((group_title, url))
    
    # 第二步：按模板顺序筛选频道，保留匹配结果
    template_filtered = OrderedDict()
    seen_filtered_urls = set()  # 去重（按URL）
    
    for template_name in template_channels:
        # 遍历所有已提取的频道，进行模糊匹配
        matched = False
        for channel_name, info_list in name_to_channel_info.items():
            similarity = calculate_string_similarity(channel_name, template_name)
            if similarity >= MATCH_THRESHOLD:
                # 匹配成功，提取分类和URL
                for group_title, url in info_list:
                    if url in seen_filtered_urls:
                        continue
                    seen_filtered_urls.add(url)
                    
                    # 初始化分类
                    if group_title not in template_filtered:
                        template_filtered[group_title] = []
                    # 添加到筛选结果中
                    template_filtered[group_title].append((channel_name, url))
                    matched = True
                    logger.debug(f"模板匹配成功：[{template_name}] → [{channel_name}]（得分：{similarity}）")
        if not matched:
            logger.warning(f"模板中的频道未匹配到有效结果：[{template_name}]")
    
    # 第三步：过滤空分类
    final_filtered = OrderedDict([(k, v) for k, v in template_filtered.items() if v])
    logger.info(f"模板筛选完成，最终保留 {sum(len(v) for v in final_filtered.values())} 个有效频道")
    
    return final_filtered

# ===================== 原生Python实现简易模糊匹配（无第三方依赖） =====================
def calculate_string_similarity(s1: str, s2: str) -> int:
    """
    原生Python计算两个字符串的相似度（返回0-100的分值）
    核心逻辑：先计算最长公共子串长度，再结合字符串总长度计算相似度
    """
    if not s1 or not s2:
        return 0
    
    # 统一转为小写，忽略大小写差异
    s1_lower = s1.lower()
    s2_lower = s2.lower()
    
    # 计算最长公共子串长度（核心：衡量两个字符串的重叠度）
    len1, len2 = len(s1_lower), len(s2_lower)
    # 构建二维数组，存储子串长度
    dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    max_common_len = 0
    
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            if s1_lower[i-1] == s2_lower[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
                max_common_len = max(max_common_len, dp[i][j])
    
    # 计算相似度（兼顾公共子串长度和字符串整体长度，避免短字符串匹配偏差）
    total_len = len1 + len2
    if total_len == 0:
        return 100
    similarity = int((2 * max_common_len / total_len) * 100)
    
    # 额外加分：若其中一个字符串是另一个的子串（如"央1"包含在"CCTV1 综合频道"）
    if s1_lower in s2_lower or s2_lower in s1_lower:
        similarity += 15
    # 限制分值不超过100
    return min(similarity, 100)

def fuzzy_match_channel(channel_name: str, group_title: str = "") -> Optional[Dict[str, str]]:
    """
    原生Python实现近似匹配，返回最接近的频道元信息（无第三方依赖）
    :param channel_name: 待匹配的频道名称
    :param group_title: 分类（辅助提升匹配精度）
    :return: 匹配到的标准元信息（无匹配返回None）
    """
    if not channel_name:
        return None
    
    best_match = None
    highest_score = 0
    
    # 遍历标准库，计算匹配度
    for std_name, std_meta in STANDARD_CHANNEL_META.items():
        # 计算核心相似度
        similarity_score = calculate_string_similarity(channel_name, std_name)
        
        # 辅助提升：分类一致时加分（提升匹配精度）
        if group_title and std_meta.get("group-title") == group_title:
            similarity_score += 10
        
        # 记录最高得分的匹配结果
        if similarity_score > highest_score and similarity_score >= MATCH_THRESHOLD:
            highest_score = similarity_score
            best_match = std_meta
    
    if best_match:
        matched_std_name = [k for k, v in STANDARD_CHANNEL_META.items() if v == best_match][0]
        logger.debug(f"频道近似匹配成功：[{channel_name}] → 标准库[{matched_std_name}]（得分：{highest_score}）")
    return best_match

# ===================== 补全EXTINF信息 =====================
def complete_extinf(meta: ChannelMeta) -> ChannelMeta:
    """
    补全不完整的EXTINF信息：保留已有字段，补全缺失字段
    :param meta: 原始频道元信息（可能存在缺失字段）
    :return: 补全后的频道元信息
    """
    # 1. 优先通过模糊匹配获取标准元信息
    std_meta = fuzzy_match_channel(meta.channel_name, meta.group_title)
    
    # 2. 补全缺失字段（已有字段不覆盖，缺失字段用标准库/默认值填充）
    if std_meta:
        meta.tvg_id = meta.tvg_id or std_meta.get("tvg-id")
        meta.tvg_logo = meta.tvg_logo or std_meta.get("tvg-logo")
        # 分类以清洗后的为准，若清洗后为空则用标准库分类
        meta.group_title = meta.group_title if meta.group_title != "未分类" else std_meta.get("group-title", "未分类")
    
    # 3. 最终兜底：确保无空字段（避免播放器解析异常）
    # 修正：hash返回int，先转绝对值→字符串→再切片（解决int不可切片错误）
    meta.tvg_id = meta.tvg_id or f"auto_{str(abs(hash(meta.channel_name or meta.url)))[:8]}"
    meta.tvg_name = meta.tvg_name or meta.channel_name or "未知频道"
    meta.tvg_logo = meta.tvg_logo or "https://epg.pw/logos/default.png"  # 默认图标
    meta.group_title = meta.group_title or "未分类"
    meta.channel_name = meta.channel_name or "未知频道"
    
    # 4. 重构完整的raw_extinf行（基于补全后的字段）
    meta.raw_extinf = (
        f"#EXTINF:-1 "
        f"tvg-id=\"{meta.tvg_id}\" "
        f"tvg-name=\"{meta.tvg_name}\" "
        f"tvg-logo=\"{meta.tvg_logo}\" "
        f"group-title=\"{meta.group_title}\","
        f"{meta.channel_name}"
    )
    return meta

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
    
    # 优化1：自动转换GitHub blob地址为raw原始文件地址（关键修复）
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        logger.debug(f"自动转换GitHub blob地址 → raw地址：{url}")
    
    # 优化2：清理重复的https://前缀（修复ghfast.top这类代理的格式问题）
    url = re.sub(r'https://+', 'https://', url)
    url = re.sub(r'http://+', 'http://', url)
    
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
    """解析标准M3U格式内容，提取频道元信息和分类（支持多种直播协议，新增EXTINF补全）"""
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
        
        # 封装频道元信息（未补全状态）
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
        
        # 补全EXTINF信息
        meta = complete_extinf(meta)
        
        meta_list.append(meta)
        channel_meta_cache[url] = meta
        
        # 按分类整理频道（补全后的分类可能更新，以补全后为准）
        final_group_title = meta.group_title
        if final_group_title not in categorized_channels:
            categorized_channels[final_group_title] = []
        categorized_channels[final_group_title].append((meta.channel_name, url))
    
    logger.info(f"M3U格式提取有效频道数：{len(meta_list)}（支持协议：{SUPPORTED_PROTOCOLS}）")
    return categorized_channels, meta_list

def extract_channels_from_content(content: str, source_url: str) -> OrderedDictType[str, List[Tuple[str, str]]]:
    """兼容解析M3U格式和自定义文本格式的直播源（支持多种直播协议，新增EXTINF补全）"""
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
                    
                    # 封装未补全的元信息
                    meta = ChannelMeta(
                        url=url,
                        raw_extinf=f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{standard_name}\" tvg-logo=\"\" group-title=\"{group_title}\",{standard_name}",
                        tvg_id="",
                        tvg_name=standard_name,
                        tvg_logo="",
                        group_title=group_title,
                        channel_name=standard_name,
                        source_url=source_url,
                        protocol=protocol
                    )
                    
                    # 补全EXTINF信息
                    meta = complete_extinf(meta)
                    
                    channel_meta_cache[url] = meta
                    
                    # 按补全后的分类整理频道
                    final_group_title = meta.group_title
                    if final_group_title not in categorized_channels:
                        categorized_channels[final_group_title] = []
                    categorized_channels[final_group_title].append((meta.channel_name, url))
        
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
            f.write("IPTV直播源汇总（自动提取+标准化+多协议支持+EXTINF补全）\n")
            f.write("="*80 + "\n")
            f.write(f"生成时间：{generate_time}\n")
            f.write(f"总频道数：{total_channels}\n")
            f.write(f"分类数：{total_categories}\n")
            f.write(f"支持协议：{', '.join([p[:-3].upper() for p in SUPPORTED_PROTOCOLS])}\n")
            f.write("="*80 + "\n\n")
            
            # 按分类写入频道详情（包含补全的tvg-id和logo）
            for group_title, channel_list in all_channels.items():
                f.write(f"【{group_title}】（{len(channel_list)}个频道）\n")
                for idx, (name, url) in enumerate(channel_list, 1):
                    source = url_source_mapping.get(url, "未知来源")
                    protocol = get_url_protocol(url)
                    meta = channel_meta_cache.get(url)
                    tvg_id = meta.tvg_id if meta else "未知"
                    tvg_logo = meta.tvg_logo if meta else "无"
                    f.write(f"{idx:>3}. {name:<20} [{protocol}] TVG-ID: {tvg_id}\n")
                    f.write(f"      URL：{url}\n")
                    f.write(f"      LOGO：{tvg_logo}\n")
                    f.write(f"      来源：{source}\n")
                f.write("\n")
        
        # 生成纯净版M3U文件（包含补全的EXTINF信息）
        with open(m3u_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U x-tvg-url=\"\"\n")
            f.write(f"# IPTV直播源合并文件 | 生成时间：{generate_time}\n")
            f.write(f"# 总频道数：{total_channels} | 总分类数：{total_categories} | 已自动补全EXTINF信息\n\n")
            
            # 按分类写入M3U内容（使用补全后的raw_extinf）
            for group_title, channel_list in all_channels.items():
                f.write(f"# ===== {group_title}（{len(channel_list)}个频道） =====\n")
                for name, url in channel_list:
                    meta = channel_meta_cache.get(url)
                    if meta:
                        # 直接使用补全后的raw_extinf
                        f.write(meta.raw_extinf + "\n")
                    else:
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
        logger.info("开始处理IPTV直播源（提取→标准化→EXTINF补全→合并→生成）")
        logger.info(f"支持的直播协议：{', '.join([p[:-3].upper() for p in SUPPORTED_PROTOCOLS])}")
        logger.info(f"模糊匹配阈值：{MATCH_THRESHOLD}（越高越严格）")
        logger.info(f"模板匹配状态：{'启用' if config.USE_TEMPLATE else '关闭'}")
        if config.USE_TEMPLATE:
            logger.info(f"模板文件：{config.TEMPLATE_FILE}")
        logger.info("="*60)
        
        # 第一步：读取模板文件（若启用）
        template_channels = load_template()
        
        # 第二步：从配置文件读取源URL列表
        source_urls = getattr(config, 'SOURCE_URLS', [])
        if not source_urls:
            logger.error("配置文件中未设置有效SOURCE_URLS，程序终止")
            return
        logger.info(f"读取到待处理的源URL数：{len(source_urls)}")
        
        # 第三步：初始化全局频道字典（保留顺序）
        all_channels = OrderedDict()
        failed_urls = []
        
        # 第四步：遍历所有源URL，逐个处理
        for idx, url in enumerate(source_urls, 1):
            logger.info(f"\n===== 处理第 {idx}/{len(source_urls)} 个源：{url} =====")
            # 抓取URL内容
            content = fetch_url_with_retry(url)
            if content is None:
                failed_urls.append(url)
                continue
            # 批量替换CCTV频道名称
            content = global_replace_cctv_name(content)
            # 提取频道信息（包含EXTINF补全）
            extracted_channels = extract_channels_from_content(content, url)
            # 合并到全局频道字典
            merge_channels(all_channels, extracted_channels)
        
        # 第五步：按模板筛选排序（若启用）
        if config.USE_TEMPLATE and template_channels:
            all_channels = filter_channels_by_template(all_channels, template_channels)
        
        # 第六步：输出处理完成统计
        logger.info(f"\n===== 处理完成统计 =====")
        total_channels = sum(len(ch_list) for _, ch_list in all_channels.items())
        logger.info(f"  - 源URL总数：{len(source_urls)}")
        logger.info(f"  - 抓取失败源数：{len(failed_urls)}")
        logger.info(f"  - 最终有效频道数：{total_channels}")
        logger.info(f"  - 最终有效分类数：{len(all_channels)}")
        if all_channels:
            logger.info(f"  - 分类列表：{list(all_channels.keys())}")
        if failed_urls:
            logger.warning(f"  - 失败的源URL列表：{failed_urls}")
        
        # 第七步：生成输出文件
        generate_summary(all_channels)
        
        logger.info("\n===== 所有操作执行完毕 =====")
        logger.info(f"输出文件存放目录：{OUTPUT_FOLDER.absolute()}")
        
    except Exception as e:
        logger.critical(f"程序运行过程中出现致命异常：{str(e)}", exc_info=True)

if __name__ == "__main__":
    main()
