import asyncio
import aiohttp
import time
import logging
import os
from dataclasses import dataclass
from typing import List, Tuple, Optional, Set
from config import Config

# 实例化配置
config = Config()

# ===================== 初始化目录与日志 =====================
# 确保output文件夹存在（与主脚本同目录）
os.makedirs(config.OUTPUT_DIR, exist_ok=True)

# 日志配置（UTF-8编码，避免中文乱码，同时输出到文件和控制台）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===================== 数据类：存储单个URL测速结果 =====================
@dataclass
class SpeedTestResult:
    url: str
    latency: Optional[float] = None  # 延迟（毫秒），保留2位小数
    resolution: Optional[str] = None  # 分辨率（简化为unknown）
    success: bool = False  # 是否测试成功
    error: Optional[str] = None  # 错误信息（截断过长内容）
    test_time: float = 0  # 测试时间戳

# ===================== 远程文件下载工具类 =====================
class RemoteM3UDownloader:
    """异步下载远程M3U/纯文本URL文件，适配GitHub RAW链接，支持缓存、多编码兼容"""
    def __init__(self):
        self.session = None
        self.download_cache = {}  # 下载缓存，避免重复请求同一链接

    async def __aenter__(self):
        """创建异步会话，配置请求头与超时"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=config.TIMEOUT),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/plain, text/html, application/x-mpegurl, */*",
                "Accept-Encoding": "gzip, deflate, br"
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭异步会话，清理缓存"""
        if self.session:
            await self.session.close()
        self.download_cache.clear()

    async def download_content(self, url: str) -> Optional[str]:
        """下载单个远程文件，支持缓存和多编码解析，返回内容字符串或None"""
        # 优先从缓存获取
        if url in self.download_cache:
            logger.info(f"从缓存中获取链接内容：{url}")
            return self.download_cache[url]

        try:
            # 第一步：验证响应状态码
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.error(f"下载失败 {url}：HTTP状态码 {response.status}")
                    return None

            # 第二步：多编码尝试解析内容，解决乱码问题
            async with self.session.get(url) as response:
                raw_content = await response.read()
                encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
                content = None
                for encoding in encodings:
                    try:
                        content = raw_content.decode(encoding)
                        break
                    except Exception:
                        continue

                if not content:
                    logger.error(f"下载成功但无法解析编码：{url}")
                    return None

                # 缓存结果并返回
                self.download_cache[url] = content
                logger.info(f"成功下载并缓存 {url}（内容大小：{len(content)} 字符）")
                self._save_debug_file(url, content)
                return content
        except Exception as e:
            logger.error(f"下载异常 {url}：{str(e)[:100]}")
            return None

    @staticmethod
    def _save_debug_file(url: str, content: str):
        """保存下载内容到本地调试文件，便于排查格式问题"""
        try:
            file_suffix = url.split('/')[-1].replace('/', '_').replace('?', '_').replace('&', '_')
            debug_filename = f"debug_{file_suffix}.txt"
            debug_path = os.path.join(config.SCRIPT_DIR, debug_filename)  # 调试文件也放在脚本目录

            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.debug(f"调试文件已保存：{debug_path}")
        except Exception as e:
            logger.warning(f"保存调试文件失败：{str(e)[:50]}")

    async def batch_download(self, urls: List[str]) -> List[str]:
        """批量下载多个远程文件，带并发控制，返回有效内容列表"""
        if not urls:
            logger.warning("远程URL列表为空，无需下载")
            return []

        semaphore = asyncio.Semaphore(config.CONCURRENT_LIMIT)
        valid_contents = []

        async def worker(single_url):
            async with semaphore:
                content = await self.download_content(single_url)
                if content:
                    valid_contents.append(content)

        # 执行所有下载任务
        tasks = [worker(url) for url in urls]
        await asyncio.gather(*tasks)

        logger.info(f"批量下载完成：共 {len(urls)} 个链接，成功下载 {len(valid_contents)} 个")
        return valid_contents

