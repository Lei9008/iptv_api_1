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

# 远程M3U下载工具类（新增）
class RemoteM3UDownloader:
    """异步下载远程M3U文件，支持多链接批量下载"""
    def __init__(self):
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=config.TIMEOUT),
            headers={"User-Agent": "Mozilla/5.0"}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def download_m3u_content(self, url: str) -> Optional[str]:
        """下载单个远程M3U文件，返回文件内容（字符串）"""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    content = await response.text(encoding='utf-8')
                    logger.info(f"成功下载远程M3U文件: {url}")
                    return content
                else:
                    logger.error(f"下载远程M3U失败 {url}：HTTP状态码 {response.status}")
                    return None
        except Exception as e:
            logger.error(f"下载远程M3U异常 {url}：{str(e)}")
            return None
    
    async def batch_download_m3u(self, urls: List[str]) -> List[str]:
        """批量下载多个远程M3U文件，返回所有有效文件内容列表"""
        if not urls:
            logger.warning("远程M3U URL列表为空")
            return []
        
        # 并发下载（复用全局并发限制）
        semaphore = asyncio.Semaphore(config.CONCURRENT_LIMIT)
        downloaded_contents = []
        
        async def worker(m3u_url):
            async with semaphore:
                content = await self.download_m3u_content(m3u_url)
                if content:
                    downloaded_contents.append(content)
        
        tasks = [worker(url) for url in config.SOURCE_URLS]
        await asyncio.gather(*tasks)
        
        return downloaded_contents

# 速度测试工具类（保留原有逻辑，无核心修改）
class SpeedTester:
    def __init__(self):
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=config.TIMEOUT))
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def measure_latency(self, url: str, retry_times: int = 3) -> SpeedTestResult:
        """测量单个URL的延迟和分辨率"""
        result = SpeedTestResult(url=url, test_time=time.time())
        
        for attempt in range(retry_times):
            try:
                start_time = time.time()
                async with self.session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as response:
                    if response.status == 200:
                        # 简单测量响应时间作为延迟（转换为毫秒）
                        latency = (time.time() - start_time) * 1000
                        
                        # 简化分辨率提取（仅判断响应类型）
                        resolution = None
                        content_type = response.headers.get("Content-Type", "")
                        if "video" in content_type or "application/vnd.apple.mpegurl" in content_type:
                            resolution = "unknown"
                        
                        result.latency = latency
                        result.resolution = resolution
                        result.success = True
                        logger.info(f"URL: {url} 测试成功，延迟: {latency:.2f}ms")
                        break
                    else:
                        result.error = f"HTTP状态码: {response.status}"
            except Exception as e:
                result.error = str(e)
                logger.warning(f"URL: {url} 尝试 {attempt+1}/{retry_times} 失败: {e}")
                await asyncio.sleep(1)  # 重试前等待1秒，避免频繁请求
        
        return result
    
    async def batch_speed_test(self, urls: List[str]) -> List[SpeedTestResult]:
        """批量测速（带并发控制）"""
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

        tasks = [worker(url) for url in urls]
        await asyncio.gather(*tasks)
        
        # 按延迟升序排序（失败项排最后）
        return sorted(results, key=lambda x: x.latency if x.latency is not None else float('inf'))

