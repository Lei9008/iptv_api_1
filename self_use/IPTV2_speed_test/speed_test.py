import asyncio
import aiohttp
import time
import logging
import os
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Set

# 从config.py导入Config类
from config import Config

# 实例化配置
config = Config()

# 确保输出目录存在，避免日志/报告创建失败
os.makedirs(config.OUTPUT_DIR, exist_ok=True)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 数据类
@dataclass
class SpeedTestResult:
    url: str
    latency: Optional[float] = None  # 延迟（毫秒）
    resolution: Optional[str] = None  # 分辨率
    success: bool = False  # 是否成功
    error: Optional[str] = None  # 错误信息
    test_time: float = 0  # 测试时间戳

# 远程M3U/纯文本URL列表下载工具类（深度优化）
class RemoteM3UDownloader:
    """异步下载远程M3U/纯文本URL文件，适配GitHub RAW链接，支持缓存和编码兼容"""
    def __init__(self):
        self.session = None
        # 缓存：避免重复下载同一URL
        self.download_cache = {}

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=config.TIMEOUT),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/plain, text/html, application/x-mpegurl"
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
        self.download_cache.clear()

    async def download_content(self, url: str) -> Optional[str]:
        """
        下载单个远程文件，支持缓存，兼容UTF-8/GBK/GB2312编码
        返回文件内容字符串，失败返回None
        """
        # 先查缓存，避免重复下载
        if url in self.download_cache:
            logger.info(f"从缓存中获取 {url} 的内容")
            return self.download_cache[url]

        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.error(f"下载失败 {url}：HTTP状态码 {response.status}")
                    return None

            # 重新请求获取内容（分开处理状态码和编码，提升兼容性）
            async with self.session.get(url) as response:
                # 尝试多种编码解析
                encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
                content = None
                for encoding in encodings:
                    try:
                        content = await response.text(encoding=encoding)
                        break
                    except:
                        continue

                if not content:
                    logger.error(f"下载 {url} 成功，但无法解析任何编码格式")
                    return None

                # 缓存结果
                self.download_cache[url] = content
                logger.info(f"成功下载并缓存 {url}（大小：{len(content)} 字符）")

                # 保存调试文件（可选，便于排查问题）
                self._save_debug_file(url, content)

                return content
        except Exception as e:
            logger.error(f"下载异常 {url}：{str(e)}")
            return None

    @staticmethod
    def _save_debug_file(url: str, content: str):
        """保存下载内容到本地调试文件，按链接命名避免覆盖"""
        try:
            # 提取简单文件名作为调试文件名称
            file_name = url.split('/')[-1].replace('.', '_') + "_debug.txt"
            debug_path = os.path.join(os.getcwd(), file_name)
            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.debug(f"调试文件已保存：{debug_path}")
        except:
            pass

    async def batch_download(self, urls: List[str]) -> List[str]:
        """批量下载多个远程文件，返回所有有效内容列表"""
        if not urls:
            logger.warning("远程URL列表为空")
            return []

        # 并发下载（复用全局并发限制）
        semaphore = asyncio.Semaphore(config.CONCURRENT_LIMIT)
        valid_contents = []

        async def worker(m3u_url):
            async with semaphore:
                content = await self.download_content(m3u_url)
                if content:
                    valid_contents.append(content)

        tasks = [worker(url) for url in urls]
        await asyncio.gather(*tasks)

        logger.info(f"批量下载完成：共 {len(urls)} 个链接，成功下载 {len(valid_contents)} 个")
        return valid_contents

