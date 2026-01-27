import re
import requests
import logging
import warnings
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set
import os

# ===================== 适配CI环境：动态导入config（核心优化） =====================
try:
    import config
except ImportError:
    # GitHub Actions环境下如果没有config.py，使用环境变量配置
    logger.warning("未找到config.py，尝试从环境变量读取SOURCE_URLS")
    config = type('Config', (), {
        'SOURCE_URLS': os.getenv('SOURCE_URLS', '').split(',') if os.getenv('SOURCE_URLS') else []
    })

# ===================== 基础配置 =====================
warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

# 适配CI环境的输出路径（支持绝对路径）
OUTPUT_FOLDER = Path(os.getenv('OUTPUT_DIR', 'output'))
OUTPUT_FOLDER.mkdir(exist_ok=True)

# GitHub 镜像域名列表
GITHUB_MIRRORS = [
    "raw.githubusercontent.com",
    "raw.kkgithub.com",
    "raw.githubusercontents.com",
    "raw.fgit.cf",
    "raw.fgithub.de"
]

# 代理前缀列表
PROXY_PREFIXES = [
    "https://ghproxy.com/",
    "https://mirror.ghproxy.com/",
    "https://gh.api.99988866.xyz/"
]

# 日志配置（适配CI环境：同时输出到文件和控制台）
LOG_FILE_PATH = OUTPUT_FOLDER / "live_source_extract.log"
logging.basicConfig(
    level=logging.INFO if not os.getenv('CI') else logging.WARNING,  # CI环境降低日志级别
    format='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, "w", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===================== CCTV频道名标准化字典 =====================
cntvNames = {
    # 基础频道
    "CCTV1": "CCTV1综合",
    "CCTV2": "CCTV2财经",
    "CCTV3": "CCTV3综艺",
    "CCTV4": "CCTV4中文国际",
    "CCTV5": "CCTV5体育",
    "CCTV5+": "CCTV5+体育赛事",
    "CCTV6": "CCTV6电影",
    "CCTV7": "CCTV7国防军事",
    "CCTV8": "CCTV8电视剧",
    "CCTV9": "CCTV9纪录",
    "cctvjilu": "CCTV9纪录",
    "CCTV10": "CCTV10科教",
    "CCTV11": "CCTV11戏曲",
    "CCTV12": "CCTV12社会与法",
    "CCTV13": "CCTV13新闻",
    "CCTV14": "CCTV14少儿",
    "CCTV15": "CCTV15音乐",
    "CCTV16": "CCTV16奥林匹克",
    "CCTV17": "CCTV17农业农村",
    # 海外频道
    "CCTV4欧洲": "CCTV4中文国际(欧洲)",
    "cctveurope": "CCTV4中文国际(欧洲)",
    "CCTV4美洲": "CCTV4中文国际(美洲)",
    "cctvamerica": "CCTV4中文国际(美洲)",
}

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
    standard_name: Optional[str] = None  # 标准化后的频道名
    source_url: str = ""  # 来源URL

# 全局存储
channel_meta_cache: Dict[str, ChannelMeta] = {}  # key: url, value: ChannelMeta
url_source_mapping: Dict[str, str] = {}  # url -> 来源URL
channel_url_map: Dict[str, Set[str]] = {}  # key: 标准化频道名+URL主体, value: URL集合

# ===================== 核心工具函数 =====================
def standardize_cctv_name(channel_name: str) -> str:
    """标准化CCTV频道名"""
    if not channel_name:
        return "未知频道"
    
    # 统一转为小写，便于匹配
    name_lower = channel_name.strip().lower()
    
    # 1. 直接匹配字典中的别名
    for alias, standard_name in cntvNames.items():
        if alias.lower() == name_lower or alias in channel_name:
            return standard_name
    
    # 2. 模糊匹配（如"CCTV1 综合" → "CCTV1综合"）
    cctv_match = re.search(r'(CCTV\d+\+?)', channel_name, re.IGNORECASE)
    if cctv_match:
        cctv_code = cctv_match.group(1).upper()
        if cctv_code in cntvNames:
            return cntvNames[cctv_code]
    
    # 3. 非CCTV频道直接返回原名称（清理空格）
    return re.sub(r'\s+', '', channel_name)

def get_url_main_body(url: str) -> str:
    """提取URL主体（去除动态参数）"""
    if not url:
        return ""
    
    if "?" in url:
        main_body = url.split("?", 1)[0]
    else:
        main_body = url
    
    # 增强动态参数过滤（适配更多直播源格式）
    main_body = re.sub(r'/[0-9a-fA-F]{32,}/', '/[动态ID]/', main_body)
    main_body = re.sub(r'/[0-9]{10,}/', '/[时间戳]/', main_body)
    main_body = re.sub(r'/index\.m3u8$', '', main_body)
    main_body = re.sub(r'/live\d*\.m3u8$', '', main_body)  # 新增：过滤liveN.m3u8
    
    return main_body

def is_duplicate_channel(channel_name: str, url: str) -> bool:
    """智能判断是否为重复频道（基于标准化名称+URL主体）"""
    if not channel_name or not url:
        return False
    
    # 使用标准化名称进行去重，避免别名导致的重复
    standard_name = standardize_cctv_name(channel_name)
    url_body = get_url_main_body(url)
    dedup_key = f"{standard_name.lower()}_{url_body.lower()}"
    
    if dedup_key in channel_url_map:
        return True
    else:
        channel_url_map[dedup_key] = {url}
        return False

def replace_github_domain(url: str) -> List[str]:
    """替换GitHub域名（自动修复GitHub URL）"""
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
    
    # 去重并限制数量（避免过多候选链接）
    unique_urls = list(dict.fromkeys(candidate_urls + proxy_urls))
    return unique_urls[:5]

def fetch_url_with_retry(url: str, timeout: int = None) -> Optional[str]:
    """带重试的URL抓取（适配CI环境的超时配置）"""
    # 优先读取环境变量的超时配置
    if timeout is None:
        timeout = int(os.getenv('REQUESTS_TIMEOUT', 15))
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "keep-alive"
    }
    
    # 自动修复GitHub blob URL
    original_url = url
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        logger.info(f"自动修复GitHub URL：{original_url} → {url}")
    
    # 获取候选URL列表
    candidate_urls = replace_github_domain(url)
    
    # 分级超时（CI环境更快超时）
    timeouts = [3, 5, 10, 15, 15] if os.getenv('CI') else [5, 10, 15, 15, 15]
    
    for idx, candidate in enumerate(candidate_urls):
        current_timeout = timeouts[min(idx, len(timeouts)-1)]
        try:
            logger.debug(f"尝试抓取 [{idx+1}/{len(candidate_urls)}]: {candidate} (超时：{current_timeout}s)")
            response = requests.get(
                candidate,
                headers=headers,
                timeout=current_timeout,
                verify=False,
                allow_redirects=True,
                stream=False  # 禁用流式下载，加快速度
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
    """M3U精准提取（集成频道名标准化）"""
    # 增强M3U匹配规则（适配更多格式）
    m3u_pattern = re.compile(
        r"(#EXTINF:-?\d+.*?)\n\s*([^#\n\r\s].*?)(?=\s|#|$)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE
    )
    
    attr_pattern = re.compile(r'(\w+)-(\w+)="([^"]*)"')
    
    categorized_channels = OrderedDict()
    meta_list = []
    seen_raw_urls = set()
    
    matches = m3u_pattern.findall(content)
    logger.info(f"从M3U内容中匹配到 {len(matches)} 个原始条目")
    
    for raw_extinf, url in matches:
        url = url.strip()
        raw_extinf = raw_extinf.strip()
        
        # 跳过无效URL或完全重复的URL
        if not url or not url.startswith(("http://", "https://")) or url in seen_raw_urls:
            continue
        
        seen_raw_urls.add(url)
        url_source_mapping[url] = source_url
        
        # 解析属性
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
        
        # 提取频道名并标准化
        name_match = re.search(r',\s*(.+?)\s*$', raw_extinf)
        if tvg_name:
            channel_name = tvg_name.strip()
        elif name_match:
            channel_name = name_match.group(1).strip()
        standard_name = standardize_cctv_name(channel_name)
        
        group_title = group_title if group_title else "未分类"
        
        # 智能去重（基于标准化名称）
        if is_duplicate_channel(channel_name, url):
            logger.debug(f"跳过重复频道线路：[{standard_name}] {url[:50]}...")
            continue
        
        # 创建元信息
        meta = ChannelMeta(
            url=url,
            raw_extinf=raw_extinf,
            tvg_id=tvg_id,
            tvg_name=tvg_name,
            tvg_logo=tvg_logo,
            group_title=group_title,
            channel_name=channel_name,
            standard_name=standard_name,
            source_url=source_url
        )
        
        meta_list.append(meta)
        channel_meta_cache[url] = meta
        
        # 按标准化名称归类
        if group_title not in categorized_channels:
            categorized_channels[group_title] = []
        categorized_channels[group_title].append((standard_name, url))
    
    logger.info(f"M3U精准提取完成：{len(meta_list)}个有效频道（含多线路）")
    logger.info(f"识别的M3U分类：{list(categorized_channels.keys())}")
    
    return categorized_channels, meta_list

def extract_channels_from_content(content: str, source_url: str) -> OrderedDict:
    """智能提取频道（集成频道名标准化）"""
    categorized_channels = OrderedDict()
    
    if "#EXTM3U" in content:
        m3u_categorized, _ = extract_m3u_meta(content, source_url)
        categorized_channels = m3u_categorized
    else:
        lines = content.split('\n')
        current_group = "默认分类"
        seen_raw_urls = set()
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith(("//", "#", "/*", "*/")):
                # 增强分类识别规则
                if any(keyword in line.lower() for keyword in ['#分类', '#genre', '分类:', 'genre:', '==', '---', '★', '☆']):
                    group_match = re.search(r'[：:=](\S+)', line)
                    if group_match:
                        current_group = group_match.group(1).strip()
                    else:
                        current_group = re.sub(r'[#分类:genre:==\-—★☆]', '', line).strip() or "默认分类"
                    current_group = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9_()]', '', current_group)
                    logger.debug(f"智能识别分类：{current_group}")
                continue
            
            # 增强频道匹配规则（适配更多文本格式）
            pattern = r'([^,|#$]+)[,|#$]\s*(https?://[^\s,|#$]+)'
            matches = re.findall(pattern, line, re.IGNORECASE)
            if matches:
                for name, url in matches:
                    name = name.strip()
                    url = url.strip()
                    if not url or url in seen_raw_urls:
                        continue
                    
                    seen_raw_urls.add(url)
                    url_source_mapping[url] = source_url
                    
                    # 标准化频道名
                    standard_name = standardize_cctv_name(name)
                    
                    # 智能分类推断（基于标准化名称）
                    group_title = current_group
                    if "CCTV" in standard_name or "央视" in standard_name:
                        group_title = "央视频道"
                    elif any(keyword in standard_name for keyword in ['卫视', '江苏', '浙江', '湖南', '东方', '北京', '广东']):
                        group_title = "卫视频道"
                    elif any(keyword in standard_name for keyword in ['电影', '影视', '影院']):
                        group_title = "电影频道"
                    elif any(keyword in standard_name for keyword in ['体育', 'CCTV5', 'NBA', '足球']):
                        group_title = "体育频道"
                    elif any(keyword in standard_name for keyword in ['少儿', '动漫', '卡通']):
                        group_title = "少儿频道"
                    
                    # 智能去重（基于标准化名称）
                    if is_duplicate_channel(name, url):
                        logger.debug(f"跳过重复频道线路：[{standard_name}] {url[:50]}...")
                        continue
                    
                    # 创建元信息
                    raw_extinf = f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{standard_name}\" tvg-logo=\"\" group-title=\"{group_title}\",{standard_name}"
                    meta = ChannelMeta(
                        url=url,
                        raw_extinf=raw_extinf,
                        tvg_id="",
                        tvg_name=standard_name,
                        tvg_logo="",
                        group_title=group_title,
                        channel_name=name,
                        standard_name=standard_name,
                        source_url=source_url
                    )
                    channel_meta_cache[url] = meta
                    
                    if group_title not in categorized_channels:
                        categorized_channels[group_title] = []
                    categorized_channels[group_title].append((standard_name, url))
        
        logger.info(f"智能识别完成：{sum(len(v) for v in categorized_channels.values())}个有效频道（含多线路）")
        logger.info(f"智能识别的分类：{list(categorized_channels.keys())}")
    
    if not categorized_channels:
        categorized_channels["未分类频道"] = []
    
    return categorized_channels

