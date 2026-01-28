import re
import requests
import logging
import warnings
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set
import config  # 导入配置文件
import os

# ===================== 基础配置 =====================
# 屏蔽SSL不安全请求警告
warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

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
    """频道元信息（完整保留原始M3U标签）"""
    url: str  # 必填：播放URL
    raw_extinf: str = ""  # 完整的原始#EXTINF行
    tvg_id: Optional[str] = None  # 原始tvg-id
    tvg_name: Optional[str] = None  # 原始tvg-name
    tvg_logo: Optional[str] = None  # 原始tvg-logo
    group_title: Optional[str] = None  # 标准化后的group-title
    channel_name: Optional[str] = None  # 标准化后的频道名
    source_url: str = ""  # 来源URL

# 全局存储
channel_meta_cache: Dict[str, ChannelMeta] = {}  # key: url, value: ChannelMeta
url_source_mapping: Dict[str, str] = {}  # url -> 来源URL

# ===================== 核心工具函数 =====================
def clean_group_title(group_title: str) -> str:
    """
    标准化group-title：
    1. 优先匹配config中的地区→频道映射
    2. 过滤emoji、特殊符号，保留核心文字
    :param group_title: 原始group-title（含emoji/特殊符号/地区名称）
    :return: 标准化后的纯文字group-title
    """
    if not group_title:
        return "未分类"
    
    # 步骤1：优先匹配config中的group-title映射（精确匹配）
    original_title = group_title.strip()
    if original_title in config.group_title_mapping:
        mapped_title = config.group_title_mapping[original_title]
        logger.debug(f"group-title映射匹配：{original_title} → {mapped_title}")
        group_title = mapped_title
    else:
        # 模糊匹配（处理带emoji/特殊符号的情况，如"🔥安徽地区"）
        # 提取纯文字部分再匹配映射
        pure_text = ''.join(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]+', original_title))
        if pure_text in config.group_title_mapping:
            mapped_title = config.group_title_mapping[pure_text]
            logger.debug(f"group-title模糊映射匹配：{original_title} → {mapped_title}")
            group_title = mapped_title
    
    # 步骤2：过滤emoji、特殊符号，保留核心文字
    cleaned = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9_\(\)]+', group_title)
    result = ''.join(cleaned).strip() or "未分类"
    
    # 步骤3：长度兜底（超过20字截取）
    if len(result) > 20:
        result = result[:20]
    
    logger.debug(f"group-title最终标准化：{original_title} → {result}")
    return result

def global_replace_cctv_name(content: str) -> str:
    """
    对源内容做全局央视频道名称替换（先长后短，避免部分匹配）
    :param content: 抓取的原始源内容
    :return: 替换后的标准化内容
    """
    if not content:
        return content
    
    # 合并映射并按名称长度降序排序（先替换长名称，避免"CCTV5"先替换导致"CCTV5+"匹配失败）
    all_mappings = {}
    # 先加入基础映射
    all_mappings.update(config.cntvNamesReverse)
    # 再加入别名映射（别名映射可覆盖基础映射，若有重复）
    all_mappings.update(config.cctv_alias)
    # 按名称长度降序、名称字母降序排序，确保长名称优先替换
    sorted_mappings = sorted(all_mappings.items(), key=lambda x: (-len(x[0]), x[0]))
    
    # 全局替换
    replaced_content = content
    for old_name, new_name in sorted_mappings:
        if old_name in replaced_content:
            replaced_content = replaced_content.replace(old_name, new_name)
            logger.debug(f"全局替换频道名：{old_name} → {new_name}")
    
    return replaced_content

def standardize_cctv_name(channel_name: str) -> str:
    """
    标准化单个央视频道名称（兜底处理，防止全局替换遗漏）
    :param channel_name: 原始频道名称
    :return: 标准化后的名称
    """
    if not channel_name:
        return channel_name
    
    # 先匹配基础映射
    if channel_name in config.cntvNamesReverse:
        return config.cntvNamesReverse[channel_name]
    # 再匹配别名映射
    if channel_name in config.cctv_alias:
        return config.cctv_alias[channel_name]
    # 模糊匹配（处理带多余字符的情况）
    normalized_name = channel_name.strip()
    for raw_name, standard_name in config.cntvNamesReverse.items():
        if raw_name in normalized_name:
            return standard_name
    for alias_name, standard_name in config.cctv_alias.items():
        if alias_name in normalized_name:
            return standard_name
    # 无匹配则返回原名称
    return channel_name