# M3U/纯文本URL处理类（专属适配两个GitHub链接）
class IPTVProcessor:
    @staticmethod
    def _judge_file_type(url: str, content: str) -> str:
        """
        预判文件类型，支持：m3u（标准格式）、txt（纯URL列表）
        返回："m3u" 或 "txt"
        """
        # 先通过文件名后缀判断
        if url.endswith('.m3u') or url.endswith('.m3u8'):
            return "m3u"
        if url.endswith('.txt'):
            return "txt"

        # 后缀无法判断时，通过内容判断
        if any(line.strip().startswith('#EXTINF:') for line in content.splitlines()):
            return "m3u"
        return "txt"

    @staticmethod
    def parse_txt_content(content: str) -> List[Tuple[str, str]]:
        """解析.txt纯URL列表（适配第一个GitHub链接），一行一个URL"""
        live_sources = []
        try:
            lines = content.splitlines()
            for line in lines:
                line = line.strip()
                # 严格筛选有效直播源URL
                if line.startswith(('http', 'https')) and len(line) >= 10:
                    # 过滤无效链接（包含特殊字符、过短链接）
                    if not any(char in line for char in [' ', '\t', '\r', '\n']):
                        live_sources.append(("未知频道", line))
            logger.info(f"解析纯文本URL列表完成，提取到 {len(live_sources)} 个直播源")
            return live_sources
        except Exception as e:
            logger.error(f"解析纯文本URL失败：{str(e)}")
            return []

    @staticmethod
    def parse_m3u_content(content: str) -> List[Tuple[str, str]]:
        """解析标准.m3u文件（适配第二个GitHub链接），带#EXTINF:频道名称"""
        live_sources = []
        try:
            lines = []
            # 预处理：过滤空白行和无关注释行
            for line in content.splitlines():
                line = line.strip()
                if line and not (line.startswith('#') and not line.startswith('#EXTINF:')):
                    lines.append(line)

            current_name = "未知频道"
            for line in lines:
                if line.startswith('#EXTINF:'):
                    # 精准提取频道名称，兼容各种#EXTINF格式
                    name_part = line.split(',', 1)[-1].strip() if ',' in line else ""
                    current_name = name_part if name_part else "未知频道"
                elif line.startswith(('http', 'https')) and len(line) >= 10:
                    live_sources.append((current_name, line))
                    current_name = "未知频道"  # 重置名称，避免重复绑定

            logger.info(f"解析标准M3U文件完成，提取到 {len(live_sources)} 个直播源")
            return live_sources
        except Exception as e:
            logger.error(f"解析标准M3U失败：{str(e)}")
            return []

    @staticmethod
    def parse_content_by_url(url: str, content: str) -> List[Tuple[str, str]]:
        """根据URL自动选择解析策略，适配两个GitHub链接"""
        file_type = IPTVProcessor._judge_file_type(url, content)
        if file_type == "m3u":
            return IPTVProcessor.parse_m3u_content(content)
        else:
            return IPTVProcessor.parse_txt_content(content)

    @staticmethod
    def merge_and_deduplicate(sources_list: List[List[Tuple[str, str]]]) -> List[Tuple[str, str]]:
        """
        合并多个解析结果，按URL去重（保留首次出现的频道名称）
        去重逻辑优化，提升大规模数据处理效率
        """
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
        """生成排序后的M3U文件，与main.py同目录，格式规范可直接用于IPTV播放器"""
        if not live_sources:
            logger.error("无有效直播源，无法生成M3U文件")
            return

        try:
            output_path = os.path.join(os.getcwd(), output_filename)
            with open(output_path, 'w', encoding='utf-8') as f:
                # 写入标准M3U文件头
                f.write('#EXTM3U x-tvg-url="https://epg.112114.xyz/pp.xml"\n\n')
                for name, url in live_sources:
                    # 格式化写入，提升文件可读性
                    f.write(f'#EXTINF:-1 group-title="默认分组",{name}\n')
                    f.write(f'{url}\n\n')

            logger.info(f"已生成标准M3U文件：{output_path}（包含 {len(live_sources)} 个有效直播源）")
        except Exception as e:
            logger.error(f"生成M3U文件失败：{str(e)}")

# 速度测试工具类（优化请求头，提升GitHub链接测速成功率）
class SpeedTester:
    def __init__(self):
        self.session = None

    async def __aenter__(self):
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
        if self.session:
            await self.session.close()

    async def measure_latency(self, url: str, retry_times: int = 3) -> SpeedTestResult:
        """测量单个URL延迟，优化重试策略，减少GitHub链接请求被封禁"""
        result = SpeedTestResult(url=url, test_time=time.time())

        for attempt in range(retry_times):
            try:
                start_time = time.time()
                async with self.session.get(url, allow_redirects=True) as response:
                    # 只需确认响应状态码，无需下载完整内容（提升测速效率）
                    if response.status == 200:
                        latency = (time.time() - start_time) * 1000  # 转换为毫秒
                        result.latency = round(latency, 2)  # 保留2位小数，更整洁
                        result.resolution = "unknown"
                        result.success = True
                        logger.debug(f"URL: {url[:50]}... 测试成功，延迟: {result.latency}ms")
                        break
                    else:
                        result.error = f"HTTP状态码: {response.status}"
            except Exception as e:
                result.error = str(e)[:100]  # 截断过长错误信息
                logger.debug(f"URL: {url[:50]}... 尝试 {attempt+1}/{retry_times} 失败: {result.error}")
                # 优化重试间隔，避免频繁请求
                await asyncio.sleep(0.5 * (attempt + 1))

        return result

    async def batch_speed_test(self, urls: List[str]) -> List[SpeedTestResult]:
        """批量测速，优化并发控制，提升大规模URL处理效率"""
        if not urls:
            logger.warning("待测速URL列表为空")
            return []

        results = []
        semaphore = asyncio.Semaphore(config.CONCURRENT_LIMIT)

        async def worker(url):
            nonlocal results
            async with semaphore:
                result = await self.measure_latency(url, config.RETRY_TIMES)
                results.append(result)

        # 分批创建任务，避免内存溢出（适配大规模直播源）
        batch_size = 100
        for i in range(0, len(urls), batch_size):
            batch_urls = urls[i:i+batch_size]
            batch_tasks = [worker(url) for url in batch_urls]
            await asyncio.gather(*batch_tasks)
            logger.info(f"已完成 {min(i+batch_size, len(urls))}/{len(urls)} 个URL测速")

        # 按延迟升序排序，失败项排最后
        return sorted(results, key=lambda x: x.latency if x.latency is not None else float('inf'))

