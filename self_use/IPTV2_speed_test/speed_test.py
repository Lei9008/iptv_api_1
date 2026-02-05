import asyncio
import aiohttp
import time
import logging
import os
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Set

# 从config.py导入Config类（适配绝对路径配置）
from config import Config

# 实例化配置
config = Config()

# 提前定义日志对象（后续初始化后会覆盖配置，避免未定义报错）
logger = logging.getLogger(__name__)

# 确保必要文件夹存在
def init_folders():
    """初始化项目所需文件夹（output，使用config中的绝对路径）"""
    # 从config中获取文件夹绝对路径，保证可移植性
    folder = config.OUTPUT_DIR
    if not os.path.exists(folder):
        os.makedirs(folder)
        logging.info(f"创建文件夹成功：{folder}")

# 配置日志系统
def init_logging():
    """初始化日志配置，同时输出到控制台和日志文件（绝对路径）"""
    init_folders()
    # 从config中获取日志文件绝对路径
    log_file = config.LOG_FILE
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',  # 补充日期时间格式，更易读
        handlers=[
            logging.FileHandler(log_file, "a", encoding="utf-8"),  # 追加模式，保留历史日志
            logging.StreamHandler()
        ]
    )
    # 全局更新logger对象，应用最新配置
    global logger
    logger = logging.getLogger(__name__)

# 数据类：存储单个URL测速结果
@dataclass
class SpeedTestResult:
    url: str
    latency: Optional[float] = None  # 延迟（毫秒），保留2位小数
    resolution: Optional[str] = None  # 分辨率（简化为unknown）
    success: bool = False  # 是否测试成功
    error: Optional[str] = None  # 错误信息（截断过长内容）
    test_time: float = 0  # 测试时间戳

# 远程文件下载工具类：适配GitHub RAW链接，支持缓存、多编码兼容
class RemoteM3UDownloader:
    """异步下载远程M3U/纯文本URL文件，适配GitHub RAW链接，优化请求成功率"""
    def __init__(self):
        self.session = None
        self.download_cache = {}  # 下载缓存，避免重复请求同一链接

    async def __aenter__(self):
        # 优化请求头，模拟浏览器，提升GitHub链接访问成功率
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
        # 关闭会话，清理缓存
        if self.session:
            await self.session.close()
        self.download_cache.clear()

    async def download_content(self, url: str) -> Optional[str]:
        """
        下载单个远程文件，支持缓存和多编码解析
        返回：文件内容字符串 | None（下载失败）
        """
        # 优先从缓存获取，避免重复请求
        if url in self.download_cache:
            logger.info(f"从缓存中获取链接内容：{url}")
            return self.download_cache[url]

        try:
            # 第一步：验证响应状态码，不下载完整内容
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.error(f"下载失败 {url}：HTTP状态码 {response.status}")
                    return None

            # 第二步：多编码尝试解析内容，解决乱码问题
            async with self.session.get(url) as response:
                encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
                content = None
                for encoding in encodings:
                    try:
                        content = await response.text(encoding=encoding)
                        break
                    except Exception:
                        continue

                if not content:
                    logger.error(f"下载成功但无法解析编码：{url}")
                    return None

                # 缓存结果，更新缓存
                self.download_cache[url] = content
                logger.info(f"成功下载并缓存 {url}（内容大小：{len(content)} 字符）")

                # 保存调试文件，便于排查格式问题（当前工作目录，不使用绝对路径，方便查看）
                self._save_debug_file(url, content)
                return content
        except Exception as e:
            logger.error(f"下载异常 {url}：{str(e)[:100]}")
            return None

    @staticmethod
    def _save_debug_file(url: str, content: str):
        """保存下载内容到本地调试文件，按链接后缀命名，避免覆盖"""
        try:
            # 提取链接末尾文件名作为调试文件名，处理特殊字符
            file_suffix = url.split('/')[-1].replace('/', '_').replace('?', '_').replace('&', '_')
            debug_filename = f"debug_{file_suffix}.txt"
            debug_path = os.path.join(os.getcwd(), debug_filename)

            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.debug(f"调试文件已保存：{debug_path}")
        except Exception as e:
            logger.warning(f"保存调试文件失败：{str(e)[:50]}")

    async def batch_download(self, urls: List[str]) -> List[str]:
        """批量下载多个远程文件，返回所有有效内容列表，带并发控制"""
        if not urls:
            logger.warning("远程URL列表为空，无需下载")
            return []

        # 使用config中的并发限制配置
        semaphore = asyncio.Semaphore(config.CONCURRENT_LIMIT)
        valid_contents = []

        async def worker(single_url):
            async with semaphore:
                content = await self.download_content(single_url)
                if content:
                    valid_contents.append(content)

        # 创建并执行所有下载任务
        tasks = [worker(url) for url in urls]
        await asyncio.gather(*tasks)

        logger.info(f"批量下载完成：共 {len(urls)} 个链接，成功下载 {len(valid_contents)} 个")
        return valid_contents

