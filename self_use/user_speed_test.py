import re
import asyncio
import aiohttp
import time
import logging
import os
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional, Any
from pathlib import Path
from urllib.parse import urlparse

# ===================== 配置类（优化：支持外部配置/类型注解） =====================
class Config:
    # 核心配置
    CONCURRENT_LIMIT: int = 20  # 并发限制（根据网络调整）
    TIMEOUT: int = 10  # 超时时间（秒）
    RETRY_TIMES: int = 2  # 重试次数
    LATENCY_THRESHOLD: float = 550.0  # 延迟阈值（毫秒）
    
    # 路径配置（使用Path更安全）
    BASE_DIR: Path = Path(__file__).parent
    OUTPUT_DIR: Path = BASE_DIR / "output"
    LOG_DIR: Path = OUTPUT_DIR / "logs"
    LOG_FILE: Path = LOG_DIR / "speed_test.log"
    REPORT_DIR: Path = OUTPUT_DIR / "reports"
    
    # 日志级别
    LOG_LEVEL: int = logging.INFO
    
    # M3U生成配置
    LOGO_BASE_URL: str = "./pic/logos/"  # LOGO路径前缀（修复分隔符问题）
    EPG_URL: str = "https://epg.112114.xyz/pp.xml"  # EPG地址（增强M3U标准性）
    
    @classmethod
    def load_from_file(cls, config_path: str = "config.json") -> None:
        """从JSON文件加载配置（增强灵活性）"""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_dict = json.load(f)
            for key, value in config_dict.items():
                if hasattr(cls, key):
                    setattr(cls, key, value)
            # 这里用临时日志输出，避免依赖logger
            print(f"成功从{config_path}加载自定义配置")
        except FileNotFoundError:
            print(f"未找到配置文件{config_path}，使用默认配置")
        except Exception as e:
            print(f"加载配置文件失败: {e}")

# 初始化配置
config = Config()

# ===================== 日志配置（优先初始化，解决顺序问题） =====================
def setup_logging() -> logging.Logger:
    """配置日志系统（更规范的日志格式）"""
    # 先创建临时日志（目录初始化前）
    temp_logger = logging.getLogger("IPTV_Speed_Tester_Temp")
    temp_logger.setLevel(logging.INFO)
    temp_logger.handlers.clear()
    
    # 控制台处理器（临时，目录创建后会替换）
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    temp_logger.addHandler(console_handler)
    
    # 尝试创建日志目录（如果失败，用临时日志输出）
    try:
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        # 正式日志配置（文件+控制台）
        logger = logging.getLogger("IPTV_Speed_Tester")
        logger.setLevel(config.LOG_LEVEL)
        logger.handlers.clear()
        
        # 文件处理器（追加模式，避免覆盖）
        file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8", mode="a")
        file_handler.setFormatter(formatter)
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        return logger
    except Exception as e:
        temp_logger.error(f"正式日志初始化失败，使用临时日志: {e}")
        return temp_logger

# 优先初始化日志（解决顺序问题）
logger = setup_logging()

# ===================== 目录初始化（修复：依赖已初始化的logger） =====================
def init_directories() -> None:
    """初始化所有必要目录"""
    try:
        for dir_path in [config.OUTPUT_DIR, config.LOG_DIR, config.REPORT_DIR]:
            dir_path.mkdir(parents=True, exist_ok=True)
        logger.info("目录初始化完成")
    except PermissionError:
        logger.critical("无目录创建权限，请检查路径权限", exc_info=True)
        raise SystemExit(1)
    except Exception as e:
        logger.critical(f"目录初始化失败: {e}", exc_info=True)
        raise SystemExit(1)

# 初始化目录（此时logger已定义）
init_directories()

# ===================== 数据类（优化：增加类型注解/序列化） =====================
@dataclass
class SpeedTestResult:
    url: str
    latency: Optional[float] = None  # 延迟（毫秒）
    resolution: Optional[str] = None  # 分辨率
    success: bool = False  # 是否成功
    error: Optional[str] = None  # 错误信息
    test_time: float = 0.0  # 测试时间戳
    attempt_times: int = 0  # 实际尝试次数（新增）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（便于序列化）"""
        return asdict(self)
    
    def is_valid(self) -> bool:
        """判断是否为有效结果（成功且延迟达标）"""
        return self.success and self.latency is not None and self.latency <= config.LATENCY_THRESHOLD

