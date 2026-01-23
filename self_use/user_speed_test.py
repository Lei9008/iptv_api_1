import re
import asyncio
import aiohttp
import time
import logging
import os
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, OrderedDict
from collections import OrderedDict

# ===================== 配置类（可按需调整） =====================
class Config:
    CONCURRENT_LIMIT = 20  # 并发测速限制
    TIMEOUT = 10  # 单个请求超时时间（秒）
    RETRY_TIMES = 2  # 失败重试次数
    OUTPUT_DIR = "output"  # 输出目录
    LOG_FILE = "output/speed_test.log"  # 日志文件路径
    LATENCY_THRESHOLD = 550  # 延迟阈值（毫秒），超过则过滤
    PIC_DIR = "pic"  # LOGO文件夹路径
    TEMPLATE_FILE = "demo.txt"  # 模板文件（核心：定义频道顺序）
    INPUT_M3U = "output/live_ipv4.m3u"  # 待测速的M3U文件
    OUTPUT_M3U = "output/live_sources_ipv4.m3u"  # 最终生成的M3U文件
    REPORT_FILE = "output/speed_test_report.txt"  # 测速报告

config = Config()

# ===================== 初始化配置 =====================
# 创建必要文件夹
for dir_path in [config.OUTPUT_DIR, config.PIC_DIR]:
    os.makedirs(dir_path, exist_ok=True)

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

# ===================== 数据结构 =====================
@dataclass
class SpeedTestResult:
    url: str
    latency: Optional[float] = None  # 延迟（毫秒）
    resolution: Optional[str] = None  # 分辨率（仅M3U8）
    success: bool = False  # 测速是否成功
    error: Optional[str] = None  # 错误信息
    test_time: float = time.time()  # 测试时间戳

