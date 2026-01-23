# main.py
import re
import asyncio
import aiohttp
import requests
import logging
import os
import time
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
import difflib

# 导入外部配置文件
import config

# ===================== 初始化 =====================
# 创建必要文件夹
for dir_path in [config.OUTPUT_DIR, config.PIC_DIR]:
    dir_path.mkdir(exist_ok=True)

# 日志配置（优化格式、避免重复输出）
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.handlers.clear()
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# 文件处理器（追加模式）
file_handler = logging.FileHandler(config.LOG_FILE, "a", encoding="utf-8")
file_handler.setFormatter(formatter)
# 控制台处理器
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# ===================== 数据结构 =====================
@dataclass
class SpeedTestResult:
    url: str
    latency: Optional[float] = None  # 延迟（毫秒）
    resolution: Optional[str] = None  # 分辨率
    success: bool = False  # 是否成功
    error: Optional[str] = None  # 错误信息
    test_time: float = 0  # 测试时间戳

# ===================== 核心工具函数 =====================
def clean_channel_name(channel_name: str) -> str:
    """标准化清洗频道名称，提升匹配率"""
    if not channel_name:
        return ""
    # 移除特殊字符、空格，统一大写
    cleaned = re.sub(r'[-$「」«»()（）\s+]', '', channel_name)
    # 数字标准化（如 05 → 5）
    cleaned = re.sub(r'(\D*)(\d+)', lambda m: m.group(1) + str(int(m.group(2))), cleaned)
    return cleaned.upper()

def is_ipv6(url: str) -> bool:
    """判断URL是否为IPv6地址"""
    if not url:
        return False
    return re.match(r'^http:\/\/\[[0-9a-fA-F:]+\]', url) is not None

def find_similar_name(target_name: str, name_list: list, cutoff: float = 0.6) -> str | None:
    """模糊匹配最相似的频道名"""
    if not target_name or not name_list:
        return None
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=cutoff)
    return matches[0] if matches else None

def sort_and_filter_urls(urls: list, written_urls: set) -> list:
    """排序并过滤URL（去重、黑名单、IP优先级）"""
    if not urls:
        return []
    
    # 1. 基础过滤：非空、未写入、不在黑名单
    filtered = [
        url.strip() for url in urls
        if url and url.strip() and url not in written_urls
        and not any(bl in url for bl in config.URL_BLACKLIST)
    ]
    
    # 2. 按IP版本优先级排序
    if config.IP_VERSION_PRIORITY == "ipv6":
        filtered.sort(key=lambda u: is_ipv6(u), reverse=True)
    else:
        filtered.sort(key=lambda u: is_ipv6(u))
    
    # 3. 更新已写入集合
    written_urls.update(filtered)
    return filtered