# ===================== 速度测试工具类（优化：性能/容错/功能增强） =====================
class SpeedTester:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore: Optional[asyncio.Semaphore] = None
    
    async def __aenter__(self) -> "SpeedTester":
        """初始化异步会话（优化：TCP连接复用）"""
        try:
            # 优化TCP连接池和超时配置
            timeout = aiohttp.ClientTimeout(
                total=config.TIMEOUT,
                connect=5,  # 连接超时单独配置
                sock_read=5  # 读取超时单独配置
            )
            # 优化请求头（更贴近真实浏览器）
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive"
            }
            # 创建会话（支持TCP连接复用）
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
                connector=aiohttp.TCPConnector(
                    limit=config.CONCURRENT_LIMIT,  # 连接池大小
                    ttl_dns_cache=300,  # DNS缓存时间（秒）
                    ssl=False  # 忽略SSL错误（保留原逻辑）
                )
            )
            self.semaphore = asyncio.Semaphore(config.CONCURRENT_LIMIT)
            logger.info("异步会话初始化完成")
            return self
        except Exception as e:
            logger.error(f"会话初始化失败: {e}", exc_info=True)
            raise
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """安全关闭会话"""
        if self.session:
            await self.session.close()
            logger.info("异步会话已关闭")
    
    @staticmethod
    def _parse_resolution(content: bytes) -> str:
        """解析M3U8分辨率（优化：更健壮的正则）"""
        try:
            # 匹配 RESOLUTION=1920x1080 格式
            res_match = re.search(rb"RESOLUTION=(\d+x\d+)", content, re.IGNORECASE)
            if res_match:
                return res_match.group(1).decode()
            # 匹配带宽（备选）
            bw_match = re.search(rb"BANDWIDTH=(\d+)", content)
            if bw_match:
                bw = int(bw_match.group(1))
                if bw >= 5000000:
                    return "1080p"
                elif bw >= 2000000:
                    return "720p"
                elif bw >= 1000000:
                    return "480p"
                else:
                    return "360p"
            return "unknown"
        except Exception:
            return "unknown"
    
    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """校验URL有效性（新增：过滤无效URL）"""
        try:
            parsed = urlparse(url)
            return all([parsed.scheme, parsed.netloc])
        except:
            return False
    
    async def measure_latency(self, url: str) -> SpeedTestResult:
        """测量单个URL的延迟（优化：更细粒度的异常处理/尝试次数记录）"""
        result = SpeedTestResult(url=url, test_time=time.time())
        
        # 前置URL校验
        if not self._is_valid_url(url):
            result.error = "无效URL格式"
            logger.warning(f"跳过无效URL: {url}")
            return result
        
        # 重试逻辑
        for attempt in range(1, config.RETRY_TIMES + 1):
            result.attempt_times = attempt
            try:
                start_time = time.perf_counter()  # 更高精度的计时
                async with self.session.get(url) as response:
                    elapsed_time = (time.perf_counter() - start_time) * 1000  # 转换为毫秒
                    
                    if response.status == 200:
                        # 解析分辨率（仅读取前1KB，减少IO）
                        resolution = "unknown"
                        content_type = response.headers.get("Content-Type", "")
                        if "application/vnd.apple.mpegurl" in content_type:
                            content = await response.content.read(1024)
                            resolution = self._parse_resolution(content)
                        
                        # 更新结果
                        result.latency = round(elapsed_time, 2)  # 保留两位小数
                        result.resolution = resolution
                        result.success = True
                        logger.debug(f"[{attempt}] {url} 成功 | 延迟: {result.latency}ms | 分辨率: {resolution}")
                        break
                    else:
                        result.error = f"HTTP状态码: {response.status}"
                        logger.warning(f"[{attempt}] {url} 失败 | 状态码: {response.status}")
            
            except asyncio.TimeoutError:
                result.error = "请求超时"
                logger.warning(f"[{attempt}] {url} 失败 | 超时")
            except aiohttp.ClientConnectionError:
                result.error = "连接失败（网络/服务器问题）"
                logger.warning(f"[{attempt}] {url} 失败 | 连接失败")
            except aiohttp.ClientError as e:
                result.error = f"客户端错误: {str(e)[:50]}"
                logger.warning(f"[{attempt}] {url} 失败 | 客户端错误: {str(e)[:50]}")
            except Exception as e:
                result.error = f"未知错误: {str(e)[:50]}"
                logger.error(f"[{attempt}] {url} 失败 | 未知错误", exc_info=True)
            
            # 重试间隔（指数退避，避免频繁重试）
            if attempt < config.RETRY_TIMES:
                await asyncio.sleep(0.5 * attempt)
        
        return result
    
    async def batch_speed_test(self, urls: List[str]) -> List[SpeedTestResult]:
        """批量测速（优化：进度日志/异常捕获）"""
        if not urls:
            logger.warning("测速URL列表为空")
            return []
        
        results: List[SpeedTestResult] = []
        total = len(urls)
        completed = 0
        
        async def worker(url: str) -> None:
            nonlocal completed
            async with self.semaphore:
                result = await self.measure_latency(url)
                results.append(result)
                completed += 1
                # 进度日志（每完成10%输出一次）
                if completed % max(1, total // 10) == 0:
                    progress = (completed / total) * 100
                    logger.info(f"测速进度: {completed}/{total} ({progress:.1f}%)")
        
        # 创建任务并执行
        try:
            logger.info(f"开始批量测速 | 总数: {total} | 并发: {config.CONCURRENT_LIMIT} | 超时: {config.TIMEOUT}s")
            tasks = [worker(url) for url in urls]
            await asyncio.gather(*tasks, return_exceptions=True)  # 单个任务失败不影响整体
        except Exception as e:
            logger.error(f"批量测速异常: {e}", exc_info=True)
        
        # 排序：有效结果按延迟升序，无效结果放最后
        sorted_results = sorted(
            results,
            key=lambda x: (not x.is_valid(), x.latency if x.latency else float("inf"))
        )
        
        # 统计日志
        success_count = sum(1 for r in results if r.success)
        valid_count = sum(1 for r in results if r.is_valid())
        logger.info(f"测速完成 | 总数: {total} | 成功: {success_count} | 有效（延迟≤{config.LATENCY_THRESHOLD}ms）: {valid_count}")
        
        return sorted_results

# ===================== M3U处理类（优化：健壮性/标准性/去重） =====================
class M3UProcessor:
    @staticmethod
    def parse_m3u(file_path: str | Path) -> List[Tuple[str, str, str]]:
        """解析M3U文件（优化：Path支持/去重增强/容错）"""
        file_path = Path(file_path)
        live_sources: List[Tuple[str, str, str]] = []
        seen_urls: set[str] = set()  # 去重URL集合
        
        try:
            if not file_path.exists():
                logger.error(f"M3U文件不存在: {file_path}")
                return []
            
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f.readlines()]
            
            current_group: Optional[str] = None
            current_name: Optional[str] = None
            group_pattern = re.compile(r'group-title="([^"]+)"', re.IGNORECASE)
            
            for line_num, line in enumerate(lines, 1):
                if not line:
                    continue
                
                # 解析EXTINF行
                if line.startswith('#EXTINF:'):
                    # 提取分组
                    group_match = group_pattern.search(line)
                    current_group = group_match.group(1).strip() if group_match else "未分组"
                    # 提取频道名
                    name_start = line.find(',') + 1
                    current_name = line[name_start:].strip() if name_start > 0 else f"未知频道_{line_num}"
                
                # 解析URL行
                elif line.startswith(("http://", "https://")):
                    if current_group and current_name and line not in seen_urls:
                        seen_urls.add(line)
                        live_sources.append((current_group, current_name, line))
                    # 重置状态，避免污染下一个频道
                    current_group = None
                    current_name = None
        
        except PermissionError:
            logger.error(f"无读取权限: {file_path}")
        except Exception as e:
            logger.error(f"解析M3U失败: {e}", exc_info=True)
        
        # 去重后日志
        logger.info(f"解析M3U完成 | 原始行数: {len(lines)} | 去重后频道数: {len(live_sources)}")
        return live_sources
    
    @staticmethod
    def generate_m3u(live_sources: List[Tuple[str, str, str]], 
                     output_path: str | Path,
                     url_to_result: Dict[str, SpeedTestResult]) -> None:
        """生成M3U文件（优化：标准格式/LOGO路径修复/注释增强）"""
        output_path = Path(output_path)
        
        # 前置校验
        if not live_sources:
            logger.warning("有效直播源为空，跳过M3U生成")
            return
        
        try:
            # 创建输出目录
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                # 标准M3U头部（包含EPG）
                f.write(f'#EXTM3U x-tvg-url="{config.EPG_URL}"\n')
                # 生成信息注释
                f.write(f"# 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 筛选条件: 延迟≤{config.LATENCY_THRESHOLD}ms | 并发数: {config.CONCURRENT_LIMIT}\n")
                f.write(f"# 总计有效频道: {len(live_sources)}\n\n")
                
                # 按分组排序后写入
                grouped_sources: Dict[str, List[Tuple[str, str, str]]] = {}
                for group, name, url in live_sources:
                    if group not in grouped_sources:
                        grouped_sources[group] = []
                    grouped_sources[group].append((name, url))
                
                # 遍历分组写入
                index = 1
                for group in sorted(grouped_sources.keys()):
                    f.write(f"# 分组: {group}\n")
                    for name, url in grouped_sources[group]:
                        # 修复LOGO路径（添加分隔符）
                        logo_url = f"{config.LOGO_BASE_URL}{name}.png"
                        # 获取测速信息（用于注释）
                        result = url_to_result.get(url)
                        latency_note = f" | 延迟:{result.latency}ms" if result and result.latency else ""
                        
                        # 标准EXTINF行
                        extinf_line = (
                            f'#EXTINF:-1 tvg-id="{index}" tvg-name="{name}" '
                            f'tvg-logo="{logo_url}" group-title="{group}",{name}{latency_note}'
                        )
                        f.write(extinf_line + "\n")
                        f.write(url + "\n\n")
                        index += 1
            
            logger.info(f"M3U文件生成成功 | 路径: {output_path.absolute()} | 频道数: {len(live_sources)}")
        except PermissionError:
            logger.error(f"无写入权限: {output_path}")
        except Exception as e:
            logger.error(f"生成M3U失败: {e}", exc_info=True)

