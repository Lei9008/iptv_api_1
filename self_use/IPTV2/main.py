import re
import requests
import logging
from collections import OrderedDict
from datetime import datetime
import config
import os
import difflib

# ---------------------- 全局配置与初始化 ----------------------
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))  # 项目根目录（当前文件所在目录）
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
# PIC_DIR = os.path.join(PROJECT_DIR, "pic")
LOG_FILE = os.path.join(OUTPUT_DIR, "function.log")
TEMPLATE_FILE = os.path.join(PROJECT_DIR, "demo.txt")

# 确保必要文件夹存在
def init_folders():
    """初始化项目所需文件夹（output、pic）"""
    for folder in [OUTPUT_DIR]:   # , PIC_DIR
        if not os.path.exists(folder):
            os.makedirs(folder)
            logging.info(f"创建文件夹成功：{folder}")

# 配置日志系统
def init_logging():
    """初始化日志配置，同时输出到控制台和日志文件"""
    init_folders()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',  # 补充日期时间格式，更易读
        handlers=[
            logging.FileHandler(LOG_FILE, "a", encoding="utf-8"),  # 改为追加模式，保留历史日志
            logging.StreamHandler()
        ]
    )

# ---------------------- 数据清洗与辅助函数 ----------------------
def clean_channel_name(channel_name):
    """
    清洗频道名称，统一格式便于后续匹配
    :param channel_name: 原始频道名称
    :return: 清洗后的标准化频道名称
    """
    if not isinstance(channel_name, str):
        return ""
    
    # 移除指定特殊字符
    cleaned_name = re.sub(r'[$「」\[\]<>-]', '', channel_name)
    # 移除所有空白字符（空格、制表符等）
    cleaned_name = re.sub(r'\s+', '', cleaned_name)
    # 去除数字前导零（如 CCTV01 -> CCTV1）
    cleaned_name = re.sub(r'(\D*)(\d+)', lambda m: m.group(1) + str(int(m.group(2))), cleaned_name)
    # 转换为大写，统一格式
    return cleaned_name.upper()

def is_ipv6(url):
    """
    判断URL是否为IPv6格式
    :param url: 待判断的URL
    :return: True（IPv6）/ False（非IPv6）
    """
    if not isinstance(url, str):
        return False
    return re.match(r'^http:\/\/\[[0-9a-fA-F:]+\]', url) is not None

def find_similar_name(target_name, name_list):
    """
    模糊匹配最相似的频道名称
    :param target_name: 模板中的目标频道名
    :param name_list: 在线抓取的频道名列表
    :return: 最相似的频道名（无匹配返回None）
    """
    if not target_name or not name_list:
        return None
    
    # 提升匹配阈值至0.7，减少无效匹配
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=0.7)
    return matches[0] if matches else None

# ---------------------- 模板与数据源解析 ----------------------
def parse_template():
    """
    解析本地demo.txt模板文件，提取频道分类与频道名
    :return: 有序字典 {分类名: [频道名1, 频道名2, ...]}
    """
    template_channels = OrderedDict()
    current_category = None

    # 检查模板文件是否存在
    if not os.path.exists(TEMPLATE_FILE):
        logging.error(f"模板文件不存在：{TEMPLATE_FILE}，无法继续执行")
        return template_channels

    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                # 忽略空行和注释行
                if not line or line.startswith("#"):
                    continue
                
                # 匹配分类行（格式：分类名,#genre#）
                if "#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    if current_category not in template_channels:
                        template_channels[current_category] = []
                        logging.debug(f"解析到分类（第{line_num}行）：{current_category}")
                # 匹配分类下的频道行
                elif current_category:
                    channel_name = clean_channel_name(line.split(",")[0].strip())
                    if channel_name:
                        template_channels[current_category].append(channel_name)
                    else:
                        logging.debug(f"第{line_num}行频道名清洗后为空，忽略")
        logging.info(f"模板文件解析成功，共提取 {len(template_channels)} 个分类")
    except Exception as e:
        logging.error(f"模板文件解析失败：{e}")

    return template_channels