# ===================== IPTV处理核心类 =====================
class IPTVProcessor:
    """IPTV文件解析、合并去重、M3U生成核心类"""
    @staticmethod
    def _judge_file_type(url: str, content: str) -> str:
        """预判文件类型：m3u_standard / m3u_custom / txt"""
        if url.endswith(('.m3u', '.m3u8')):
            lines = content.splitlines()
            # 判断标准M3U（包含#EXTINF:）
            has_standard_extinf = any(line.strip().startswith('#EXTINF:') for line in lines)
            if has_standard_extinf:
                return "m3u_standard"

            # 判断自定义M3U（名称, URL 格式）
            for line in lines:
                line = line.strip()
                if ',' in line:
                    name_part, url_part = line.split(',', 1)
                    if url_part.strip().startswith(('http', 'https', 'rtmp', 'udp')):
                        return "m3u_custom"

            return "m3u_standard"

        if url.endswith('.txt'):
            return "txt"

        # 无明确后缀，按内容兜底判断
        lines = content.splitlines()
        for line in lines:
            line = line.strip()
            if line.startswith('#EXTINF:'):
                return "m3u_standard"
            if ',' in line:
                name_part, url_part = line.split(',', 1)
                if url_part.strip().startswith(('http', 'https')):
                    return "m3u_custom"

        return "txt"

    @staticmethod
    def parse_txt_content(content: str) -> List[Tuple[str, str]]:
        """解析纯文本URL列表，提取有效直播源"""
        live_sources = []
        try:
            lines = content.splitlines()
            for line in lines:
                line = line.strip()
                if (line.startswith(('http', 'https')) and
                    len(line) >= 10 and
                    not any(char in line for char in [' ', '\t', '\r'])):
                    live_sources.append(("未知频道", line))

            logger.info(f"解析纯文本URL列表完成，提取到 {len(live_sources)} 个直播源")
            return live_sources
        except Exception as e:
            logger.error(f"解析纯文本URL失败：{str(e)[:100]}")
            return []

    @staticmethod
    def parse_m3u_standard_content(content: str) -> List[Tuple[str, str]]:
        """解析标准M3U文件，提取有效直播源"""
        live_sources = []
        try:
            lines = content.splitlines()
            current_name = "未知频道"
            has_extinf_flag = False

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if line.startswith('#EXTINF:'):
                    comma_indexes = [i for i, char in enumerate(line) if char == ',']
                    if comma_indexes:
                        name_part = line[comma_indexes[-1]+1:].strip()
                        current_name = name_part if name_part else "未知频道"
                    has_extinf_flag = True

                elif line.startswith(('http', 'https', 'rtmp', 'udp')) and len(line) >= 8:
                    if has_extinf_flag:
                        live_sources.append((current_name, line))
                        has_extinf_flag = False
                        current_name = "未知频道"
                    else:
                        live_sources.append(("未知频道", line))

            logger.info(f"解析标准M3U文件完成，提取到 {len(live_sources)} 个直播源")
            return live_sources
        except Exception as e:
            logger.error(f"解析标准M3U失败：{str(e)[:100]}")
            return []

    @staticmethod
    def parse_m3u_custom_content(content: str) -> List[Tuple[str, str]]:
        """解析自定义M3U文件（名称, URL格式），提取有效直播源"""
        live_sources = []
        try:
            lines = content.splitlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#') or line.endswith(',#genre#'):
                    continue

                if ',' not in line:
                    continue
                name_part, url_part = line.split(',', 1)
                name_part = name_part.strip()
                url_part = url_part.strip()

                if url_part.startswith(('http', 'https', 'rtmp', 'udp')) and len(url_part) >= 10:
                    final_name = name_part if name_part else "未知频道"
                    live_sources.append((final_name, url_part))

            logger.info(f"解析自定义M3U文件完成，提取到 {len(live_sources)} 个直播源")
            return live_sources
        except Exception as e:
            logger.error(f"解析自定义M3U失败：{str(e)[:100]}")
            return []

    @staticmethod
    def parse_content_by_url(url: str, content: str) -> List[Tuple[str, str]]:
        """根据URL自动选择解析策略，返回有效直播源列表"""
        file_type = IPTVProcessor._judge_file_type(url, content)
        if file_type == "m3u_standard":
            return IPTVProcessor.parse_m3u_standard_content(content)
        elif file_type == "m3u_custom":
            return IPTVProcessor.parse_m3u_custom_content(content)
        else:
            return IPTVProcessor.parse_txt_content(content)

    @staticmethod
    def merge_and_deduplicate(sources_list: List[List[Tuple[str, str]]]) -> List[Tuple[str, str]]:
        """合并多个解析结果，按URL去重，保留首次出现的频道名称"""
        if not sources_list:
            logger.warning("待合并的直播源列表为空")
            return []

        url_set: Set[str] = set()
        merged_sources: List[Tuple[str, str]] = []

        for sources in sources_list:
            for name, url in sources:
                if url not in url_set:
                    url_set.add(url)
                    merged_sources.append((name, url))

        total_original = sum(len(s) for s in sources_list)
        total_merged = len(merged_sources)
        logger.info(f"合并去重完成：原始 {total_original} 个源，去重后 {total_merged} 个有效源")
        return merged_sources

    @staticmethod
    def generate_sorted_m3u(live_sources: List[Tuple[str, str]], output_filename: str = "live_ipv4_source_sorted.m3u") -> None:
        """生成标准M3U文件，存入output文件夹（与主脚本同目录），可直接导入IPTV播放器"""
        if not live_sources:
            logger.error("无有效直播源，无法生成M3U文件")
            return

        try:
            # M3U文件路径：output文件夹（与主脚本同目录）
            output_path = os.path.join(config.OUTPUT_DIR, output_filename)
            with open(output_path, 'w', encoding='utf-8') as f:
                # 写入标准M3U头，添加EPG链接提升播放器兼容性
                f.write('#EXTM3U x-tvg-url="https://epg.112114.xyz/pp.xml"\n\n')

                for name, url in live_sources:
                    # 提取URL线路信息，优化频道名称显示
                    final_name = name
                    final_url = url
                    if '$' in url:
                        url_parts = url.split('$', 1)
                        if len(url_parts) == 2:
                            final_url = url_parts[0].strip()
                            line_info = url_parts[1].strip()
                            final_name = f"{name}（{line_info}）"

                    # 格式化写入频道信息
                    f.write(f'#EXTINF:-1 group-title="默认分组",{final_name}\n')
                    f.write(f'{final_url}\n\n')

            logger.info(f"已生成标准M3U文件：{output_path}（包含 {len(live_sources)} 个有效直播源）")
        except Exception as e:
            logger.error(f"生成M3U文件失败：{str(e)[:100]}")