# ===================== 报告生成（优化：多格式报告/详细统计） =====================
class ReportGenerator:
    @staticmethod
    def generate_detailed_report(live_sources: List[Tuple[str, str, str]],
                                 url_to_result: Dict[str, SpeedTestResult],
                                 report_path: str | Path) -> None:
        """生成详细的测速报告（优化：结构化/易读）"""
        report_path = Path(report_path)
        
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(report_path, 'w', encoding='utf-8') as f:
                # 报告头部
                f.write("="*60 + "\n")
                f.write("IPTV直播源测速报告\n")
                f.write("="*60 + "\n")
                f.write(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"配置信息: 并发={config.CONCURRENT_LIMIT} | 超时={config.TIMEOUT}s | 重试={config.RETRY_TIMES}次 | 延迟阈值={config.LATENCY_THRESHOLD}ms\n")
                
                # 统计信息
                total_tested = len(url_to_result)
                success_count = sum(1 for r in url_to_result.values() if r.success)
                valid_count = len(live_sources)
                avg_latency = sum(r.latency for r in url_to_result.values() if r.is_valid()) / valid_count if valid_count else 0
                
                f.write(f"\n【统计摘要】\n")
                f.write(f"总测试URL数: {total_tested}\n")
                f.write(f"测试成功数: {success_count} ({success_count/total_tested*100:.1f}%)\n")
                f.write(f"有效频道数: {valid_count} ({valid_count/total_tested*100:.1f}%)\n")
                f.write(f"有效频道平均延迟: {avg_latency:.2f}ms\n\n")
                
                # 按分组展示详细信息
                f.write("【详细列表】\n")
                f.write("-"*60 + "\n")
                grouped_sources: Dict[str, List[Tuple[str, str, str]]] = {}
                for group, name, url in live_sources:
                    if group not in grouped_sources:
                        grouped_sources[group] = []
                    grouped_sources[group].append((name, url))
                
                for group in sorted(grouped_sources.keys()):
                    f.write(f"\n★ 分组: {group} | 频道数: {len(grouped_sources[group])}\n")
                    for name, url in grouped_sources[group]:
                        r = url_to_result[url]
                        f.write(f"  ▶ 名称: {name}\n")
                        f.write(f"     URL: {url}\n")
                        f.write(f"     延迟: {r.latency:.2f}ms | 分辨率: {r.resolution} | 尝试次数: {r.attempt_times}\n\n")
            
            logger.info(f"详细报告生成成功 | 路径: {report_path.absolute()}")
        except Exception as e:
            logger.error(f"生成报告失败: {e}", exc_info=True)
    
    @staticmethod
    def generate_json_report(results: List[SpeedTestResult], json_path: str | Path) -> None:
        """生成JSON格式报告（便于后续处理）"""
        json_path = Path(json_path)
        try:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            # 转换为字典并序列化
            report_data = {
                "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "config": {
                    "concurrent_limit": config.CONCURRENT_LIMIT,
                    "timeout": config.TIMEOUT,
                    "latency_threshold": config.LATENCY_THRESHOLD
                },
                "statistics": {
                    "total": len(results),
                    "success": sum(1 for r in results if r.success),
                    "valid": sum(1 for r in results if r.is_valid())
                },
                "results": [r.to_dict() for r in results]
            }
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            logger.info(f"JSON报告生成成功 | 路径: {json_path.absolute()}")
        except Exception as e:
            logger.error(f"生成JSON报告失败: {e}", exc_info=True)

