import re
import asyncio
import aiohttp
import time
import logging
import os
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional, OrderedDict
from collections import OrderedDict

# 配置类
class Config:
    CONCURRENT_LIMIT = 20  # 并发限制
    TIMEOUT = 10  # 超时时间（秒）
    RETRY_TIMES = 2  # 重试次数
    OUTPUT_DIR = "output"  # 输出目录
    LOG_FILE = "output/speed_test.log"  # 日志文件
    LATENCY_THRESHOLD = 550  # 延迟阈值（毫秒）
    PIC_DIR = "pic"  # LOGO文件夹配置
    TEMPLATE_FILE = "demo.txt"  # 模板文件路径

config = Config()

# 提前创建输出目录和LOGO目录
os.makedirs(config.OUTPUT_DIR, exist_ok=True)
os.makedirs(config.PIC_DIR, exist_ok=True)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
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

# 速度测试工具类
class SpeedTester:
    def __init__(self):
        self.session = None
    
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=config.TIMEOUT)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
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
                async with self.session.get(url, ssl=False) as response:  # 忽略SSL错误
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
                                logger.debug(f"解析分辨率失败 {url}: {e}")
                        
                        result.latency = elapsed_time
                        result.resolution = resolution
                        result.success = True
                        logger.info(f"[{attempt+1}] {url} 测试成功 | 延迟: {elapsed_time:.2f}ms | 分辨率: {resolution}")
                        break
                    else:
                        result.error = f"HTTP状态码: {response.status}"
                        logger.warning(f"[{attempt+1}] {url} 失败 | 状态码: {response.status}")
            # 细分异常类型
            except asyncio.TimeoutError:
                result.error = "请求超时"
            except aiohttp.ClientConnectionError:
                result.error = "连接失败"
            except Exception as e:
                result.error = f"未知错误: {str(e)}"
            
            if attempt < retry_times - 1:
                await asyncio.sleep(1)  # 重试间隔
        
        return result
    
    async def batch_speed_test(self, urls: List[str]) -> List[SpeedTestResult]:
        """批量测速（带并发控制）"""
        results = []
        semaphore = asyncio.Semaphore(config.CONCURRENT_LIMIT)

        async def worker(url):
            nonlocal results
            async with semaphore:
                result = await self.measure_latency(url, config.RETRY_TIMES)
                results.append(result)

        tasks = [worker(url) for url in urls]
        await asyncio.gather(*tasks)
        
        # 按延迟升序排序，无延迟的放最后
        return sorted(results, key=lambda x: x.latency if x.latency else float("inf"))