# IPTV处理核心类：兼容3种格式，支持合并去重、标准M3U生成
class IPTVProcessor:
    @staticmethod
    def _judge_file_type(url: str, content: str) -> str:
        """
        预判文件类型，支持3种格式：
        - m3u_standard: 标准M3U（#EXTINF: + URL）
        - m3u_custom: 自定义M3U（名称, URL 逗号分隔）
        - txt: 纯URL列表（一行一个URL）
        """
        # 第一步：按文件后缀初步判断
        if url.endswith(('.m3u', '.m3u8')):
            # 第二步：按内容细分格式
            lines = content.splitlines()
            # 判断是否为标准M3U（包含#EXTINF:）
            has_standard_extinf = any(line.strip().startswith('#EXTINF:') for line in lines)
            if has_standard_extinf:
                return "m3u_standard"

            # 判断是否为自定义M3U（名称, URL 格式）
            for line in lines:
                line = line.strip()
                if ',' in line:
                    name_part, url_part = line.split(',', 1)
                    if url_part.strip().startswith(('http', 'https', 'rtmp', 'udp')):
                        return "m3u_custom"

            # 兜底：视为标准M3U
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
        """解析.txt纯URL列表（一行一个URL），提取有效直播源"""
        live_sources = []
        try:
            lines = content.splitlines()
            for line in lines:
                line = line.strip()
                # 筛选有效URL：以http/https开头，无空白字符，长度≥10
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
        """解析标准M3U文件（#EXTINF: + URL），增强兼容性"""
        live_sources = []
        try:
            lines = content.splitlines()
            current_name = "未知频道"
            has_extinf_flag = False  # 标记是否已读取#EXTINF:行

            for line in lines:
                line = line.strip()
                if not line:
                    continue  # 跳过空白行

                # 处理#EXTINF:行，提取频道名称
                if line.startswith('#EXTINF:'):
                    comma_indexes = [i for i, char in enumerate(line) if char == ',']
                    if comma_indexes:
                        # 取最后一个逗号后的内容，兼容多逗号格式
                        name_part = line[comma_indexes[-1]+1:].strip()
                    else:
                        name_part = ""
                    current_name = name_part if name_part else "未知频道"
                    has_extinf_flag = True

                # 处理URL行，绑定最近的频道名称
                elif line.startswith(('http', 'https', 'rtmp', 'udp')) and len(line) >= 8:
                    if has_extinf_flag:
                        live_sources.append((current_name, line))
                        # 重置标记，避免重复绑定
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
        """解析自定义M3U文件（名称, URL 逗号分隔），适配目标GitHub链接"""
        live_sources = []
        try:
            lines = content.splitlines()
            for line in lines:
                line = line.strip()
                # 跳过空行、注释行、分类行（如"广东频道,#genre#"）
                if not line or line.startswith('#') or line.endswith(',#genre#'):
                    continue

                # 按第一个逗号分割，避免URL中包含逗号导致解析失败
                if ',' not in line:
                    continue
                name_part, url_part = line.split(',', 1)
                name_part = name_part.strip()
                url_part = url_part.strip()

                # 筛选有效URL，支持多种直播协议
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
        """根据URL自动选择解析策略，适配对应文件格式"""
        file_type = IPTVProcessor._judge_file_type(url, content)
        if file_type == "m3u_standard":
            return IPTVProcessor.parse_m3u_standard_content(content)
        elif file_type == "m3u_custom":
            return IPTVProcessor.parse_m3u_custom_content(content)
        else:
            return IPTVProcessor.parse_txt_content(content)

    @staticmethod
    def merge_and_deduplicate(sources_list: List[List[Tuple[str, str]]]) -> List[Tuple[str, str]]:
        """合并多个解析结果，按URL去重（保留首次出现的频道名称），提升大规模数据效率"""
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
        """生成标准M3U文件，可直接导入IPTV播放器，优化频道名称和URL格式"""
        if not live_sources:
            logger.error("无有效直播源，无法生成M3U文件")
            return

        try:
            # 生成M3U文件到当前工作目录（方便用户查找，也可改为绝对路径）
            output_path = os.path.join(os.getcwd(), output_filename)
            with open(output_path, 'w', encoding='utf-8') as f:
                # 写入标准M3U头，添加EPG链接，提升播放器体验
                f.write('#EXTM3U x-tvg-url="https://epg.112114.xyz/pp.xml"\n\n')

                for name, url in live_sources:
                    # 优化：提取URL中的线路信息（$后内容），添加到频道名称
                    final_name = name
                    final_url = url
                    if '$' in url:
                        url_parts = url.split('$', 1)
                        if len(url_parts) == 2:
                            final_url = url_parts[0].strip()  # 核心播放URL，去除后缀
                            line_info = url_parts[1].strip()  # 线路信息
                            final_name = f"{name}（{line_info}）"  # 拼接频道名称

                    # 格式化写入，添加分组，提升可读性
                    f.write(f'#EXTINF:-1 group-title="默认分组",{final_name}\n')
                    f.write(f'{final_url}\n\n')

            logger.info(f"已生成标准M3U文件：{output_path}（包含 {len(live_sources)} 个有效直播源）")
        except Exception as e:
            logger.error(f"生成M3U文件失败：{str(e)[:100]}")