def merge_channels(target: OrderedDict, source: OrderedDict):
    """合并频道（基于标准化名称智能去重）"""
    for category_name, channel_list in source.items():
        if category_name not in target:
            target[category_name] = []
        
        for name, url in channel_list:
            if not is_duplicate_channel(name, url):
                target[category_name].append((name, url))

def generate_summary(all_channels: OrderedDict):
    """生成汇总文件（展示标准化名称）"""
    summary_path = OUTPUT_FOLDER / "live_source_summary.txt"
    m3u_path = OUTPUT_FOLDER / "live_source_merged.m3u"
    
    try:
        # 统计每个标准化频道的线路数
        channel_line_count = {}
        for _, channel_list in all_channels.items():
            for name, _ in channel_list:
                channel_line_count[name] = channel_line_count.get(name, 0) + 1
        
        # 生成汇总TXT（增强可读性）
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("IPTV直播源汇总（标准化频道名 + 智能去重）\n")
            f.write("="*80 + "\n")
            f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"总线路数（含多线路）：{sum(len(ch_list) for _, ch_list in all_channels.items())}\n")
            f.write(f"独特频道数（标准化后）：{len(channel_line_count)}\n")
            f.write(f"分类数：{len(all_channels)}\n")
            f.write("="*80 + "\n\n")
            
            # 按分类排序输出（央视频道优先）
            sorted_categories = sorted(
                all_channels.keys(),
                key=lambda x: (0 if x == "央视频道" else 1 if x == "卫视频道" else 2, x)
            )
            
            for group_title in sorted_categories:
                channel_list = all_channels[group_title]
                f.write(f"【{group_title}】（{len(channel_list)}条线路，{len(set([n for n, _ in channel_list]))}个频道）\n")
                for idx, (name, url) in enumerate(channel_list, 1):
                    source = url_source_mapping.get(url, "未知来源")
                    line_num = channel_line_count[name]
                    f.write(f"{idx:>3}. {name:<25} 线路{line_num} | {url}\n")
                    f.write(f"      来源：{source}\n")
                f.write("\n")
        
        # 生成合并后的M3U文件（兼容更多播放器）
        with open(m3u_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U x-tvg-url=\"https://epg.112114.xyz/pp.xml\"\n")  # 新增EPG地址
            f.write(f"# IPTV直播源合并文件（标准化频道名 + 智能去重）\n")
            f.write(f"# 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 总线路数：{sum(len(ch_list) for _, ch_list in all_channels.items())}\n\n")
            
            for group_title in sorted_categories:
                channel_list = all_channels[group_title]
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
    """主函数：抓取、提取、标准化、去重、汇总直播源"""
    try:
        # 清空缓存
        global channel_meta_cache, url_source_mapping, channel_url_map
        channel_meta_cache = {}
        url_source_mapping = {}
        channel_url_map = {}
        
        logger.info("===== 开始处理直播源（标准化+多线路版本） =====")
        
        # 从config.py/环境变量获取源URL列表
        source_urls = getattr(config, 'SOURCE_URLS', [])
        # 过滤空URL（避免无效请求）
        source_urls = [url.strip() for url in source_urls if url.strip()]
        
        if not source_urls:
            logger.error("未配置SOURCE_URLS，程序终止")
            return
        logger.info(f"从配置中读取到 {len(source_urls)} 个有效源URL")
        
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
        logger.info(f"  - 独特频道数（标准化后）：{total_unique_channels}")
        logger.info(f"  - 分类数：{len(all_channels)}")
        logger.info(f"  - 分类列表：{list(all_channels.keys())}")
        
        if failed_urls:
            logger.warning(f"  - 失败的源：{', '.join(failed_urls)}")
        
        if total_lines > 0:
            generate_summary(all_channels)
        else:
            logger.warning("未提取到任何有效频道，跳过汇总文件生成")
        
        logger.info("\n===== 所有操作完成 =====")
        
    except Exception as e:
        logger.critical(f"程序执行异常：{str(e)}", exc_info=True)
        # 确保CI环境返回错误码
        if os.getenv('CI'):
            exit(1)

if __name__ == "__main__":
    main()
