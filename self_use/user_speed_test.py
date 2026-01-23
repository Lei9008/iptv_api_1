import re
import asyncio
import aiohttp
import time
import logging
import os
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from collections import OrderedDict

# ===================== 配置类 =====================
class Config:
    CONCURRENT_LIMIT = 20  # 并发限制
    TIMEOUT = 10  # 超时时间（秒）
    RETRY_TIMES = 2  # 重试次数
    OUTPUT_DIR = "output"
    LOG_FILE = "output/speed_test.log"
    LATENCY_THRESHOLD = 550  # 延迟阈值（毫秒）
    PIC_DIR = "pic"
    TEMPLATE_FILE = "demo.txt"  # 模板文件
    INPUT_M3U = "output/live_ipv4.m3u"  # 待测M3U
    OUTPUT_M3U = "output/live_sources_ipv4.m3u"  # 输出M3U
    REPORT_FILE = "output/speed_test_report.txt"  # 报告文件

config = Config()

# ===================== 初始化 =====================
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
    latency: Optional[float] = None
    resolution: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    test_time: float = time.time()

# ===================== 核心工具函数 =====================
def clean_channel_name(name: str) -> str:
    """
    标准化清洗频道名称（关键：用于匹配）
    处理规则：去特殊字符、去空白、转大写、数字标准化
    """
    if not name:
        return ""
    # 移除特殊字符：$、「、」、-、空格、括号等
    cleaned = re.sub(r'[$「」\-()（）\s+]', '', name)
    # 数字标准化（如 05 → 5）
    cleaned = re.sub(r'(\D*)(\d+)', lambda m: m.group(1) + str(int(m.group(2))), cleaned)
    return cleaned.upper()  # 统一大写

# ===================== 测速类 =====================
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
        result = SpeedTestResult(url=url)
        for attempt in range(config.RETRY_TIMES + 1):
            try:
                start = time.time()
                async with self.session.get(url, ssl=False) as resp:
                    elapsed = (time.time() - start) * 1000
                    if resp.status == 200:
                        result.latency = elapsed
                        result.success = True
                        # 解析M3U8分辨率
                        if "application/vnd.apple.mpegurl" in resp.headers.get("Content-Type", ""):
                            content = await resp.content.read(1024)
                            res_match = re.search(rb"RESOLUTION=(\d+x\d+)", content)
                            result.resolution = res_match.group(1).decode() if res_match else "unknown"
                        else:
                            result.resolution = "unknown"
                        logger.info(f"[{attempt+1}] 成功 {url[:50]} | 延迟: {elapsed:.2f}ms | 分辨率: {result.resolution}")
                        break
                    else:
                        result.error = f"HTTP {resp.status}"
            except asyncio.TimeoutError:
                result.error = "超时"
            except aiohttp.ClientConnectionError:
                result.error = "连接失败"
            except Exception as e:
                result.error = f"未知错误: {str(e)[:30]}"
            if attempt < config.RETRY_TIMES:
                await asyncio.sleep(1)
        if not result.success:
            logger.warning(f"最终失败 {url[:50]} | 原因: {result.error}")
        return result

    async def batch_test(self, urls: List[str]) -> List[SpeedTestResult]:
        results = []
        semaphore = asyncio.Semaphore(config.CONCURRENT_LIMIT)
        async def worker(url):
            async with semaphore:
                results.append(await self.measure_latency(url))
        await asyncio.gather(*[worker(url) for url in urls])
        return results