# ===================== 核心工具类 =====================
class SpeedTester:
    """异步测速工具类"""
    def __init__(self):
        self.session = None

    async def __aenter__(self):
        """创建异步HTTP会话"""
        timeout = aiohttp.ClientTimeout(total=config.TIMEOUT)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        }
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭HTTP会话"""
        if self.session:
            await self.session.close()

    async def measure_latency(self, url: str) -> SpeedTestResult:
        """测量单个URL的延迟和分辨率"""
        result = SpeedTestResult(url=url)

        for attempt in range(config.RETRY_TIMES + 1):  # 包含首次尝试
            try:
                start_time = time.time()
                async with self.session.get(url, ssl=False) as resp:
                    elapsed = (time.time() - start_time) * 1000  # 转毫秒

                    if resp.status == 200:
                        # 解析M3U8分辨率
                        result.resolution = "unknown"
                        if "application/vnd.apple.mpegurl" in resp.headers.get("Content-Type", ""):
                            content = await resp.content.read(1024)
                            res_match = re.search(rb"RESOLUTION=(\d+x\d+)", content)
                            if res_match:
                                result.resolution = res_match.group(1).decode()

                        result.latency = elapsed
                        result.success = True
                        logger.info(f"[{attempt+1}] 成功 - {url[:50]} | 延迟: {elapsed:.2f}ms | 分辨率: {result.resolution}")
                        break
                    else:
                        result.error = f"HTTP {resp.status}"
                        logger.warning(f"[{attempt+1}] 失败 - {url[:50]} | 状态码: {resp.status}")

            except asyncio.TimeoutError:
                result.error = "请求超时"
            except aiohttp.ClientConnectionError:
                result.error = "连接失败"
            except Exception as e:
                result.error = f"未知错误: {str(e)[:50]}"

            # 重试间隔（最后一次不等待）
            if attempt < config.RETRY_TIMES:
                await asyncio.sleep(1)

        if not result.success:
            logger.error(f"最终失败 - {url[:50]} | 原因: {result.error}")
        return result

    async def batch_test(self, urls: List[str]) -> List[SpeedTestResult]:
        """批量测速（带并发限制）"""
        results = []
        semaphore = asyncio.Semaphore(config.CONCURRENT_LIMIT)

        async def worker(url):
            """单个URL的测速任务（受控并发）"""
            async with semaphore:
                result = await self.measure_latency(url)
                results.append(result)

        # 创建并执行所有任务
        tasks = [worker(url) for url in urls]
        await asyncio.gather(*tasks)
        return results

class M3UHandler:
    """M3U文件解析/生成工具类"""
    @staticmethod
    def parse_template(template_file: str) -> OrderedDict:
        """
        解析demo.txt模板，保留原始顺序
        返回: OrderedDict{分类: [频道名列表]}
        """
        template = OrderedDict()
        current_category = None

        try:
            with open(template_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    if "#genre#" in line:
                        # 提取分类
                        current_category = line.split(",")[0].strip()
                        template[current_category] = []
                    elif current_category:
                        # 提取频道名
                        channel_name = line.split(",")[0].strip()
                        template[current_category].append(channel_name)

            logger.info(f"模板解析完成 | 分类数: {len(template)} | 总频道数: {sum(len(v) for v in template.values())}")
        except FileNotFoundError:
            logger.error(f"模板文件不存在: {template_file}")
        except Exception as e:
            logger.error(f"解析模板失败: {e}", exc_info=True)

        return template

    @staticmethod
    def parse_m3u(m3u_file: str) -> List[Tuple[str, str, str]]:
        """
        解析M3U文件
        返回: [(分组, 频道名, URL), ...]
        """
        sources = []
        current_group = None
        current_name = None
        group_pattern = re.compile(r'group-title="([^"]+)"')

        try:
            with open(m3u_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in lines:
                line = line.strip()
                if line.startswith("#EXTINF:"):
                    # 提取分组和频道名
                    group_match = group_pattern.search(line)
                    current_group = group_match.group(1) if group_match else "未分组"
                    # 提取频道名（, 后的内容）
                    name_pos = line.find(",") + 1
                    current_name = line[name_pos:].strip() if name_pos > 0 else "未知频道"
                elif line.startswith(("http://", "https://")) and current_group and current_name:
                    # 去重后添加
                    if not any(s[2] == line for s in sources):
                        sources.append((current_group, current_name, line))
                    current_group = current_name = None

            logger.info(f"M3U解析完成 | 有效直播源数: {len(sources)}")
        except Exception as e:
            logger.error(f"解析M3U失败: {e}", exc_info=True)

        return sources

    @staticmethod
    def generate_m3u(sources: List[Tuple[str, str, str]], output_path: str):
        """
        按模板顺序生成标准化M3U文件
        :param sources: [(分类, 频道名, URL), ...]（模板顺序）
        :param output_path: 输出文件路径
        """
        if not sources:
            logger.warning("无有效频道，跳过M3U生成")
            return

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                # M3U头部
                f.write("#EXTM3U\n")
                f.write(f"# 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 排序规则: 严格遵循 {config.TEMPLATE_FILE} 顺序\n")
                f.write(f"# 延迟阈值: {config.LATENCY_THRESHOLD}ms\n\n")

                # 按模板顺序写入每个频道
                for idx, (group, name, url) in enumerate(sources, 1):
                    # 构建LOGO路径
                    logo_url = f"{config.PIC_DIR}/logos{name}.png"
                    # 标准EXTINF行（含完整元信息）
                    extinf_line = (
                        f"#EXTINF:-1 tvg-id=\"{idx}\" tvg-name=\"{name}\" "
                        f"tvg-logo=\"{logo_url}\" group-title=\"{group}\",{name}"
                    )
                    f.write(f"{extinf_line}\n{url}\n\n")

            logger.info(f"M3U文件生成成功 | 路径: {output_path} | 频道数: {len(sources)}")
        except Exception as e:
            logger.error(f"生成M3U失败: {e}", exc_info=True)

    @staticmethod
    def generate_report(sources: List[Tuple[str, str, str]], result_map: Dict[str, SpeedTestResult], report_path: str):
        """生成详细的测速报告"""
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("="*80 + "\n")
                f.write("IPTV直播源测速报告（按demo.txt顺序）\n")
                f.write("="*80 + "\n")
                f.write(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"模板文件: {config.TEMPLATE_FILE}\n")
                f.write(f"延迟阈值: {config.LATENCY_THRESHOLD}ms\n")
                f.write(f"有效频道数: {len(sources)}\n\n")

                # 按模板顺序写入每个频道的详情
                for idx, (group, name, url) in enumerate(sources, 1):
                    res = result_map[url]
                    f.write(f"{idx}. 分类: {group}\n")
                    f.write(f"   频道: {name}\n")
                    f.write(f"   URL: {url}\n")
                    f.write(f"   延迟: {res.latency:.2f}ms\n")
                    f.write(f"   分辨率: {res.resolution}\n")
                    f.write(f"   状态: 成功\n\n")

            logger.info(f"测速报告生成成功 | 路径: {report_path}")
        except Exception as e:
            logger.error(f"生成报告失败: {e}", exc_info=True)

# ===================== 主程序 =====================
async def main():
    # 1. 解析模板（核心：获取频道顺序）
    template = M3UHandler.parse_template(config.TEMPLATE_FILE)
    if not template:
        logger.error("模板解析失败，程序退出")
        return
    # 扁平化模板：[(分类, 频道名), ...] 严格保留模板顺序
    template_order = []
    for category, names in template.items():
        for name in names:
            template_order.append((category, name))

    # 2. 解析待测速的M3U文件
    live_sources = M3UHandler.parse_m3u(config.INPUT_M3U)
    if not live_sources:
        logger.error("无有效直播源，程序退出")
        return

    # 3. 批量测速
    logger.info(f"开始批量测速 | 总URL数: {len(live_sources)} | 并发限制: {config.CONCURRENT_LIMIT}")
    async with SpeedTester() as tester:
        urls = [src[2] for src in live_sources]
        test_results = await tester.batch_test(urls)
    # 构建URL→测速结果的映射
    result_map = {res.url: res for res in test_results}

    # 4. 核心：按模板顺序筛选有效频道
    final_sources = []
    # 先构建直播源的「分类+频道名」→ URL映射（按延迟升序）
    source_index = {}
    for group, name, url in live_sources:
        res = result_map[url]
        # 只保留达标且成功的URL
        if res.success and res.latency and res.latency <= config.LATENCY_THRESHOLD:
            key = (group.upper(), name.upper())  # 统一大写，避免大小写匹配问题
            if key not in source_index:
                source_index[key] = []
            source_index[key].append((url, res.latency))

    # 按模板顺序遍历，匹配有效URL
    for template_group, template_name in template_order:
        key = (template_group.upper(), template_name.upper())
        if key in source_index:
            # 取延迟最低的URL
            sorted_urls = sorted(source_index[key], key=lambda x: x[1])
            best_url = sorted_urls[0][0]
            final_sources.append((template_group, template_name, best_url))
            logger.debug(f"匹配成功 | [{template_group}] {template_name} | 最优延迟: {sorted_urls[0][1]:.2f}ms")
        else:
            logger.warning(f"无有效URL | [{template_group}] {template_name}")

    # 5. 生成最终文件
    # 5.1 生成M3U文件
    M3UHandler.generate_m3u(final_sources, config.OUTPUT_M3U)
    # 5.2 生成测速报告
    M3UHandler.generate_report(final_sources, result_map, config.REPORT_FILE)

    # 6. 输出统计信息
    total_tested = len(test_results)
    total_success = sum(1 for res in test_results if res.success)
    total_valid = len(final_sources)
    logger.info(f"===== 测速完成 =====")
    logger.info(f"总测试数: {total_tested}")
    logger.info(f"成功数: {total_success} ({total_success/total_tested*100:.1f}%)")
    logger.info(f"模板匹配有效数: {total_valid}")
    logger.info(f"最终M3U文件: {config.OUTPUT_M3U}")

if __name__ == "__main__":
    # 兼容Windows异步事件循环
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # 运行主程序
    asyncio.run(main())