def fetch_channels(url):
    """
    从指定URL抓取直播源，自动识别M3U/TXT格式并解析
    :param url: 直播源数据源URL
    :return: 有序字典 {分类名: [(频道名, 频道URL), ...]}
    """
    channels = OrderedDict()
    if not url:
        logging.warning("传入的URL为空，跳过抓取")
        return channels

    try:
        # 发送GET请求，添加超时设置（避免无限等待）
        response = requests.get(url, timeout=30)
        response.raise_for_status()  # 抛出HTTP错误（4xx/5xx）
        response.encoding = 'utf-8'
        lines = response.text.split("\n")

        # 自动判断文件格式
        is_m3u = any(line.strip().startswith("#EXTINF") for line in lines[:15])
        source_type = "m3u" if is_m3u else "txt"
        logging.info(f"开始解析URL：{url}，格式判定为：{source_type}")

        # 调用对应格式解析函数
        if is_m3u:
            channels = parse_m3u_lines(lines)
        else:
            channels = parse_txt_lines(lines)

        # 输出解析结果
        if channels:
            categories = ", ".join(channels.keys())
            logging.info(f"URL解析成功：{url}，包含 {len(channels)} 个分类，分类列表：{categories}")
        else:
            logging.warning(f"URL解析完成：{url}，未提取到有效频道数据")

    except requests.RequestException as e:
        logging.error(f"URL抓取失败：{url}，错误信息：{e}")
    except Exception as e:
        logging.error(f"URL解析异常：{url}，错误信息：{e}")

    return channels

def parse_m3u_lines(lines):
    """解析M3U格式的直播源数据"""
    channels = OrderedDict()
    current_category = None
    channel_name = None

    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF"):
            # 提取M3U格式中的分类和频道名
            match = re.search(r'group-title="(.*?)",(.*)', line)
            if match:
                current_category = match.group(1).strip()
                channel_name = clean_channel_name(match.group(2).strip())

                # 仅保留CCTV开头的频道
                if channel_name and channel_name.startswith("CCTV"):
                    if current_category not in channels:
                        channels[current_category] = []
                else:
                    channel_name = None
            else:
                channel_name = None
        elif line and not line.startswith("#"):
            channel_url = line.strip()
            if current_category and channel_name and channel_url:
                channels[current_category].append((channel_name, channel_url))

    return channels

def parse_txt_lines(lines):
    """解析TXT格式的直播源数据"""
    channels = OrderedDict()
    current_category = None

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if "#genre#" in line:
            current_category = line.split(",")[0].strip()
            if current_category not in channels:
                channels[current_category] = []
        elif current_category:
            match = re.match(r"^(.*?),(.*?)$", line)
            if match:
                channel_name = clean_channel_name(match.group(1).strip())
                # 仅保留CCTV开头的频道
                if not (channel_name and channel_name.startswith("CCTV")):
                    continue

                # 解析多URL（用#分隔）
                channel_urls = [u.strip() for u in match.group(2).strip().split('#') if u.strip()]
                for channel_url in channel_urls:
                    channels[current_category].append((channel_name, channel_url))

    return channels

# ---------------------- 数据合并与匹配 ----------------------
def merge_channels(target, source):
    """
    合并多个数据源的频道数据，避免分类覆盖
    :param target: 目标有序字典（用于存储合并结果）
    :param source: 待合并的有序字典（新抓取的数据源）
    """
    if not isinstance(target, OrderedDict) or not isinstance(source, OrderedDict):
        return

    for category, channel_list in source.items():
        if category in target:
            target[category].extend(channel_list)
        else:
            target[category] = channel_list