# ===================== M3U处理类 =====================
class M3UHandler:
    @staticmethod
    def parse_template() -> Tuple[OrderedDict, Dict[str, Tuple[str, str]]]:
        """
        解析模板并生成匹配映射
        返回：
            1. 有序模板字典 {分类: [原始频道名列表]}
            2. 名称匹配映射 {标准名: (原始分类, 原始频道名)}
        """
        template = OrderedDict()
        name_map = {}  # 核心：标准名 → (分类, 原始名)
        current_category = None

        try:
            with open(config.TEMPLATE_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "#genre#" in line:
                        current_category = line.split(",")[0].strip()
                        template[current_category] = []
                    elif current_category:
                        raw_name = line.split(",")[0].strip()
                        template[current_category].append(raw_name)
                        # 生成标准名并加入映射
                        std_name = clean_channel_name(raw_name)
                        if std_name not in name_map:
                            name_map[std_name] = (current_category, raw_name)
                        else:
                            logger.warning(f"模板存在重复频道名（标准化后）: {raw_name}")
        except FileNotFoundError:
            logger.error(f"模板文件不存在: {config.TEMPLATE_FILE}")
        except Exception as e:
            logger.error(f"解析模板失败: {e}", exc_info=True)

        logger.info(f"模板解析完成 | 分类数: {len(template)} | 频道数: {sum(len(v) for v in template.values())}")
        return template, name_map

    @staticmethod
    def parse_m3u() -> List[Tuple[str, str, str, str]]:
        """
        解析M3U并生成标准名
        返回：[(原始分类, 原始名称, URL, 标准名), ...]
        """
        sources = []
        current_group = None
        current_name = None
        group_pattern = re.compile(r'group-title="([^"]+)"')

        try:
            with open(config.INPUT_M3U, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#EXTINF:"):
                        # 提取分组和原始名称
                        group_match = group_pattern.search(line)
                        current_group = group_match.group(1) if group_match else "未分组"
                        name_pos = line.find(",") + 1
                        current_name = line[name_pos:].strip() if name_pos > 0 else "未知频道"
                    elif line.startswith(("http://", "https://")) and current_group and current_name:
                        # 生成标准名，去重添加
                        std_name = clean_channel_name(current_name)
                        if not any(s[3] == std_name and s[2] == line for s in sources):
                            sources.append((current_group, current_name, line, std_name))
                        current_group = current_name = None
        except Exception as e:
            logger.error(f"解析M3U失败: {e}", exc_info=True)

        logger.info(f"M3U解析完成 | 直播源数: {len(sources)}")
        return sources

    @staticmethod
    def generate_m3u(match_sources: List[Tuple[str, str, str]]):
        """生成最终M3U文件（按模板名称匹配）"""
        if not match_sources:
            logger.warning("无匹配的频道，跳过生成")
            return
        try:
            with open(config.OUTPUT_M3U, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                f.write(f"# 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 匹配规则: 按 {config.TEMPLATE_FILE} 频道名匹配\n")
                f.write(f"# 延迟阈值: {config.LATENCY_THRESHOLD}ms\n\n")
                for idx, (category, name, url) in enumerate(match_sources, 1):
                    logo_url = f"{config.PIC_DIR}/logos{name}.png"
                    extinf = f'#EXTINF:-1 tvg-id="{idx}" tvg-name="{name}" tvg-logo="{logo_url}" group-title="{category}",{name}'
                    f.write(f"{extinf}\n{url}\n\n")
            logger.info(f"最终M3U生成成功 | 路径: {config.OUTPUT_M3U} | 频道数: {len(match_sources)}")
        except Exception as e:
            logger.error(f"生成M3U失败: {e}", exc_info=True)

    @staticmethod
    def generate_report(match_sources: List[Tuple[str, str, str]], result_map: Dict[str, SpeedTestResult]):
        """生成匹配结果报告"""
        try:
            with open(config.REPORT_FILE, "w", encoding="utf-8") as f:
                f.write("="*60 + "\n")
                f.write("IPTV直播源匹配测速报告\n")
                f.write("="*60 + "\n")
                f.write(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"匹配模板: {config.TEMPLATE_FILE}\n")
                f.write(f"延迟阈值: {config.LATENCY_THRESHOLD}ms\n")
                f.write(f"匹配成功数: {len(match_sources)}\n\n")
                for idx, (category, name, url) in enumerate(match_sources, 1):
                    res = result_map[url]
                    f.write(f"{idx}. 分类: {category}\n")
                    f.write(f"   频道名: {name}\n")
                    f.write(f"   URL: {url[:80]}\n")
                    f.write(f"   延迟: {res.latency:.2f}ms | 分辨率: {res.resolution}\n\n")
            logger.info(f"报告生成成功 | 路径: {config.REPORT_FILE}")
        except Exception as e:
            logger.error(f"生成报告失败: {e}", exc_info=True)

# ===================== 主程序 =====================
async def main():
    # 1. 解析模板，获取名称匹配映射
    template, name_map = M3UHandler.parse_template()
    if not name_map:
        logger.error("模板名称映射为空，程序退出")
        return

    # 2. 解析待测M3U，获取带标准名的直播源
    live_sources = M3UHandler.parse_m3u()
    if not live_sources:
        logger.error("无直播源，程序退出")
        return

    # 3. 批量测速
    urls = [src[2] for src in live_sources]
    logger.info(f"开始批量测速 | 总URL数: {len(urls)}")
    async with SpeedTester() as tester:
        test_results = await tester.batch_test(urls)
    result_map = {res.url: res for res in test_results}

    # 4. 核心：按模板名称匹配直播源（只保留匹配且达标的）
    match_sources = []
    # 先构建 直播源标准名 → [(URL, 延迟, 原始分类, 原始名)]
    source_std_map = {}
    for raw_group, raw_name, url, std_name in live_sources:
        res = result_map.get(url)
        if res and res.success and res.latency and res.latency <= config.LATENCY_THRESHOLD:
            if std_name not in source_std_map:
                source_std_map[std_name] = []
            source_std_map[std_name].append((url, res.latency, raw_group, raw_name))

    # 按模板顺序匹配（模板顺序不变）
    for category in template:
        for template_raw_name in template[category]:
            template_std_name = clean_channel_name(template_raw_name)
            # 匹配直播源标准名
            if template_std_name in source_std_map:
                # 取延迟最低的URL
                best_source = sorted(source_std_map[template_std_name], key=lambda x: x[1])[0]
                best_url = best_source[0]
                # 用模板的分类和名称（保证和模板一致）
                match_sources.append((category, template_raw_name, best_url))
                logger.info(f"匹配成功 | [{category}] {template_raw_name} | 延迟: {best_source[1]:.2f}ms")
            else:
                logger.warning(f"无匹配直播源 | [{category}] {template_raw_name}")

    # 5. 生成最终文件
    M3UHandler.generate_m3u(match_sources)
    M3UHandler.generate_report(match_sources, result_map)

    # 6. 统计信息
    logger.info(f"\n===== 任务完成 =====")
    logger.info(f"模板频道总数: {sum(len(v) for v in template.values())}")
    logger.info(f"匹配成功数: {len(match_sources)}")
    logger.info(f"最终M3U路径: {config.OUTPUT_M3U}")

if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
