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

# 导入配置文件
try:
    import config1
except ImportError:
    # 如果没有config1.py，创建默认配置
    class config1:
        SOURCE_URLS = []
        # 默认配置
        FETCH_TIMEOUT = 15
        LOG_LEVEL = "INFO"
    logging.warning("未找到config1.py，使用默认配置")

# 屏蔽SSL不安全请求警告
warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

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

# ===================== 初始化配置 =====================
# 确保 output 文件夹存在
OUTPUT_FOLDER = Path("output")
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

# 日志配置（修正拼写错误：basicconfig1 而非 basicconfig11）
LOG_FILE_PATH = OUTPUT_FOLDER / "iptv_process.log"
# 从配置读取日志级别
log_level = getattr(config1, 'LOG_LEVEL', "INFO").upper()
logging.basicconfig1(  # 关键修正：将basicconfig11改为basicconfig1
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, "w", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 全局存储
channel_meta_cache: Dict[str, ChannelMeta] = {}  # key: url, value: ChannelMeta
all_categories: Set[str] = set()  # 所有识别到的分类

# ===================== 核心工具函数 =====================
def clean_channel_name(channel_name: str) -> str:
    """标准化清洗频道名称"""
    if not channel_name:
        return ""
    
    # 保留特殊标识
    channel_name = re.sub(r'CCTV-?5\+', 'CCTV5+', channel_name)
    
    # 港澳台/凤凰卫视特殊处理
    channel_name = channel_name.replace("翡翠台", "TVB翡翠台")
    channel_name = channel_name.replace("凤凰中文", "凤凰卫视中文台")
    
    # 移除特殊字符
    cleaned_name = re.sub(r'[$「」()（）\s-]', '', channel_name)
    # 数字标准化
    cleaned_name = re.sub(r'(\D*)(\d+)(\D*)', lambda m: m.group(1) + str(int(m.group(2))) + m.group(3), cleaned_name)
    
    return cleaned_name.upper()

def normalize_url(url: str) -> str:
    """URL标准化，用于去重"""
    if not url:
        return ""
    
    # 移除URL参数（部分参数不影响播放）
    url = url.split('?', 1)[0]
    # 移除锚点
    url = url.split('#', 1)[0]
    # 移除自定义后缀（如$IPv4(100ms)）
    url = url.split('$', 1)[0]
    # 统一为小写
    return url.strip().lower()

# ===================== GitHub URL修复 =====================
def replace_github_domain(url: str) -> List[str]:
    """替换GitHub域名，生成候选URL列表"""
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
    
    # 添加代理前缀
    proxy_urls = []
    for base_url in candidate_urls:
        for proxy in PROXY_PREFIXES:
            if not base_url.startswith(proxy):
                proxy_url = proxy + base_url
                if proxy_url not in proxy_urls:
                    proxy_urls.append(proxy_url)
    
    candidate_urls.extend(proxy_urls)
    # 去重并限制数量
    unique_urls = list(dict.fromkeys(candidate_urls))
    
    return unique_urls[:5]

def fetch_url_with_retry(url: str) -> Optional[str]:
    """带重试的URL抓取（自动修复GitHub URL）"""
    # 从配置读取超时时间
    fetch_timeout = getattr(config1, 'FETCH_TIMEOUT', 15)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # 自动修复GitHub blob URL
    original_url = url
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        logger.info(f"自动修复GitHub URL：{original_url} → {url}")
    
    candidate_urls = replace_github_domain(url)
    
    # 分级超时
    timeouts = [5, 10, fetch_timeout]
    
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

# ===================== M3U精准提取 =====================
def extract_m3u_meta(content: str, source_url: str) -> Tuple[OrderedDict, List[ChannelMeta]]:
    """
    M3U精准提取（完整保留原始#EXTINF行）
    :return: (按原始group-title分类的频道字典, 完整的ChannelMeta列表)
    """
    # 匹配完整的M3U条目：#EXTINF行 + URL
    m3u_pattern = re.compile(
        r"(#EXTINF:-?\d+.*?)\n\s*([^#\n\r\s].*?)(?=\s|#|$)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE
    )
    
    # 匹配#EXTINF中的属性
    attr_pattern = re.compile(r'(\w+)-(\w+)="([^"]*)"')
    
    categorized_channels = OrderedDict()
    meta_list = []
    seen_normalized_urls = set()  # 用于去重的标准化URL集合
    
    matches = m3u_pattern.findall(content)
    logger.info(f"M3U格式检测：发现{len(matches)}个潜在频道条目")
    
    for raw_extinf, url in matches:
        url = url.strip()
        raw_extinf = raw_extinf.strip()
        
        # 跳过无效URL
        if not url or not url.startswith(("http://", "https://")):
            continue
        
        # URL去重（基于标准化URL）
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
        
        # 使用原始group-title，无则设为"未分类"
        group_title = group_title if group_title else "未分类"
        all_categories.add(group_title)
        
        # 创建完整的元信息对象
        meta = ChannelMeta(
            url=url,
            raw_extinf=raw_extinf,
            tvg_id=tvg_id,
            tvg_name=tvg_name,
            tvg_logo=tvg_logo,
            group_title=group_title,
            channel_name=channel_name,
            clean_channel_name=clean_channel_name(channel_name),
            source_url=source_url
        )
        
        meta_list.append(meta)
        channel_meta_cache[url] = meta
        
        # 添加到分类字典
        if group_title not in categorized_channels:
            categorized_channels[group_title] = []
        categorized_channels[group_title].append((channel_name, url))
    
    logger.info(f"M3U精准提取完成：{len(meta_list)}个唯一频道")
    logger.info(f"M3U识别的分类：{sorted(list(all_categories))}")
    
    return categorized_channels, meta_list

# ===================== 智能分类识别 =====================
def extract_channels_from_content(content: str, source_url: str) -> OrderedDict:
    """
    提取频道和URL（增强格式兼容，智能识别分类）
    :return: 按分类组织的唯一频道字典
    """
    categorized_channels = OrderedDict()
    seen_normalized_urls = set()  # 用于去重的标准化URL集合
    
    # 优先处理M3U格式（完整保留元信息）
    if "#EXTM3U" in content:
        m3u_categorized, _ = extract_m3u_meta(content, source_url)
        categorized_channels = m3u_categorized
        
        # 更新已见URL（标准化）
        for _, ch_list in m3u_categorized.items():
            for _, url in ch_list:
                seen_normalized_urls.add(normalize_url(url))
    else:
        # 从普通文本中智能提取
        lines = content.split('\n')
        current_group = "默认分类"
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith(("//", "#", "/*", "*/")):
                # 识别分类行（支持多种格式）
                if any(keyword in line.lower() for keyword in ['#分类', '#genre', '分类:', 'genre:', '==', '---']):
                    # 提取分类名称
                    group_match = re.search(r'[：:=](\S+)', line)
                    if group_match:
                        current_group = group_match.group(1).strip()
                    else:
                        current_group = re.sub(r'[#分类:genre:==\-—]', '', line).strip() or "默认分类"
                    # 清理特殊字符
                    current_group = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9_()]', '', current_group)
                    all_categories.add(current_group)
                    logger.debug(f"智能识别分类：{current_group}")
                continue
            
            # 匹配频道名,URL格式（支持多种分隔符）
            pattern = r'([^,|#$]+)[,|#$]\s*(https?://[^\s,|#$]+)'
            matches = re.findall(pattern, line, re.IGNORECASE)
            
            if matches:
                for name, url in matches:
                    name = name.strip()
                    url = url.strip()
                    
                    # URL标准化去重
                    normalized_url = normalize_url(url)
                    if not url or normalized_url in seen_normalized_urls:
                        continue
                    seen_normalized_urls.add(normalized_url)
                    
                    # 智能分类推断
                    group_title = current_group
                    if any(keyword in name for keyword in ['CCTV', '央视', '中央']):
                        group_title = "央视频道"
                    elif any(keyword in name for keyword in ['卫视', '江苏', '浙江', '湖南']):
                        group_title = "卫视频道"
                    elif any(keyword in name for keyword in ['电影', '影视']):
                        group_title = "电影频道"
                    elif any(keyword in name for keyword in ['体育', 'CCTV5']):
                        group_title = "体育频道"
                    elif any(keyword in name for keyword in ['少儿', '卡通']):
                        group_title = "少儿频道"
                    
                    all_categories.add(group_title)
                    
                    # 生成元信息
                    raw_extinf = f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{name}\" tvg-logo=\"\" group-title=\"{group_title}\",{name}"
                    meta = ChannelMeta(
                        url=url,
                        raw_extinf=raw_extinf,
                        tvg_id="",
                        tvg_name=name,
                        tvg_logo="",
                        group_title=group_title,
                        channel_name=name,
                        clean_channel_name=clean_channel_name(name),
                        source_url=source_url
                    )
                    
                    channel_meta_cache[url] = meta
                    
                    # 确保分类存在
                    if group_title not in categorized_channels:
                        categorized_channels[group_title] = []
                    categorized_channels[group_title].append((name, url))
        
        # 处理剩余的单独URL
        pattern3 = r'(https?://[^\s]+)'
        matches3 = re.findall(pattern3, content, re.IGNORECASE | re.MULTILINE)
        
        for url in matches3:
            url = url.strip()
            normalized_url = normalize_url(url)
            
            if not url or normalized_url in seen_normalized_urls:
                continue
            seen_normalized_urls.add(normalized_url)
            
            # 从URL中提取频道名
            channel_name = "未知频道"
            url_parts = url.split('/')
            for part in url_parts:
                if part and len(part) > 3 and not part.startswith(('http', 'www', 'live', 'stream')):
                    channel_name = part
                    break
            
            # 智能分类
            group_title = "其他频道"
            if any(keyword in channel_name for keyword in ['CCTV', '央视']):
                group_title = "央视频道"
            elif any(keyword in channel_name for keyword in ['卫视']):
                group_title = "卫视频道"
            
            all_categories.add(group_title)
            
            # 生成元信息
            raw_extinf = f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{channel_name}\" tvg-logo=\"\" group-title=\"{group_title}\",{channel_name}"
            meta = ChannelMeta(
                url=url,
                raw_extinf=raw_extinf,
                tvg_id="",
                tvg_name=channel_name,
                tvg_logo="",
                group_title=group_title,
                channel_name=channel_name,
                clean_channel_name=clean_channel_name(channel_name),
                source_url=source_url
            )
            
            channel_meta_cache[url] = meta
            
            # 添加到分类字典
            if group_title not in categorized_channels:
                categorized_channels[group_title] = []
            categorized_channels[group_title].append((channel_name, url))
    
    # 确保至少有一个分类
    if not categorized_channels:
        categorized_channels["未分类频道"] = []
        all_categories.add("未分类频道")
    
    logger.info(f"智能提取完成：{sum(len(v) for v in categorized_channels.values())}个唯一频道")
    logger.info(f"智能识别的分类：{sorted(list(all_categories))}")
    
    return categorized_channels