# ===================== 直播源抓取模块 =====================
class SourceFetcher:
    @staticmethod
    def parse_template() -> OrderedDict:
        """解析demo.txt模板，保留原始顺序"""
        template_channels = OrderedDict()
        current_category = None
        
        try:
            with open(config.TEMPLATE_FILE, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    
                    if "#genre#" in line:
                        current_category = line.split(",")[0].strip()
                        template_channels[current_category] = []
                        logger.debug(f"模板第{line_num}行：识别分类 {current_category}")
                    elif current_category:
                        channel_name = line.split(",")[0].strip()
                        template_channels[current_category].append(channel_name)
                        logger.debug(f"模板第{line_num}行：添加频道 {channel_name}")
        
        except FileNotFoundError:
            logger.error(f"模板文件不存在：{config.TEMPLATE_FILE}")
        except Exception as e:
            logger.error(f"解析模板失败：{e}", exc_info=True)
        
        return template_channels

    @staticmethod
    def parse_m3u_lines(lines: list) -> OrderedDict:
        """解析M3U格式的频道行"""
        channels = OrderedDict()
        current_category = None
        channel_name = ""
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            
            if line.startswith("#EXTINF"):
                # 优化正则：兼容频道名含逗号的情况
                match = re.search(r'group-title="(.*?)",(.*)', line)
                if match:
                    current_category = match.group(1).strip()
                    channel_name = match.group(2).strip()
                    if channel_name.startswith("CCTV"):
                        channel_name = clean_channel_name(channel_name)
                    if current_category not in channels:
                        channels[current_category] = []
                else:
                    logger.warning(f"M3U第{line_num}行格式异常：{line}")
            elif not line.startswith("#"):
                channel_url = line
                if current_category and channel_name and channel_url:
                    channels[current_category].append((channel_name, channel_url))
        
        return channels

    @staticmethod
    def parse_txt_lines(lines: list) -> OrderedDict:
        """解析TXT格式的频道行"""
        channels = OrderedDict()
        current_category = None
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            if "#genre#" in line:
                current_category = line.split(",")[0].strip()
                channels[current_category] = []
            elif current_category:
                match = re.match(r"^(.*?),(.*?)$", line)
                if match:
                    channel_name = match.group(1).strip()
                    if channel_name.startswith("CCTV"):
                        channel_name = clean_channel_name(channel_name)
                    # 处理多地址（#分隔）
                    channel_urls = match.group(2).strip().split('#')
                    for url in channel_urls:
                        url = url.strip()
                        if url:
                            channels[current_category].append((channel_name, url))
        
        return channels

    @staticmethod
    def fetch_channels(url: str) -> OrderedDict:
        """从URL抓取频道列表（自动识别M3U/TXT）"""
        channels = OrderedDict()
        
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or 'utf-8'
            lines = response.text.split("\n")
            
            # 判断格式
            is_m3u = any(line.startswith("#EXTINF") for line in lines[:15])
            logger.info(f"成功抓取 {url}，格式：{'m3u' if is_m3u else 'txt'}")
            
            # 解析内容
            if is_m3u:
                channels = SourceFetcher.parse_m3u_lines(lines)
            else:
                channels = SourceFetcher.parse_txt_lines(lines)
        
        except requests.RequestException as e:
            logger.error(f"抓取 {url} 失败：{e}", exc_info=True)
        
        return channels

    @staticmethod
    def merge_channels(target: OrderedDict, source: OrderedDict):
        """合并两个频道字典（去重）"""
        for category, channel_list in source.items():
            if category not in target:
                target[category] = []
            # 去重合并：基于（频道名+地址）去重
            existing = {(name, url) for name, url in target[category]}
            for name, url in channel_list:
                if (name, url) not in existing:
                    target[category].append((name, url))
                    existing.add((name, url))

    @staticmethod
    def match_channels(template_channels: OrderedDict, all_channels: OrderedDict) -> OrderedDict:
        """匹配模板频道与抓取到的频道"""
        matched_channels = OrderedDict()
        
        # 收集所有在线频道名
        all_online_names = []
        online_name_to_urls = {}
        for _, channel_list in all_channels.items():
            for name, url in channel_list:
                if name:
                    all_online_names.append(name)
                    online_name_to_urls.setdefault(name, []).append(url)
        
        # 遍历模板进行匹配
        for category, template_names in template_channels.items():
            matched_channels[category] = OrderedDict()
            for template_name in template_names:
                # 标准化后模糊匹配
                std_template_name = clean_channel_name(template_name)
                std_online_names = [clean_channel_name(n) for n in all_online_names]
                # 使用配置中的匹配阈值，提高匹配率
                similar_std_name = find_similar_name(std_template_name, std_online_names, cutoff=config.MATCH_CUTOFF)
                
                if similar_std_name:
                    # 找到原始名称
                    raw_name = all_online_names[std_online_names.index(similar_std_name)]
                    matched_channels[category][template_name] = online_name_to_urls.get(raw_name, [])
                    logger.debug(f"匹配成功：{template_name} → {raw_name}")
                else:
                    logger.warning(f"未匹配到频道：{template_name}")
        
        return matched_channels

    @staticmethod
    def get_matched_channels() -> Tuple[OrderedDict, OrderedDict]:
        """抓取并匹配频道，返回（匹配结果，模板频道）"""
        # 1. 解析模板
        template_channels = SourceFetcher.parse_template()
        if not template_channels:
            logger.error("模板解析为空，终止流程")
            return OrderedDict(), template_channels
        
        # 2. 抓取所有源URL
        if not config.SOURCE_URLS:
            logger.error("未配置SOURCE_URLS，终止流程")
            return OrderedDict(), template_channels
        
        all_channels = OrderedDict()
        for url in config.SOURCE_URLS:
            fetched = SourceFetcher.fetch_channels(url)
            SourceFetcher.merge_channels(all_channels, fetched)
        
        # 3. 匹配频道
        matched_channels = SourceFetcher.match_channels(template_channels, all_channels)
        return matched_channels, template_channels

# ===================== 测速模块 =====================
class SpeedTester:
    def __init__(self):
        self.session = None
    
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=config.TIMEOUT)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def measure_latency(self, url: str) -> SpeedTestResult:
        """测量单个URL的延迟和分辨率"""
        result = SpeedTestResult(url=url, test_time=time.time())
        
        for attempt in range(config.RETRY_TIMES + 1):
            try:
                start_time = time.time()
                async with self.session.get(url, ssl=False) as response:
                    elapsed_time = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        # 解析M3U8分辨率
                        resolution = "unknown"
                        content_type = response.headers.get("Content-Type", "")
                        if "application/vnd.apple.mpegurl" in content_type:
                            try:
                                content = await response.content.read(1024)
                                res_match = re.search(rb"RESOLUTION=(\d+x\d+)", content)
                                if res_match:
                                    resolution = res_match.group(1).decode()
                            except Exception as e:
                                logger.debug(f"解析分辨率失败 {url}: {str(e)}")
                        
                        result.latency = elapsed_time
                        result.resolution = resolution
                        result.success = True
                        logger.info(f"[{attempt+1}] {url[:50]} 成功 | 延迟: {elapsed_time:.2f}ms")
                        break
                    else:
                        result.error = f"HTTP {response.status}"
                        logger.warning(f"[{attempt+1}] {url[:50]} 失败 | 状态码: {response.status}")
            except asyncio.TimeoutError:
                result.error = "请求超时"
            except aiohttp.ClientConnectionError:
                result.error = "连接失败"
            except Exception as e:
                result.error = f"未知错误: {str(e)[:30]}"
            
            if attempt < config.RETRY_TIMES:
                await asyncio.sleep(1)
        
        return result
    
    async def batch_speed_test(self, urls: List[str]) -> List[SpeedTestResult]:
        """批量测速（带并发控制）"""
        results = []
        semaphore = asyncio.Semaphore(config.CONCURRENT_LIMIT)

        async def worker(url):
            async with semaphore:
                results.append(await self.measure_latency(url))

        tasks = [worker(url) for url in urls]
        await asyncio.gather(*tasks)
        return results