# ===================== 速度测试工具类 =====================
class SpeedTester:
    """异步批量测速，按延迟排序，筛选可用直播源"""
    def __init__(self):
        self.session = None

    async def __aenter__(self):
        """创建异步会话，配置请求头"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=config.TIMEOUT),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br"
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭异步会话"""
        if self.session:
            await self.session.close()

    async def measure_latency(self, url: str) -> SpeedTestResult:
        """测量单个URL延迟，使用配置中的重试次数"""
        result = SpeedTestResult(url=url, test_time=time.time())
        retry_times = config.RETRY_TIMES

        for attempt in range(retry_times):
            try:
                start_time = time.time()
                async with self.session.get(url, allow_redirects=True, ssl=False) as response:
                    if response.status == 200:
                        latency = (time.time() - start_time) * 1000
                        result.latency = round(latency, 2)
                        result.resolution = "unknown"
                        result.success = True
                        logger.debug(f"测速成功 {url[:50]}... 延迟：{result.latency}ms")
                        break
                    else:
                        result.error = f"HTTP状态码：{response.status}"
            except Exception as e:
                result.error = str(e)[:100]
                logger.debug(f"测速失败 {url[:50]}... 尝试 {attempt+1}/{retry_times}：{result.error}")
                await asyncio.sleep(0.5 * (attempt + 1))

        return result

    async def batch_speed_test(self, urls: List[str]) -> List[SpeedTestResult]:
        """批量测速，分批处理避免内存溢出，返回排序后的结果"""
        if not urls:
            logger.warning("待测速URL列表为空")
            return []

        results = []
        semaphore = asyncio.Semaphore(config.CONCURRENT_LIMIT)
        batch_size = 100  # 分批大小，可根据机器性能调整

        async def worker(url):
            async with semaphore:
                result = await self.measure_latency(url)
                results.append(result)

        # 分批执行测速任务
        for i in range(0, len(urls), batch_size):
            batch_urls = urls[i:i+batch_size]
            batch_tasks = [worker(url) for url in batch_urls]
            await asyncio.gather(*batch_tasks)
            logger.info(f"测速进度：已完成 {min(i+batch_size, len(urls))}/{len(urls)} 个URL")

        # 按延迟升序排序，失败项排最后
        return sorted(results, key=lambda x: x.latency if x.latency is not None else float('inf'))