def match_channels(template_channels, all_channels):
    """
    将模板频道与抓取到的在线频道进行模糊匹配
    :param template_channels: 解析后的模板数据
    :param all_channels: 合并后的所有在线数据源
    :return: 有序字典 {分类名: {频道名: [URL1, URL2, ...]}}
    """
    matched_channels = OrderedDict()
    if not template_channels or not all_channels:
        logging.warning("模板数据或在线数据源为空，无法进行频道匹配")
        return matched_channels

    # 提取所有在线频道名，用于模糊匹配
    all_online_channel_names = []
    for online_channel_list in all_channels.values():
        for channel_name, _ in online_channel_list:
            if channel_name not in all_online_channel_names:
                all_online_channel_names.append(channel_name)

    # 遍历模板，进行频道匹配
    for category, template_channel_list in template_channels.items():
        matched_channels[category] = OrderedDict()
        for target_channel in template_channel_list:
            # 查找最相似的在线频道名
            similar_channel = find_similar_name(target_channel, all_online_channel_names)
            if not similar_channel:
                logging.debug(f"未找到与 {target_channel} 匹配的在线频道")
                continue

            # 提取该相似频道对应的所有URL
            channel_urls = []
            for online_channel_list in all_channels.values():
                for channel_name, channel_url in online_channel_list:
                    if channel_name == similar_channel and channel_url not in channel_urls:
                        channel_urls.append(channel_url)

            if channel_urls:
                matched_channels[category][target_channel] = channel_urls
                logging.debug(f"频道 {target_channel} 匹配成功，获取到 {len(channel_urls)} 个有效URL")

    logging.info(f"频道匹配完成，共匹配到 {len(matched_channels)} 个分类的有效频道")
    return matched_channels

# ---------------------- 数据过滤与文件生成 ----------------------
def sort_and_filter_urls(urls, written_urls):
    """
    对URL进行排序、去重、黑名单过滤
    :param urls: 原始URL列表
    :param written_urls: 已写入文件的URL集合（用于去重）
    :return: 处理后的有效URL列表
    """
    if not urls:
        return []

    # 1. 基础过滤：非空、未写入、不在黑名单
    filtered_urls = [
        url for url in urls
        if url and url not in written_urls and not any(
            blacklist in url for blacklist in config.url_blacklist
        )
    ]

    # 2. 按IP版本优先级排序
    if config.ip_version_priority == "ipv6":
        # 优先IPv6，再IPv4
        filtered_urls.sort(key=lambda u: not is_ipv6(u))
    else:
        # 优先IPv4，再IPv6（默认）
        filtered_urls.sort(key=lambda u: is_ipv6(u))

    # 3. 更新已写入URL集合，避免重复
    written_urls.update(filtered_urls)
    return filtered_urls

def write_to_files(f_m3u, f_txt, category, channel_name, index, url):
    """
    统一将频道数据写入M3U和TXT文件
    :param f_m3u: M3U文件句柄
    :param f_txt: TXT文件句柄
    :param category: 频道分类
    :param channel_name: 频道名称
    :param index: 线路序号
    :param url: 频道原始URL
    """
    # 构造logo路径（本地pic文件夹）
    logo_url = f"https://raw.githubusercontent.com/fanmingming/live/main/tv/{channel_name}.png"
    # 写入M3U文件（符合M3U格式规范）
    f_m3u.write(f"#EXTINF:-1 tvg-id=\"{index}\" tvg-name=\"{channel_name}\" tvg-logo=\"{logo_url}\" group-title=\"{category}\",{channel_name}\n")
    f_m3u.write(f"{url}\n")
    # 写入TXT文件
    f_txt.write(f"{channel_name},{url}\n")