# 主程序（专属适配两个GitHub链接，流程优化）
async def main():
    # 1. 验证配置中的远程URL列表
    if not config.SOURCE_URLS:
        logger.error("config.py中的SOURCE_URLS列表为空，请配置目标GitHub链接")
        return

    # 2. 批量下载远程文件
    logger.info(f"开始处理 {len(config.SOURCE_URLS)} 个GitHub远程链接...")
    async with RemoteM3UDownloader() as downloader:
        valid_contents = await downloader.batch_download(config.SOURCE_URLS)

    if not valid_contents:
        logger.error("未成功下载任何远程文件，程序退出")
        return

    # 3. 解析每个下载的内容（自动适配.txt/.m3u格式）
    logger.info("开始解析所有远程文件内容...")
    iptv_processor = IPTVProcessor()
    all_sources = []
    for url, content in zip(config.SOURCE_URLS, valid_contents):
        parsed_sources = iptv_processor.parse_content_by_url(url, content)
        if parsed_sources:
            all_sources.append(parsed_sources)

    # 4. 合并去重
    merged_sources = iptv_processor.merge_and_deduplicate(all_sources)
    if not merged_sources:
        logger.error("合并去重后无有效直播源，程序退出")
        return

    # 5. 批量异步测速
    logger.info(f"开始对 {len(merged_sources)} 个有效直播源进行测速...")
    async with SpeedTester() as tester:
        urls = [source[1] for source in merged_sources]
        test_results = await tester.batch_speed_test(urls)

    # 6. 筛选有效源并排序
    url_to_result = {result.url: result for result in test_results}
    valid_live_sources = [(name, url) for name, url in merged_sources if url_to_result[url].success]

    if not valid_live_sources:
        logger.error("无测速成功的直播源，无法生成最终文件")
        return

    # 按延迟升序排序有效源
    sorted_valid_sources = sorted(
        valid_live_sources,
        key=lambda x: url_to_result[x[1]].latency if url_to_result[x[1]].latency is not None else float('inf')
    )

    # 7. 生成最终M3U文件和测试报告
    iptv_processor.generate_sorted_m3u(sorted_valid_sources)

    # 生成详细测试报告
    report_file = f"{config.OUTPUT_DIR}/speed_test_report_{int(time.time())}.txt"
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("IPTV直播源速度测试报告（GitHub专属版）\n")
            f.write(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"远程链接数量: {len(config.SOURCE_URLS)}\n")
            f.write(f"总解析源数量: {len(merged_sources)}\n")
            f.write(f"测速成功数量: {len(sorted_valid_sources)}\n\n")

            f.write("前20个最快的直播源（按延迟升序）:\n")
            for i, (name, url) in enumerate(sorted_valid_sources[:20], 1):
                result = url_to_result[url]
                f.write(f"{i}. {name} - 延迟: {result.latency}ms - 状态: 成功\n")

            f.write(f"\n完整有效源列表（共 {len(sorted_valid_sources)} 个）:\n")
            for i, (name, url) in enumerate(sorted_valid_sources, 1):
                result = url_to_result[url]
                f.write(f"{i}. {name} - 延迟: {result.latency}ms - URL: {url[:100]}...\n")

        logger.info(f"已生成详细测试报告: {report_file}")
    except Exception as e:
        logger.error(f"生成测试报告失败: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())