# ===================== 主程序入口 =====================
async def main():
    """主流程：下载 -> 解析 -> 合并 -> 测速 -> 生成文件"""
    # 1. 验证配置中的远程URL列表
    if not config.SOURCE_URLS:
        logger.error("SOURCE_URLS列表为空，请配置有效远程IPTV链接")
        return

    # 2. 批量下载远程文件
    logger.info(f"开始处理 {len(config.SOURCE_URLS)} 个远程链接...")
    async with RemoteM3UDownloader() as downloader:
        valid_contents = await downloader.batch_download(config.SOURCE_URLS)

    if not valid_contents:
        logger.error("未成功下载任何远程文件，程序退出")
        return

    # 3. 解析所有下载内容
    logger.info("开始解析所有远程文件内容...")
    iptv_processor = IPTVProcessor()
    all_parsed_sources = []
    for url, content in zip(config.SOURCE_URLS[:len(valid_contents)], valid_contents):
        parsed_sources = iptv_processor.parse_content_by_url(url, content)
        if parsed_sources:
            all_parsed_sources.append(parsed_sources)

    # 4. 合并去重获取有效直播源
    merged_sources = iptv_processor.merge_and_deduplicate(all_parsed_sources)
    if not merged_sources:
        logger.error("合并去重后无有效直播源，程序退出")
        return

    # 5. 批量异步测速
    logger.info(f"开始对 {len(merged_sources)} 个有效直播源进行测速...")
    async with SpeedTester() as tester:
        urls_to_test = [source[1] for source in merged_sources]
        test_results = await tester.batch_speed_test(urls_to_test)

    # 6. 筛选测速成功的源并排序
    url_to_result = {result.url: result for result in test_results}
    valid_live_sources = [(name, url) for name, url in merged_sources if url_to_result.get(url, SpeedTestResult(url)).success]

    if not valid_live_sources:
        logger.error("无测速成功的直播源，无法生成最终文件")
        return

    sorted_valid_sources = sorted(
        valid_live_sources,
        key=lambda x: url_to_result[x[1]].latency if url_to_result[x[1]].latency is not None else float('inf')
    )

    # 7. 生成M3U文件和测速报告
    iptv_processor.generate_sorted_m3u(sorted_valid_sources)

    # 生成测速报告（存入output文件夹）
    report_file = os.path.join(config.OUTPUT_DIR, f"speed_test_report_{int(time.time())}.txt")
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("IPTV直播源速度测试报告（专属优化版）\n")
            f.write(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"远程链接数量: {len(config.SOURCE_URLS)}\n")
            f.write(f"总解析源数量: {len(merged_sources)}\n")
            f.write(f"测速成功数量: {len(sorted_valid_sources)}\n\n")

            f.write("=" * 50 + "\n")
            f.write("前20个最快直播源（按延迟升序）\n")
            f.write("=" * 50 + "\n")
            for i, (name, url) in enumerate(sorted_valid_sources[:20], 1):
                result = url_to_result[url]
                f.write(f"{i:2d}. 名称：{name}\n")
                f.write(f"    延迟：{result.latency}ms\n")
                f.write(f"    URL：{url[:100]}...\n\n")

            f.write("=" * 50 + "\n")
            f.write(f"完整有效源列表（共 {len(sorted_valid_sources)} 个）\n")
            f.write("=" * 50 + "\n")
            for i, (name, url) in enumerate(sorted_valid_sources, 1):
                result = url_to_result[url]
                f.write(f"{i}. {name} - 延迟：{result.latency}ms - URL：{url[:100]}...\n")

        logger.info(f"已生成详细测试报告：{report_file}")
    except Exception as e:
        logger.error(f"生成测试报告失败：{str(e)[:100]}")

    # 8. 程序执行完成提示
    logger.info("=" * 60)
    logger.info("程序执行完成，所有结果文件已存入output文件夹（与主脚本同目录）")
    logger.info("=" * 60)

if __name__ == "__main__":
    """运行入口，兼容Windows系统asyncio事件循环"""
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            logger.warning("Windows系统事件循环关闭警告，核心功能已正常完成")
        else:
            logger.error(f"程序运行异常：{str(e)[:100]}")