# 速度测试工具类：优化测速效率，适配大规模直播源
class SpeedTester:
    def __init__(self):
        self.session = None

    async def __aenter__(self):
        # 优化请求头，提升测速成功率，避免被目标服务器封禁
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
        """测量单个URL延迟，优化重试策略，仅验证响应状态码，提升效率"""
        # 使用config中的重试次数配置
        retry_times = config.RETRY_TIMES
        result = SpeedTestResult(url=url, test_time=time.time())

        for attempt in range(retry_times):
            try:
                start_time = time.time()
                # 允许重定向，适配跳转类直播源，不下载完整内容（关闭SSL验证，提升兼容性）
                async with self.session.get(url, allow_redirects=True, ssl=False) as response:
                    if response.status == 200:
                        # 计算延迟，保留2位小数
                        latency = (time.time() - start_time) * 1000
                        result.latency = round(latency, 2)
                        result.resolution = "unknown"
                        result.success = True
                        logger.debug(f"测速成功 {url[:50]}... 延迟：{result.latency}ms")
                        break
                    else:
                        result.error = f"HTTP状态码：{response.status}"
            except Exception as e:
                result.error = str(e)[:100]  # 截断过长错误信息
                logger.debug(f"测速失败 {url[:50]}... 尝试 {attempt+1}/{retry_times}：{result.error}")
                # 递增重试间隔，避免频繁请求被封禁
                await asyncio.sleep(0.5 * (attempt + 1))

        return result

    async def batch_speed_test(self, urls: List[str]) -> List[SpeedTestResult]:
        """批量测速，分批处理，避免内存溢出，适配大规模直播源"""
        if not urls:
            logger.warning("待测速URL列表为空")
            return []

        results = []
        # 使用config中的并发限制配置
        semaphore = asyncio.Semaphore(config.CONCURRENT_LIMIT)
        batch_size = 100  # 分批大小，可根据机器性能调整

        async def worker(url):
            async with semaphore:
                result = await self.measure_latency(url)
                results.append(result)

        # 分批创建并执行任务，提升大规模数据处理稳定性
        for i in range(0, len(urls), batch_size):
            batch_urls = urls[i:i+batch_size]
            batch_tasks = [worker(url) for url in batch_urls]
            await asyncio.gather(*batch_tasks)
            logger.info(f"测速进度：已完成 {min(i+batch_size, len(urls))}/{len(urls)} 个URL")

        # 按延迟升序排序，失败项排最后
        return sorted(results, key=lambda x: x.latency if x.latency is not None else float('inf'))

# 主程序：串联所有流程，实现从下载到生成的闭环
async def main():
    # 1. 验证配置中的远程URL列表
    if not config.SOURCE_URLS:
        logger.error("config.py中的SOURCE_URLS列表为空，请先配置有效GitHub链接")
        return

    # 2. 批量下载远程文件
    logger.info(f"开始处理 {len(config.SOURCE_URLS)} 个GitHub远程链接...")
    async with RemoteM3UDownloader() as downloader:
        valid_contents = await downloader.batch_download(config.SOURCE_URLS)

    if not valid_contents:
        logger.error("未成功下载任何远程文件，程序退出")
        return

    # 3. 解析所有下载内容，自动适配格式
    logger.info("开始解析所有远程文件内容...")
    iptv_processor = IPTVProcessor()
    all_parsed_sources = []
    for url, content in zip(config.SOURCE_URLS, valid_contents):
        parsed_sources = iptv_processor.parse_content_by_url(url, content)
        if parsed_sources:
            all_parsed_sources.append(parsed_sources)

    # 4. 合并去重，获取有效直播源列表
    merged_sources = iptv_processor.merge_and_deduplicate(all_parsed_sources)
    if not merged_sources:
        logger.error("合并去重后无有效直播源，程序退出")
        return

    # 5. 批量异步测速，获取排序结果
    logger.info(f"开始对 {len(merged_sources)} 个有效直播源进行测速...")
    async with SpeedTester() as tester:
        urls_to_test = [source[1] for source in merged_sources]
        test_results = await tester.batch_speed_test(urls_to_test)

    # 6. 筛选测速成功的源，按延迟排序
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

    # 7. 生成标准M3U文件和详细测试报告（使用config中的绝对路径保存报告）
    iptv_processor.generate_sorted_m3u(sorted_valid_sources)

    # 生成测试报告（保存到output文件夹，绝对路径）
    report_file = os.path.join(config.OUTPUT_DIR, f"speed_test_report_{int(time.time())}.txt")
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("IPTV直播源速度测试报告（GitHub专属优化版）\n")
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
    logger.info("程序执行完成，所有结果文件已生成，可直接导入IPTV播放器使用")
    logger.info("=" * 60)

if __name__ == "__main__":
    # 关键：先执行日志和文件夹初始化（适配绝对路径），再运行主程序
    init_logging()
    asyncio.run(main())