# M3U文件处理类
class M3UProcessor:
    @staticmethod
    def parse_m3u(file_path: str) -> List[Tuple[str, str, str]]:
        """解析M3U文件，返回[(分组, 名称, URL), ...]"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            live_sources = []
            current_group = None
            current_name = None
            group_pattern = re.compile(r'group-title="([^"]+)"')
            
            for line in lines:
                line = line.strip()
                if line.startswith('#EXTINF:'):
                    # 提取分组和名称
                    group_match = group_pattern.search(line)
                    current_group = group_match.group(1) if group_match else "未分组"
                    
                    name_start = line.find(',') + 1
                    current_name = line[name_start:].strip() if name_start > 0 else "未知频道"
                elif line.startswith(("http://", "https://")) and current_group and current_name:
                    # 去重，避免重复URL
                    if not any(src[2] == line for src in live_sources):
                        live_sources.append((current_group, current_name, line))
                    current_group = None
                    current_name = None
            
            return live_sources
        except Exception as e:
            logger.error(f"解析M3U失败: {e}", exc_info=True)
            return []
    
    @staticmethod
    def parse_template(template_file: str) -> OrderedDict:
        """解析demo.txt模板，返回有序字典 {分类: [频道名列表]}"""
        template_channels = OrderedDict()
        current_category = None
        
        try:
            with open(template_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    # 跳过空行、注释行
                    if not line or line.startswith("#"):
                        continue
                    
                    if "#genre#" in line:
                        # 提取分类名
                        current_category = line.split(",")[0].strip()
                        template_channels[current_category] = []
                        logger.debug(f"模板文件第{line_num}行：识别分类 {current_category}")
                    elif current_category:
                        # 提取频道名
                        channel_name = line.split(",")[0].strip()
                        template_channels[current_category].append(channel_name)
                        logger.debug(f"模板文件第{line_num}行：添加频道 {channel_name} 到分类 {current_category}")
        
        except FileNotFoundError:
            logger.error(f"模板文件不存在：{template_file}")
        except Exception as e:
            logger.error(f"解析模板文件失败：{e}", exc_info=True)
        
        return template_channels
    
    @staticmethod
    def generate_m3u(live_sources: List[Tuple[str, str, str]], output_path: str) -> None:
        """
        生成带扩展字段的M3U文件（含tvg-id、tvg-logo、group-title）
        :param live_sources: 三元组列表 [(分组, 名称, URL)]
        :param output_path: 输出路径
        """
        # 前置校验
        if not live_sources:
            logger.warning("直播源列表为空，跳过生成")
            return

        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                # 标准M3U头部
                f.write('#EXTM3U\n')
                # 写入注释行记录生成时间（不影响播放器解析）
                f.write(f"# 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 排序规则: 按demo.txt模板顺序 | 延迟阈值: {config.LATENCY_THRESHOLD}ms\n\n")

                # 遍历生成每个频道的信息
                for index, (group, name, url) in enumerate(live_sources, start=1):
                    if not name or not url:
                        logger.warning(f"跳过无效频道: 名称={name}, URL={url}")
                        continue
                    
                    # 使用配置的PIC_DIR和循环变量name
                    logo_url = f"{config.PIC_DIR}/logos{name}.png"
                    # 标准EXTINF格式，包含所有扩展字段
                    extinf_line = f'#EXTINF:-1 tvg-id="{index}" tvg-name="{name}" tvg-logo="{logo_url}" group-title="{group}",{name}'
                    
                    f.write(extinf_line + "\n")
                    f.write(url + "\n\n")  # 空行分隔，提升可读性
            
            logger.info(f"成功生成M3U文件: {output_path} | 共{len(live_sources)}个频道")
        except PermissionError:
            logger.error(f"无写入权限: {output_path}")
        except Exception as e:
            logger.error(f"生成M3U失败: {e}", exc_info=True)

# 主程序
async def main():
    input_file = "output/live_ipv4.m3u"
    output_file = f"{config.OUTPUT_DIR}/live_sources_ipv4.m3u"
    report_file = f"{config.OUTPUT_DIR}/speed_test_report_log.txt"

    # 1. 解析demo.txt模板（核心：获取模板顺序）
    logger.info(f"开始解析模板文件: {config.TEMPLATE_FILE}")
    template_channels = M3UProcessor.parse_template(config.TEMPLATE_FILE)
    if not template_channels:
        logger.error("模板文件解析为空，程序退出")
        return
    # 扁平化模板：[(分类, 频道名), ...] 保留模板顺序
    template_flat = []
    for category, names in template_channels.items():
        for name in names:
            template_flat.append((category, name))
    logger.info(f"模板解析完成，共{len(template_flat)}个频道（按模板顺序）")

    # 2. 解析M3U直播源
    logger.info(f"开始解析直播源文件: {input_file}")
    m3u_processor = M3UProcessor()
    live_sources = m3u_processor.parse_m3u(input_file)
    
    if not live_sources:
        logger.error("未找到有效直播源，程序退出")
        return
    logger.info(f"直播源解析完成，共找到 {len(live_sources)} 个去重直播源")

    # 3. 批量测速
    logger.info("开始速度测试...")
    async with SpeedTester() as tester:
        urls = [src[2] for src in live_sources]
        results = await tester.batch_speed_test(urls)

    # 4. 构建直播源映射：(分类, 频道名) → 低延迟URL列表
    url_to_result = {res.url: res for res in results}
    source_map = {}  # key: (分类, 频道名) → value: [(URL, 延迟), ...]
    for group, name, url in live_sources:
        result = url_to_result.get(url)
        # 筛选符合延迟阈值的有效URL
        if result and result.success and result.latency and result.latency <= config.LATENCY_THRESHOLD:
            key = (group, name)
            if key not in source_map:
                source_map[key] = []
            source_map[key].append((url, result.latency))
    
    # 5. 按模板顺序筛选有效频道（核心逻辑）
    final_sources = []
    for template_group, template_name in template_flat:
        # 匹配模板中的频道（忽略大小写，提高匹配率）
        match_key = None
        for (group, name) in source_map.keys():
            if name.upper() == template_name.upper() and group.upper() == template_group.upper():
                match_key = (group, name)
                break
        
        if match_key:
            # 对该频道的URL按延迟升序排序，取最优（最低延迟）
            sorted_urls = sorted(source_map[match_key], key=lambda x: x[1])
            if sorted_urls:
                best_url = sorted_urls[0][0]
                final_sources.append((template_group, template_name, best_url))
                logger.debug(f"模板匹配成功: [{template_group}] {template_name} → 最优URL延迟: {sorted_urls[0][1]:.2f}ms")
        else:
            logger.warning(f"模板中频道未找到有效直播源: [{template_group}] {template_name}")

    # 6. 生成日志报告
    success_count = sum(1 for res in results if res.success)
    logger.info(f"测试完成 | 总数: {len(results)} | 成功: {success_count} | 模板匹配有效数: {len(final_sources)}")
    
    # 打印前10个按模板排序的频道
    logger.info("前10个按模板顺序的有效直播源:")
    for i, (group, name, url) in enumerate(final_sources[:10], 1):
        latency = url_to_result[url].latency
        res = url_to_result[url].resolution
        logger.info(f"{i}. [{group}] {name} | 延迟: {latency:.2f}ms | 分辨率: {res}")

    # 7. 生成M3U和详细报告
    m3u_processor.generate_m3u(final_sources, output_file)
    
    # 写入详细报告
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("IPTV直播源测速报告（按demo.txt模板顺序）\n")
            f.write("="*60 + "\n")
            f.write(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"延迟阈值: {config.LATENCY_THRESHOLD}ms\n")
            f.write(f"模板文件: {config.TEMPLATE_FILE}\n")
            f.write(f"总测试数: {len(results)} | 成功数: {success_count} | 模板匹配有效数: {len(final_sources)}\n\n")
            
            for i, (group, name, url) in enumerate(final_sources, 1):
                r = url_to_result[url]
                f.write(f"{i}. 分组: {group} | 名称: {name}\n")
                f.write(f"   URL: {url}\n")
                f.write(f"   延迟: {r.latency:.2f}ms | 分辨率: {r.resolution} | 状态: 成功\n\n")
        logger.info(f"详细报告已生成: {report_file}")
    except Exception as e:
        logger.error(f"生成报告失败: {e}")

if __name__ == "__main__":
    # 兼容Windows系统事件循环
    if os.name == 'nt':  # Windows系统
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