# ===================== 主程序（优化：结构清晰/配置加载/容错） =====================
async def main():
    # 1. 加载自定义配置（可选）
    config.load_from_file()
    
    # 2. 配置输入输出路径
    input_file = config.BASE_DIR / "self_use" / "output" / "live_ipv4.m3u"
    timestamp = time.strftime("%Y%m%d_%H%M%S")  # 时间戳避免文件覆盖
    output_m3u = config.OUTPUT_DIR / f"live_sources_ipv4_{timestamp}.m3u"
    report_file = config.REPORT_DIR / f"speed_test_report_{timestamp}.txt"
    json_report_file = config.REPORT_DIR / f"speed_test_report_{timestamp}.json"
    
    # 3. 解析M3U文件
    logger.info(f"开始解析M3U文件 | 路径: {input_file}")
    m3u_processor = M3UProcessor()
    live_sources = m3u_processor.parse_m3u(input_file)
    
    if not live_sources:
        logger.error("未解析到有效直播源，程序退出")
        return
    
    # 4. 批量测速
    logger.info("开始执行批量测速...")
    async with SpeedTester() as tester:
        urls = [src[2] for src in live_sources]
        results = await tester.batch_speed_test(urls)
    
    # 5. 构建URL到结果的映射
    url_to_result = {res.url: res for res in results}
    
    # 6. 筛选并排序有效直播源
    # 排序规则：分组升序 → 频道名升序 → 延迟升序
    valid_live_sources = sorted(
        [src for src in live_sources if url_to_result[src[2]].is_valid()],
        key=lambda x: (
            x[0].lower(),  # 分组名（小写避免大小写影响）
            x[1].lower(),  # 频道名（小写）
            url_to_result[x[2]].latency or float("inf")  # 延迟升序
        )
    )
    
    # 7. 输出前10个结果（验证排序）
    logger.info("前10个有效直播源（分组→名称→延迟）:")
    for i, (group, name, url) in enumerate(valid_live_sources[:10], 1):
        r = url_to_result[url]
        logger.info(f"{i}. [{group}] {name} | 延迟: {r.latency}ms | 分辨率: {r.resolution}")
    
    # 8. 生成M3U文件和报告
    m3u_processor.generate_m3u(valid_live_sources, output_m3u, url_to_result)
    ReportGenerator.generate_detailed_report(valid_live_sources, url_to_result, report_file)
    ReportGenerator.generate_json_report(results, json_report_file)
    
    logger.info("程序执行完成！")

# ===================== 入口函数（优化：兼容Windows事件循环） =====================
def run_main():
    """兼容不同系统的事件循环"""
    try:
        # 优先使用asyncio.run（Python 3.7+）
        asyncio.run(main())
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            # Jupyter/IPython环境兼容
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main())
        else:
            # Windows系统兼容
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            asyncio.run(main())
    except Exception as e:
        logger.critical(f"程序执行失败: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    run_main()