# M3U文件处理类（优化：支持解析字符串内容，新增去重逻辑）
class M3UProcessor:
    @staticmethod
    def parse_m3u_content(m3u_content: str) -> List[Tuple[str, str]]:
        """解析M3U字符串内容，返回[(名称, URL), ...]（替代原有本地文件解析）"""
        try:
            lines = m3u_content.splitlines()  # 按行分割字符串，模拟本地文件读取
            live_sources = []
            current_name = None
            
            for line in lines:
                line = line.strip()
                if line.startswith('#EXTINF:'):
                    # 提取频道名称
                    name_start = line.find(',') + 1
                    current_name = line[name_start:] if name_start > 0 else "未知频道"
                elif line.startswith('http') and current_name:
                    # 过滤无效短链接（可选优化）
                    if len(line) > 10:
                        live_sources.append((current_name, line))
                        current_name = None
            
            return live_sources
        except Exception as e:
            logger.error(f"解析M3U内容失败: {e}")
            return []
    
    @staticmethod
    def merge_and_deduplicate(sources_list: List[List[Tuple[str, str]]]) -> List[Tuple[str, str]]:
        """合并多个M3U解析结果，去重（按URL去重，保留首次出现的名称）"""
        if not sources_list:
            return []
        
        url_set: Set[str] = set()
        merged_sources: List[Tuple[str, str]] = []
        
        for sources in sources_list:
            for name, url in sources:
                if url not in url_set:
                    url_set.add(url)
                    merged_sources.append((name, url))
        
        logger.info(f"合并完成：共处理 {sum(len(s) for s in sources_list)} 个原始源，去重后剩余 {len(merged_sources)} 个有效源")
        return merged_sources
    
    @staticmethod
    def generate_m3u(live_sources: List[Tuple[str, str]], output_path: str) -> None:
        """生成M3U文件（与main.py同目录，无修改）"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for name, url in live_sources:
                    f.write(f'#EXTINF:-1,{name}\n')
                    f.write(f'{url}\n')
            
            logger.info(f"已生成排序后的M3U文件: {output_path}")
        except Exception as e:
            logger.error(f"生成M3U文件失败: {e}")

# 主程序（核心流程改造：下载 -> 合并解析 -> 测速 -> 生成结果）
async def main():
    # 1. 验证远程URL列表是否为空
    if not config.SOURCE_URLS:
        logger.error("config.py中的SOURCE_URLS列表为空，请先配置远程M3U链接")
        return
    
    # 2. 异步批量下载所有远程M3U文件
    logger.info(f"开始下载 {len(config.SOURCE_URLS)} 个远程M3U文件...")
    async with RemoteM3UDownloader() as downloader:
        m3u_contents = await downloader.batch_download_m3u(config.SOURCE_URLS)
    
    if not m3u_contents:
        logger.error("未成功下载任何远程M3U文件，程序退出")
        return
    
    # 3. 解析所有下载的M3U内容，合并并去重
    logger.info("开始解析并合并M3U内容...")
    m3u_processor = M3UProcessor()
    all_sources = []
    for content in m3u_contents:
        parsed_sources = m3u_processor.parse_m3u_content(content)
        if parsed_sources:
            all_sources.append(parsed_sources)
    
    merged_live_sources = m3u_processor.merge_and_deduplicate(all_sources)
    if not merged_live_sources:
        logger.error("合并去重后无有效直播源，程序退出")
        return
    
    # 4. 异步批量测速
    logger.info(f"开始对 {len(merged_live_sources)} 个直播源进行测速...")
    async with SpeedTester() as tester:
        urls = [source[1] for source in merged_live_sources]
        test_results = await tester.batch_speed_test(urls)
    
    # 5. 构建URL->测试结果映射，筛选有效源并排序
    url_to_result = {result.url: result for result in test_results}
    # 筛选仅成功的源
    valid_live_sources = [(name, url) for name, url in merged_live_sources if url_to_result[url].success]
    if not valid_live_sources:
        logger.error("无测速成功的有效直播源，无法生成输出文件")
        return
    
    # 按延迟升序排序有效源
    sorted_valid_sources = sorted(
        valid_live_sources,
        key=lambda x: url_to_result[x[1]].latency if url_to_result[x[1]].latency is not None else float('inf')
    )
    
    # 6. 生成输出M3U文件（与main.py同目录）
    output_file = "live_ipv4_source_sorted.m3u"
    # 可选：带时间戳避免覆盖
    # output_file = f"live_ipv4_source_sorted_{int(time.time())}.m3u"
    m3u_processor.generate_m3u(sorted_valid_sources, output_file)
    
    # 7. 生成详细测试报告
    report_file = f"{config.OUTPUT_DIR}/speed_test_report_{int(time.time())}.txt"
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("IPTV直播源速度测试报告（远程源版）\n")
            f.write(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"远程源数量: {len(config.SOURCE_URLS)}\n")
            f.write(f"总解析源数量: {len(merged_live_sources)}\n")
            f.write(f"测速成功数量: {len(sorted_valid_sources)}\n\n")
            
            f.write("排序后的有效直播源列表（按延迟升序）:\n")
            for i, (name, url) in enumerate(sorted_valid_sources, 1):
                result = url_to_result[url]
                latency_str = f"{result.latency:.2f}" if isinstance(result.latency, float) else "N/A"
                f.write(f"{i}. {name} - 延迟: {latency_str}ms - 状态: 成功\n")
        
        logger.info(f"已生成详细测试报告: {report_file}")
    except Exception as e:
        logger.error(f"生成测试报告失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())