# ===================== URL去重汇总 =====================
def merge_and_deduplicate_channels(all_sources: List[OrderedDict]) -> OrderedDict:
    """
    合并多个来源的频道，基于URL去重
    :param all_sources: 多个来源的分类频道字典列表
    :return: 去重后的汇总字典
    """
    merged_channels = OrderedDict()
    global_seen_urls = set()  # 全局URL去重（标准化）
    
    logger.info("\n开始合并并去重所有频道...")
    
    for source_idx, source_channels in enumerate(all_sources):
        logger.info(f"处理第{source_idx+1}个来源，包含{len(source_channels)}个分类")
        
        for group_title, channel_list in source_channels.items():
            # 初始化分类
            if group_title not in merged_channels:
                merged_channels[group_title] = []
            
            # 遍历频道，去重添加
            for channel_name, url in channel_list:
                normalized_url = normalize_url(url)
                
                # 全局URL去重
                if normalized_url in global_seen_urls:
                    logger.debug(f"全局去重：跳过重复URL {url[:60]}")
                    continue
                
                global_seen_urls.add(normalized_url)
                merged_channels[group_title].append((channel_name, url))
    
    # 按分类名称排序
    sorted_merged = OrderedDict()
    for category in sorted(merged_channels.keys()):
        sorted_merged[category] = merged_channels[category]
    
    total_channels = sum(len(v) for v in sorted_merged.values())
    logger.info(f"合并去重完成：总计{len(sorted_merged)}个分类，{total_channels}个唯一频道")
    logger.info(f"最终分类列表：{sorted(list(sorted_merged.keys()))}")
    
    return sorted_merged