# ===================== M3U生成模块 =====================
class M3UGenerator:
    @staticmethod
    def generate_final_m3u(matched_channels: OrderedDict, template_channels: OrderedDict, speed_results: Dict[str, SpeedTestResult]):
        """生成最终的M3U文件（按模板顺序、每个频道保留10个最优URL）"""
        if not matched_channels or not template_channels:
            logger.warning("无有效频道数据，跳过文件生成")
            return
        
        # 文件路径
        output_m3u = config.OUTPUT_DIR / "live_sources_ipv4.m3u"
        report_file = config.OUTPUT_DIR / "speed_test_report.txt"
        
        # 已写入的URL（去重）
        written_urls = set()
        final_sources = []
        
        # 按模板顺序处理每个频道
        for category, template_names in template_channels.items():
            if category not in matched_channels:
                continue
            
            for channel_name in template_names:
                if channel_name not in matched_channels[category]:
                    continue
                
                # 获取该频道的所有URL
                raw_urls = matched_channels[category][channel_name]
                # 筛选符合延迟阈值的URL
                valid_urls = []
                for url in raw_urls:
                    result = speed_results.get(url)
                    if result and result.success and result.latency and result.latency <= config.LATENCY_THRESHOLD:
                        valid_urls.append((url, result.latency, result.resolution))
                
                if not valid_urls:
                    logger.warning(f"[{category}] {channel_name} 无有效URL（延迟超标）")
                    continue
                
                # 按延迟升序排序，取前N个最优URL（N=MAX_URLS_PER_CHANNEL）
                valid_urls.sort(key=lambda x: x[1])
                top_urls = valid_urls[:config.MAX_URLS_PER_CHANNEL]
                
                # 为每个URL生成频道条目（保留10个）
                for idx, (url, latency, resolution) in enumerate(top_urls):
                    if url not in written_urls:
                        written_urls.add(url)
                        # 频道名添加序号（如 央视1套_1、央视1套_2）
                        display_name = f"{channel_name}_{idx+1}" if idx > 0 else channel_name
                        final_sources.append((category, display_name, url, latency, resolution))
                        logger.info(f"[{category}] {display_name} | 延迟: {latency:.2f}ms | 分辨率: {resolution}")
        
        # 生成M3U文件
        try:
            with open(output_m3u, 'w', encoding='utf-8') as f:
                # M3U头部
                f.write('#EXTM3U\n')
                f.write(f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 排序规则: 按demo.txt模板顺序 | 延迟阈值: {config.LATENCY_THRESHOLD}ms\n")
                f.write(f"# 每个频道保留最优URL数量: {config.MAX_URLS_PER_CHANNEL}\n\n")
                
                # 写入每个频道
                for index, (group, name, url, latency, resolution) in enumerate(final_sources, 1):
                    # LOGO路径设为空，避免本地路径问题
                    extinf_line = (
                        f"#EXTINF:-1 tvg-id=\"{index}\" tvg-name=\"{name}\" "
                        f"tvg-logo=\"\" group-title=\"{group}\",{name} (延迟:{latency:.0f}ms)"
                    )
                    f.write(f"{extinf_line}\n{url}\n\n")
            
            logger.info(f"最终M3U生成成功：{output_m3u} | 总有效URL数：{len(final_sources)}")
        except Exception as e:
            logger.error(f"生成M3U失败：{e}", exc_info=True)
        
        # 生成测速报告
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write("IPTV直播源测速报告（按模板顺序）\n")
                f.write("="*80 + "\n")
                f.write(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"延迟阈值: {config.LATENCY_THRESHOLD}ms\n")
                f.write(f"每个频道保留URL数: {config.MAX_URLS_PER_CHANNEL}\n")
                f.write(f"总有效URL数: {len(final_sources)}\n\n")
                
                # 按频道分组展示报告
                channel_groups = {}
                for item in final_sources:
                    category, name, url, latency, resolution = item
                    base_name = name.split('_')[0] if '_' in name else name
                    if base_name not in channel_groups:
                        channel_groups[base_name] = []
                    channel_groups[base_name].append(item)
                
                for base_name, items in channel_groups.items():
                    f.write(f"【{base_name}】\n")
                    for i, (category, name, url, latency, resolution) in enumerate(items, 1):
                        f.write(f"  {i}. 分类: {category}\n")
                        f.write(f"     URL: {url[:100]}{'...' if len(url) > 100 else ''}\n")
                        f.write(f"     延迟: {latency:.2f}ms | 分辨率: {resolution}\n")
                    f.write("\n")
            
            logger.info(f"测速报告生成成功：{report_file}")
        except Exception as e:
            logger.error(f"生成报告失败：{e}", exc_info=True)

# ===================== 主程序 =====================
async def main():
    try:
        # 1. 抓取并匹配频道（按模板）
        logger.info("===== 开始抓取并匹配直播源 =====")
        matched_channels, template_channels = SourceFetcher.get_matched_channels()
        if not matched_channels:
            return
        
        # 2. 收集所有需要测速的URL
        all_urls = []
        for category in matched_channels.values():
            for urls in category.values():
                all_urls.extend(urls)
        all_urls = list(set(all_urls))  # 去重
        logger.info(f"===== 开始批量测速（共{len(all_urls)}个URL） =====")
        
        # 3. 批量测速
        async with SpeedTester() as tester:
            speed_results = await tester.batch_speed_test(all_urls)
        speed_result_map = {res.url: res for res in speed_results}
        
        # 4. 生成最终M3U和报告
        logger.info("===== 开始生成最终文件 =====")
        M3UGenerator.generate_final_m3u(matched_channels, template_channels, speed_result_map)
        
        logger.info("===== 全部流程执行完成 =====")
    
    except Exception as e:
        logger.critical(f"程序执行异常：{e}", exc_info=True)

if __name__ == "__main__":
    # 兼容Windows异步事件循环
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