def generate_live_files(matched_channels, template_channels):
    """
    生成最终的IPv4/IPv6 M3U和TXT文件
    :param matched_channels: 匹配后的频道数据
    :param template_channels: 模板频道数据
    """
    if not matched_channels or not template_channels:
        logging.warning("无有效匹配数据，无法生成直播源文件")
        return

    # 定义输出文件路径
    file_paths = {
        "ipv4_m3u": os.path.join(OUTPUT_DIR, "live_ipv4_source.m3u"),
        "ipv4_txt": os.path.join(OUTPUT_DIR, "live_ipv4_source.txt"),
        "ipv6_m3u": os.path.join(OUTPUT_DIR, "live_ipv6_source.m3u"),
        "ipv6_txt": os.path.join(OUTPUT_DIR, "live_ipv6_source.txt")
    }

    # 初始化已写入URL集合（去重）
    written_urls_ipv4 = set()
    written_urls_ipv6 = set()

    # 处理公告日期
    current_date = datetime.now().strftime("%Y-%m-%d")
    for group in config.announcements:
        for entry in group.get("entries", []):
            if entry.get("name") is None:
                entry["name"] = current_date

    try:
        # 打开所有输出文件
        with open(file_paths["ipv4_m3u"], "w", encoding="utf-8") as f_m3u4, \
             open(file_paths["ipv4_txt"], "w", encoding="utf-8") as f_txt4, \
             open(file_paths["ipv6_m3u"], "w", encoding="utf-8") as f_m3u6, \
             open(file_paths["ipv6_txt"], "w", encoding="utf-8") as f_txt6:

            # 写入M3U文件头部（EPG配置）
            epg_str = ",".join(f'"{epg}"' for epg in config.epg_urls)
            m3u_header = f"#EXTM3U x-tvg-url={epg_str}\n" if epg_str else "#EXTM3U\n"
            f_m3u4.write(m3u_header)
            f_m3u6.write(m3u_header)

            # 写入公告内容
            for group in config.announcements:
                category = group.get("channel", "公告")
                f_txt4.write(f"{category},#genre#\n")
                f_txt6.write(f"{category},#genre#\n")

                for entry in group.get("entries", []):
                    name = entry.get("name", "公告")
                    url = entry.get("url", "")
                    logo = entry.get("logo", "")

                    if not url:
                        continue

                    # 分IPv4/IPv6写入
                    if is_ipv6(url):
                        if url not in written_urls_ipv6:
                            written_urls_ipv6.add(url)
                            f_m3u6.write(f"#EXTINF:-1 tvg-id=\"1\" tvg-name=\"{name}\" tvg-logo=\"{logo}\" group-title=\"{category}\",{name}\n")
                            f_m3u6.write(f"{url}\n")
                            f_txt6.write(f"{name},{url}\n")
                    else:
                        if url not in written_urls_ipv4:
                            written_urls_ipv4.add(url)
                            f_m3u4.write(f"#EXTINF:-1 tvg-id=\"1\" tvg-name=\"{name}\" tvg-logo=\"{logo}\" group-title=\"{category}\",{name}\n")
                            f_m3u4.write(f"{url}\n")
                            f_txt4.write(f"{name},{url}\n")

            # 写入匹配后的CCTV频道数据
            for category, channel_list in template_channels.items():
                f_txt4.write(f"{category},#genre#\n")
                f_txt6.write(f"{category},#genre#\n")

                if category not in matched_channels:
                    continue

                for channel_name in channel_list:
                    channel_urls = matched_channels[category].get(channel_name, [])
                    if not channel_urls:
                        continue

                    # 过滤并排序IPv4/IPv6 URL
                    ipv4_urls = sort_and_filter_urls([u for u in channel_urls if not is_ipv6(u)], written_urls_ipv4)
                    ipv6_urls = sort_and_filter_urls([u for u in channel_urls if is_ipv6(u)], written_urls_ipv6)

                    # 写入IPv4数据
                    for idx, url in enumerate(ipv4_urls, start=1):
                        write_to_files(f_m3u4, f_txt4, category, channel_name, idx, url)

                    # 写入IPv6数据
                    for idx, url in enumerate(ipv6_urls, start=1):
                        write_to_files(f_m3u6, f_txt6, category, channel_name, idx, url)

        logging.info(f"直播源文件生成成功，文件存放路径：{OUTPUT_DIR}")
        logging.info(f"生成文件列表：{', '.join(os.path.basename(p) for p in file_paths.values())}")

    except Exception as e:
        logging.error(f"直播源文件生成失败：{e}")

# ---------------------- 主执行函数 ----------------------
def main():
    """主执行流程：初始化 -> 解析 -> 抓取 -> 匹配 -> 生成文件"""
    # 1. 初始化日志和文件夹
    init_logging()
    logging.info("=" * 50 + " 开始执行直播源整理程序 " + "=" * 50)

    # 2. 解析本地模板
    template_channels = parse_template()
    if not template_channels:
        logging.error("无有效模板数据，程序终止")
        return

    # 3. 抓取并合并所有在线数据源
    all_channels = OrderedDict()
    for url in config.source_urls:
        fetched_channels = fetch_channels(url)
        merge_channels(all_channels, fetched_channels)

    if not all_channels:
        logging.warning("未抓取到任何有效在线数据源，仅生成公告内容（如有）")

    # 4. 频道模糊匹配
    matched_channels = match_channels(template_channels, all_channels)

    # 5. 生成最终直播源文件
    generate_live_files(matched_channels, template_channels)

    logging.info("=" * 50 + " 直播源整理程序执行完毕 " + "=" * 50)

if __name__ == "__main__":
    main()