def replace_github_domain(url: str) -> List[str]:
    """替换GitHub域名（自动修复GitHub URL）"""
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
    # 去重并限制数量
    unique_urls = list(dict.fromkeys(candidate_urls + proxy_urls))
    return unique_urls[:5]

def fetch_url_with_retry(url: str, timeout: int = 15) -> Optional[str]:
    """带重试的URL抓取（自动修复GitHub URL）"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    # 自动修复GitHub blob URL
    original_url = url
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        logger.info(f"自动修复GitHub URL：{original_url} → {url}")
    # 获取候选URL列表
    candidate_urls = replace_github_domain(url)
    # 分级超时
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
    """
    M3U精准提取（标准化group-title和频道名）
    :return: (按标准化group-title分类的频道字典, 完整的ChannelMeta列表)
    """
    m3u_pattern = re.compile(
        r"(#EXTINF:-?\d+.*?)\n\s*([^#\n\r\s].*?)(?=\s|#|$)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE
    )
    attr_pattern = re.compile(r'(\w+)-(\w+)="([^"]*)"')
    categorized_channels = OrderedDict()
    meta_list = []
    seen_urls = set()
    matches = m3u_pattern.findall(content)
    logger.info(f"从M3U内容中匹配到 {len(matches)} 个原始条目")
    
    for raw_extinf, url in matches:
        url = url.strip()
        raw_extinf = raw_extinf.strip()
        # 跳过无效URL或重复URL
        if not url or not url.startswith(("http://", "https://")) or url in seen_urls:
            continue
        seen_urls.add(url)
        url_source_mapping[url] = source_url
        
        # 解析#EXTINF属性
        tvg_id, tvg_name, tvg_logo, group_title = None, None, None, None
        channel_name = "未知频道"
        attr_matches = attr_pattern.findall(raw_extinf)
        for attr1, attr2, value in attr_matches:
            if attr1 == "tvg" and attr2 == "id":
                tvg_id = value
            elif attr1 == "tvg" and attr2 == "name":
                tvg_name = standardize_cctv_name(value)  # 标准化tvg-name
            elif attr1 == "tvg" and attr2 == "logo":
                tvg_logo = value
            elif attr1 == "group" and attr2 == "title":
                group_title = clean_group_title(value)  # 核心修改：标准化group-title
        
        # 提取并标准化逗号后的频道名
        name_match = re.search(r',\s*(.+?)\s*$', raw_extinf)
        if name_match:
            channel_name = name_match.group(1).strip()
            channel_name = standardize_cctv_name(channel_name)
        
        # 最终标准化group-title（兜底）
        group_title = clean_group_title(group_title)
        
        # 创建元信息对象（存储标准化后的名称和分类）
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
        
        # 添加到分类字典（基于标准化后的group-title）
        if group_title not in categorized_channels:
            categorized_channels[group_title] = []
        categorized_channels[group_title].append((channel_name, url))
    
    logger.info(f"M3U精准提取完成：{len(meta_list)}个有效频道")
    logger.info(f"识别的标准化分类：{list(categorized_channels.keys())}")
    return categorized_channels, meta_list

def extract_channels_from_content(content: str, source_url: str) -> OrderedDict:
    """
    智能提取频道（标准化group-title和频道名）
    先全局替换源内容中的不规范名称，再解析
    :return: 按标准化分类整理的频道字典
    """
    categorized_channels = OrderedDict()
    # 优先处理M3U格式
    if "#EXTM3U" in content:
        m3u_categorized, _ = extract_m3u_meta(content, source_url)
        categorized_channels = m3u_categorized
    else:
        # 智能识别普通文本中的频道和分类
        lines = content.split('\n')
        current_group = "默认分类"
        seen_urls = set()
        for line in lines:
            line = line.strip()
            if not line or line.startswith(("//", "#", "/*", "*/")):
                # 识别分类行并标准化
                if any(keyword in line.lower() for keyword in ['#分类', '#genre', '分类:', 'genre:', '==', '---']):
                    group_match = re.search(r'[：:=](\S+)', line)
                    if group_match:
                        current_group = group_match.group(1).strip()
                    else:
                        current_group = re.sub(r'[#分类:genre:==\-—]', '', line).strip() or "默认分类"
                    # 核心修改：标准化智能识别的分类名（含映射匹配）
                    current_group = clean_group_title(current_group)
                    logger.debug(f"智能识别并标准化分类：{current_group}")
                    continue
            # 匹配频道名,URL格式
            pattern = r'([^,|#$]+)[,|#$]\s*(https?://[^\s,|#$]+)'
            matches = re.findall(pattern, line, re.IGNORECASE)
            if matches:
                for name, url in matches:
                    name = name.strip()
                    url = url.strip()
                    if not url or url in seen_urls:
                        continue
                    # 标准化名称（兜底）
                    standard_name = standardize_cctv_name(name)
                    seen_urls.add(url)
                    url_source_mapping[url] = source_url
                    
                    # 智能分类推断（基于标准化名称）+ 标准化分类名
                    group_title = current_group
                    if any(keyword in standard_name for keyword in ['CCTV', '央视', '中央']):
                        group_title = "央视频道"  # 固定分类名，已标准化
                    elif any(keyword in standard_name for keyword in ['卫视', '江苏', '浙江', '湖南', '东方']):
                        group_title = "卫视频道"  # 固定分类名，已标准化
                    elif any(keyword in standard_name for keyword in ['电影', '影视']):
                        group_title = "电影频道"  # 固定分类名，已标准化
                    elif any(keyword in standard_name for keyword in ['体育', 'CCTV5']):
                        group_title = "体育频道"  # 固定分类名，已标准化
                    # 最终标准化分类名（兜底，含映射匹配）
                    group_title = clean_group_title(group_title)
                    
                    # 创建元信息
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
                    
                    # 添加到分类字典（基于标准化后的group-title）
                    if group_title not in categorized_channels:
                        categorized_channels[group_title] = []
                    categorized_channels[group_title].append((standard_name, url))
        
        logger.info(f"智能识别完成：{sum(len(v) for v in categorized_channels.values())}个有效频道")
        logger.info(f"识别的标准化分类：{list(categorized_channels.keys())}")
    
    # 确保至少有一个分类
    if not categorized_channels:
        categorized_channels["未分类"] = []
    return categorized_channels

def merge_channels(target: OrderedDict, source: OrderedDict):
    """合并频道（URL去重，基于标准化分类）"""
    url_set = set()
    # 收集已有的URL
    for category_name, ch_list in target.items():
        for _, url in ch_list:
            url_set.add(url)
    # 合并源数据（只添加新URL，分类名已标准化，可直接合并）
    for category_name, channel_list in source.items():
        if category_name not in target:
            target[category_name] = []
        for name, url in channel_list:
            if url not in url_set:
                target[category_name].append((name, url))
                url_set.add(url)

def generate_summary(all_channels: OrderedDict):
    """生成汇总文件（修复正则转义问题，兼容特殊字符）"""
    summary_path = OUTPUT_FOLDER / "live_source_summary.txt"
    m3u_path = OUTPUT_FOLDER / "live_source_merged.m3u"
    try:
        # 生成汇总TXT
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("IPTV直播源汇总（URL去重+频道名标准化+分类名标准化）\n")
            f.write("="*80 + "\n")
            f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"总频道数：{sum(len(ch_list) for _, ch_list in all_channels.items())}\n")
            f.write(f"分类数：{len(all_channels)}\n")
            f.write("="*80 + "\n\n")
            # 按分类写入（分类名已标准化）
            for group_title, channel_list in all_channels.items():
                f.write(f"【{group_title}】（{len(channel_list)}个频道）\n")
                for idx, (name, url) in enumerate(channel_list, 1):
                    source = url_source_mapping.get(url, "未知来源")
                    f.write(f"{idx:>3}. {name:<20} {url}\n")
                    f.write(f"      来源：{source}\n")
                f.write("\n")
        
        # 生成合并后的M3U文件（修复正则转义问题）
        with open(m3u_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U x-tvg-url=\"\"\n")
            f.write(f"# IPTV直播源合并文件（URL去重+频道名标准化+分类名标准化）\n")
            f.write(f"# 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 总频道数：{sum(len(ch_list) for _, ch_list in all_channels.items())}\n\n")
            
            for group_title, channel_list in all_channels.items():
                f.write(f"# ===== {group_title}（{len(channel_list)}个频道） =====\n")
                for name, url in channel_list:
                    meta = channel_meta_cache.get(url)
                    if meta and meta.raw_extinf:
                        # 替换group-title（字符串操作，避免正则转义）
                        standard_extinf = meta.raw_extinf
                        if 'group-title="' in standard_extinf:
                            start_idx = standard_extinf.find('group-title="') + len('group-title="')
                            end_idx = standard_extinf.find('"', start_idx)
                            if end_idx > start_idx:
                                standard_extinf = standard_extinf[:start_idx] + group_title + standard_extinf[end_idx:]
                        
                        # 替换频道名（字符串分割+拼接，避免正则转义）
                        if ',' in standard_extinf:
                            extinf_part, old_name = standard_extinf.rsplit(',', 1)
                            # 转义频道名中的特殊字符
                            safe_name = name.replace('\\', '\\\\').replace('$', '\\$')
                            standard_extinf = extinf_part + ',' + safe_name
                        f.write(standard_extinf + "\n")
                    else:
                        # 直接生成标准化的EXTINF行
                        f.write(f"#EXTINF:-1 tvg-name=\"{name}\" group-title=\"{group_title}\",{name}\n")
                    f.write(url + "\n\n")
        
        logger.info(f"\n汇总文件生成完成：")
        logger.info(f"  - 汇总信息：{summary_path}")
        logger.info(f"  - 合并M3U：{m3u_path}")
        
    except Exception as e:
        logger.error(f"生成汇总文件失败：{str(e)}", exc_info=True)

# ===================== 主程序 =====================
def main():
    """主函数：抓取→全局替换名称→提取（标准化分类+频道名）→去重→汇总直播源"""
    try:
        # 清空缓存
        global channel_meta_cache, url_source_mapping
        channel_meta_cache = {}
        url_source_mapping = {}
        logger.info("===== 开始处理直播源（全量标准化版） =====")
        
        # 从config.py获取源URL列表
        source_urls = getattr(config, 'SOURCE_URLS', [])
        if not source_urls:
            logger.error("config.py中未配置SOURCE_URLS，程序终止")
            return
        logger.info(f"从配置中读取到 {len(source_urls)} 个源URL")
        
        # 初始化总频道字典
        all_channels = OrderedDict()
        failed_urls = []
        
        # 遍历所有源URL：抓取→全局替换→提取（标准化）→合并
        for idx, url in enumerate(source_urls, 1):
            logger.info(f"\n===== 处理第 {idx}/{len(source_urls)} 个源：{url} =====")
            # 1. 抓取源内容
            content = fetch_url_with_retry(url)
            if content is None:
                failed_urls.append(url)
                continue
            # 2. 全局替换源内容中的不规范央视频道名
            content = global_replace_cctv_name(content)
            # 3. 提取频道（同时标准化group-title和频道名）
            extracted_channels = extract_channels_from_content(content, url)
            # 4. 合并频道（自动去重，分类已标准化）
            merge_channels(all_channels, extracted_channels)
        
        # 统计结果
        total_channels = sum(len(ch_list) for _, ch_list in all_channels.items())
        logger.info(f"\n===== 处理完成统计 =====")
        logger.info(f"  - 源URL总数：{len(source_urls)}")
        logger.info(f"  - 失败源数：{len(failed_urls)}")
        logger.info(f"  - 去重后总频道数：{total_channels}")
        logger.info(f"  - 标准化分类数：{len(all_channels)}")
        logger.info(f"  - 标准化分类列表：{list(all_channels.keys())}")
        if failed_urls:
            logger.info(f"  - 失败的源：{', '.join(failed_urls)}")
        
        # 生成汇总文件
        if total_channels > 0:
            generate_summary(all_channels)
        logger.info("\n===== 所有操作完成 =====")
    except Exception as e:
        logger.critical(f"程序执行异常：{str(e)}", exc_info=True)

if __name__ == "__main__":
    main()