def generate_summary_files(merged_channels: OrderedDict):
    """生成去重汇总后的文件"""
    # 文件路径
    summary_m3u = OUTPUT_FOLDER / "iptv_summary.m3u"
    summary_txt = OUTPUT_FOLDER / "iptv_summary.txt"
    summary_report = OUTPUT_FOLDER / "summary_report.txt"
    
    try:
        # 写入M3U文件
        with open(summary_m3u, "w", encoding="utf-8") as f_m3u:
            # M3U头部
            f_m3u.write("#EXTM3U x-tvg-url=\"\"\n")
            f_m3u.write(f"# IPTV直播源汇总（URL去重版）\n")
            f_m3u.write(f"# 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f_m3u.write(f"# 总分类数：{len(merged_channels)} | 总频道数：{sum(len(v) for v in merged_channels.values())}\n\n")
            
            # 按分类写入
            for group_title, channel_list in merged_channels.items():
                f_m3u.write(f"# ===== {group_title}（{len(channel_list)}个频道） =====\n")
                
                for channel_name, url in channel_list:
                    # 获取原始EXTINF或生成
                    meta = channel_meta_cache.get(url)
                    if meta and meta.raw_extinf:
                        f_m3u.write(meta.raw_extinf + "\n")
                    else:
                        f_m3u.write(
                            f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{channel_name}\" "
                            f"tvg-logo=\"\" group-title=\"{group_title}\",{channel_name}\n"
                        )
                    f_m3u.write(url + "\n\n")
        
        # 写入TXT文件（简易格式）
        with open(summary_txt, "w", encoding="utf-8") as f_txt:
            for group_title, channel_list in merged_channels.items():
                f_txt.write(f"{group_title},#genre#\n")
                for channel_name, url in channel_list:
                    f_txt.write(f"{channel_name},{url}\n")
        
        # 生成汇总报告
        with open(summary_report, "w", encoding="utf-8") as f_report:
            f_report.write("IPTV直播源汇总报告\n")
            f_report.write("="*60 + "\n")
            f_report.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f_report.write(f"总分类数：{len(merged_channels)}\n")
            f_report.write(f"总唯一频道数：{sum(len(v) for v in merged_channels.values())}\n\n")
            
            f_report.write("分类详情：\n")
            f_report.write("-"*60 + "\n")
            for idx, (category, channels) in enumerate(merged_channels.items(), 1):
                f_report.write(f"{idx:2d}. {category:<20} {len(channels)}个频道\n")
            
            f_report.write("\n频道详情（按分类）：\n")
            f_report.write("-"*60 + "\n")
            for category, channels in merged_channels.items():
                f_report.write(f"\n【{category}】\n")
                for channel_name, url in channels:
                    f_report.write(f"  {channel_name:<20} {url[:80]}\n")
        
        logger.info(f"\n汇总文件生成完成：")
        logger.info(f"  - M3U格式：{summary_m3u}")
        logger.info(f"  - TXT格式：{summary_txt}")
        logger.info(f"  - 汇总报告：{summary_report}")
        
    except Exception as e:
        logger.error(f"生成汇总文件失败：{str(e)}", exc_info=True)

# ===================== 主程序 =====================
def main():
    """主函数：处理IPTV源，去重汇总"""
    start_time = time.time()
    
    # 从config1.py读取源URL列表
    SOURCE_URLS = getattr(config1, 'SOURCE_URLS', [])
    
    if not SOURCE_URLS:
        logger.warning("config1.py中未配置SOURCE_URLS，使用测试内容演示...")
        # 演示用：创建测试内容
        test_content = """#EXTM3U
#EXTINF:-1 tvg-id="cctv1" tvg-name="CCTV1" tvg-logo="" group-title="央视频道",CCTV1
http://test.com/cctv1.m3u8
#EXTINF:-1 tvg-id="hunan" tvg-name="湖南卫视" tvg-logo="" group-title="卫视频道",湖南卫视
http://test.com/hunan.m3u8?token=123
#EXTINF:-1 tvg-id="hunan" tvg-name="湖南卫视" tvg-logo="" group-title="卫视频道",湖南卫视
http://test.com/hunan.m3u8$IPv4(100ms)
"""
        # 处理测试内容
        test_channels, _ = extract_m3u_meta(test_content, "test_source")
        all_sources = [test_channels]
    else:
        logger.info(f"从config1.py读取到 {len(SOURCE_URLS)} 个源URL")
        # 抓取并处理所有源
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
        # 生成汇总文件
        generate_summary_files(merged_channels)
    
    # 统计耗时
    elapsed = time.time() - start_time
    logger.info(f"\n===== 处理完成 | 总耗时：{elapsed:.2f}秒 =====")

if __name__ == "__main__":
    main()
