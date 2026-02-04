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
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")  # 输出文件夹绝对路径
LOG_FILE = os.path.join(OUTPUT_DIR, "function.log")  # 日志文件绝对路径
TEMPLATE_FILE = os.path.join(PROJECT_DIR, "demo.txt")  # 模板文件绝对路径

# 特殊优先级URL前缀（最优先排列）
SPECIAL_WEBVIEW_PREFIX = "webview://https://yangshipin.cn"

# 确保必要文件夹存在
def init_folders():
    """初始化项目所需文件夹（output）"""
    for folder in [OUTPUT_DIR]:
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

def parse_template(template_file):
    """解析同级目录下的模板文件，提取频道分类和频道名称（保留顺序）"""
    template_channels = OrderedDict()
    current_category = None

    try:
        with open(template_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释行（#开头）
                if line and not line.startswith("#"):
                    if "#genre#" in line:
                        # 提取分类名称（逗号前的内容）
                        current_category = line.split(",")[0].strip()
                        template_channels[current_category] = []
                    elif current_category:
                        # 提取频道名称并加入当前分类
                        channel_name = line.split(",")[0].strip()
                        template_channels[current_category].append(channel_name)
        logging.info(f"模板文件 {template_file} 解析成功，包含 {len(template_channels)} 个分类")
    except FileNotFoundError:
        logging.error(f"模板文件 {template_file} 未找到，请确认文件在同级目录下")
        raise
    return template_channels

def clean_channel_name(channel_name):
    """数据清洗：去除特殊字符、空白、数字前导零，转为大写（仅处理CCTV频道）"""
    if not channel_name:
        return ""
    # 去除指定特殊字符（$、「、」、-）
    cleaned_name = re.sub(r'[$「」-]', '', channel_name)
    # 去除所有空白字符（空格、制表符等）
    cleaned_name = re.sub(r'\s+', '', cleaned_name)
    # 数字转整数，去除前导零（如 CCTV001 → CCTV1）
    cleaned_name = re.sub(r'(\D*)(\d+)', lambda m: m.group(1) + str(int(m.group(2))), cleaned_name)
    # 转为大写，保证匹配一致性
    return cleaned_name.upper()

def fetch_channels(url):
    """从指定URL抓取频道列表，自动判断M3U/TXT格式，返回有序频道字典"""
    channels = OrderedDict()

    try:
        # 发送网络请求，设置超时时间避免卡死
        response = requests.get(url, timeout=15)
        response.raise_for_status()  # 捕获HTTP状态码错误（4xx/5xx）
        response.encoding = 'utf-8'  # 强制指定UTF-8编码，避免中文乱码
        lines = response.text.split("\n")

        # 判断文件格式（前15行包含#EXTINF即为M3U格式）
        is_m3u = any(line.startswith("#EXTINF") for line in lines[:15])
        source_type = "m3u" if is_m3u else "txt"
        logging.info(f"URL: {url} 抓取成功，判断为 {source_type} 格式")

        # 调用对应格式解析函数
        if is_m3u:
            channels.update(parse_m3u_lines(lines))
        else:
            channels.update(parse_txt_lines(lines))

        # 记录抓取到的分类信息
        if channels:
            categories = ", ".join(channels.keys())
            logging.info(f"URL: {url} 解析成功，包含分类：{categories}")
    except requests.RequestException as e:
        logging.error(f"URL: {url} 抓取失败 ❌，错误信息：{e}")
    return channels

def parse_m3u_lines(lines):
    """解析M3U格式内容，提取分类、CCTV频道名称和对应URL"""
    channels = OrderedDict()
    current_category = None
    channel_name = None  # 初始化，避免变量未定义报错

    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF"):
            # 匹配M3U格式中的分类和频道名称
            match = re.search(r'group-title="(.*?)",(.*)', line)
            if match:
                current_category = match.group(1).strip()
                channel_name = match.group(2).strip()

                # 仅处理CCTV开头的频道，进行数据清洗
                if channel_name and channel_name.startswith("CCTV"):
                    channel_name = clean_channel_name(channel_name)

                # 初始化分类对应的频道列表
                if current_category not in channels:
                    channels[current_category] = []
            else:
                channel_name = None  # 匹配失败时重置，避免无效数据
        elif line and not line.startswith("#"):
            # 提取频道URL，仅在分类和频道名称有效时保存
            channel_url = line.strip()
            if current_category and channel_name and channel_url:
                channels[current_category].append((channel_name, channel_url))
    return channels

def parse_txt_lines(lines):
    """解析TXT格式内容，提取分类、CCTV频道名称和对应URL（支持#分割多URL）"""
    channels = OrderedDict()
    current_category = None

    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            if "#genre#" in line:
                # 提取分类名称
                current_category = line.split(",")[0].strip()
                channels[current_category] = []
            elif current_category:
                # 匹配 频道名称,URL 格式
                match = re.match(r"^(.*?),(.*?)$", line)
                if match:
                    channel_name = match.group(1).strip()
                    channel_url_str = match.group(2).strip()

                    # 仅处理CCTV开头的频道，进行数据清洗
                    if channel_name and channel_name.startswith("CCTV"):
                        channel_name = clean_channel_name(channel_name)

                    # 分割#分隔的多个URL，逐个保存
                    for channel_url in channel_url_str.split('#'):
                        channel_url = channel_url.strip()
                        if channel_url:  # 跳过空URL
                            channels[current_category].append((channel_name, channel_url))
                elif line:
                    # 无URL的情况，保存空URL占位
                    channels[current_category].append((line, ''))
    return channels

def find_similar_name(target_name, name_list):
    """使用模糊匹配，查找最相似的频道名称（相似度阈值0.6）"""
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=0.6)
    return matches[0] if matches else None

def match_channels(template_channels, all_channels):
    """将模板频道与抓取到的频道进行匹配，返回匹配结果"""
    matched_channels = OrderedDict()

    # 收集所有抓取到的频道名称（去重，提升匹配效率）
    all_online_channel_names = []
    for online_channel_list in all_channels.values():
        for online_channel_name, _ in online_channel_list:
            if online_channel_name and online_channel_name not in all_online_channel_names:
                all_online_channel_names.append(online_channel_name)

    # 按模板分类进行匹配
    for category, channel_list in template_channels.items():
        matched_channels[category] = OrderedDict()
        for channel_name in channel_list:
            # 查找相似频道名称
            similar_name = find_similar_name(channel_name, all_online_channel_names)
            if similar_name:
                # 收集该相似频道对应的所有URL
                for online_channel_list in all_channels.values():
                    for online_name, online_url in online_channel_list:
                        if online_name == similar_name and online_url:
                            matched_channels[category].setdefault(channel_name, []).append(online_url)

    logging.info(f"频道匹配完成，模板中有效匹配频道 {len([c for cl in matched_channels.values() for c in cl])} 个")
    return matched_channels

def filter_source_urls(template_file):
    """整合所有步骤：解析模板、抓取所有源、合并、匹配，返回最终结果"""
    # 解析模板
    template_channels = parse_template(template_file)
    if not template_channels:
        logging.warning("模板文件解析结果为空，无后续操作")
        return OrderedDict(), template_channels

    # 抓取所有配置的源URL并合并结果
    all_channels = OrderedDict()
    for url in config.source_urls:
        fetched_channels = fetch_channels(url)
        merge_channels(all_channels, fetched_channels)

    # 频道匹配
    matched_channels = match_channels(template_channels, all_channels)
    return matched_channels, template_channels

def merge_channels(target, source):
    """合并两个频道字典，保留原有顺序，补充新分类和频道"""
    for category, channel_list in source.items():
        if category in target:
            target[category].extend(channel_list)
        else:
            target[category] = channel_list

def is_ipv6(url):
    """判断URL是否为IPv6格式（匹配 http://[xxxx:xxxx:...]/ 格式）"""
    return re.match(r'^http:\/\/\[[0-9a-fA-F:]+\]', url) is not None

def is_special_webview(url):
    """判断URL是否为特殊优先级webview（webview://https://yangshipin.cn开头）"""
    return url.startswith(SPECIAL_WEBVIEW_PREFIX)

def is_webview(url):
    """判断URL是否为普通webview协议（排除特殊优先级后）"""
    return url.startswith("webview://") and not is_special_webview(url)

def sort_and_filter_urls(urls, written_urls):
    """URL排序与过滤：特殊webview→普通webview→HTTP → IP版本优先级 → 去重 → 黑名单"""
    if not urls:
        return []

    # 1. 基础过滤：非空、未写入、不在黑名单
    valid_urls = [
        url for url in urls
        if url and url not in written_urls and not any(blk in url for blk in config.url_blacklist)
    ]

    # 2. 三级排序逻辑
    def sort_key(url):
        # 第一级：特殊webview（0）→ 普通webview（1）→ HTTP（2）
        if is_special_webview(url):
            protocol_priority = 0
        elif is_webview(url):
            protocol_priority = 1
        else:
            protocol_priority = 2
        
        # 第二级：IP版本优先级（根据配置排序）
        if config.ip_version_priority == "ipv6":
            ip_priority = 0 if is_ipv6(url) else 1
        else:
            ip_priority = 1 if is_ipv6(url) else 0
        
        # 组合排序键（先按协议层级，再按IP版本）
        return (protocol_priority, ip_priority)

    # 按排序键排序，确保特殊webview排在最前
    sorted_urls = sorted(valid_urls, key=sort_key)

    # 3. 更新已写入URL集合，避免重复
    written_urls.update(sorted_urls)
    return sorted_urls

def write_to_files(f_m3u, f_txt, category, channel_name, index, url):
    """统一写入M3U和TXT文件，填充标准字段和频道logo"""
    # 频道logo链接（适配GitHub公开图库）
    channel_logo = f"https://raw.githubusercontent.com/fanmingming/live/main/tv/{channel_name}.png"

    # 写入M3U格式（标准EXTINF字段）
    f_m3u.write(
        f"#EXTINF:-1 tvg-id=\"{index}\" tvg-name=\"{channel_name}\" tvg-logo=\"{channel_logo}\" group-title=\"{category}\",{channel_name}\n"
    )
    f_m3u.write(f"{url}\n")

    # 写入TXT格式（频道名称,URL）
    f_txt.write(f"{channel_name},{url}\n")

def updateChannelUrlsM3U(channels, template_channels):
    """生成最终的IPv4/IPv6版本M3U和TXT文件，保存到output文件夹"""
    # 初始化已写入URL集合，避免跨频道重复
    written_urls_ipv4 = set()
    written_urls_ipv6 = set()

    # 填充公告信息中的当前日期
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    for group in config.announcements:
        for entry in group['entries']:
            if entry['name'] is None:
                entry['name'] = current_date

    # 定义输出文件路径（使用全局常量OUTPUT_DIR）
    file_paths = {
        "ipv4_m3u": os.path.join(OUTPUT_DIR, "live_ipv4_source.m3u"),
        "ipv4_txt": os.path.join(OUTPUT_DIR, "live_ipv4_source.txt"),
        "ipv6_m3u": os.path.join(OUTPUT_DIR, "live_ipv6_source.m3u"),
        "ipv6_txt": os.path.join(OUTPUT_DIR, "live_ipv6_source.txt")
    }

    # 同时打开4个输出文件，批量写入
    try:
        with open(file_paths["ipv4_m3u"], "w", encoding="utf-8") as f_m3u4, \
             open(file_paths["ipv4_txt"], "w", encoding="utf-8") as f_txt4, \
             open(file_paths["ipv6_m3u"], "w", encoding="utf-8") as f_m3u6, \
             open(file_paths["ipv6_txt"], "w", encoding="utf-8") as f_txt6:

            # 写入M3U文件头部（包含EPG地址）
            epg_str = ",".join(f'"{epg}"' for epg in config.epg_urls)
            f_m3u4.write(f"#EXTM3U x-tvg-url={epg_str}\n")
            f_m3u6.write(f"#EXTM3U x-tvg-url={epg_str}\n")

            # 写入公告信息
            for group in config.announcements:
                category_name = group['channel']
                # 写入TXT文件的分类标记
                f_txt4.write(f"{category_name},#genre#\n")
                f_txt6.write(f"{category_name},#genre#\n")

                for entry in group['entries']:
                    entry_url = entry['url']
                    entry_name = entry['name']
                    entry_logo = entry['logo']

                    # 区分IPv4/IPv6，分别写入对应文件
                    if is_ipv6(entry_url) and entry_url not in written_urls_ipv6:
                        written_urls_ipv6.add(entry_url)
                        f_m3u6.write(
                            f"#EXTINF:-1 tvg-id=\"1\" tvg-name=\"{entry_name}\" tvg-logo=\"{entry_logo}\" group-title=\"{category_name}\",{entry_name}\n"
                        )
                        f_m3u6.write(f"{entry_url}\n")
                        f_txt6.write(f"{entry_name},{entry_url}\n")
                    elif not is_ipv6(entry_url) and entry_url not in written_urls_ipv4:
                        written_urls_ipv4.add(entry_url)
                        f_m3u4.write(
                            f"#EXTINF:-1 tvg-id=\"1\" tvg-name=\"{entry_name}\" tvg-logo=\"{entry_logo}\" group-title=\"{category_name}\",{entry_name}\n"
                        )
                        f_m3u4.write(f"{entry_url}\n")
                        f_txt4.write(f"{entry_name},{entry_url}\n")

            # 写入匹配到的频道数据
            for category, channel_list in template_channels.items():
                # 写入TXT文件的分类标记
                f_txt4.write(f"{category},#genre#\n")
                f_txt6.write(f"{category},#genre#\n")

                if category not in channels:
                    continue

                # 遍历模板中的每个频道
                for channel_name in channel_list:
                    if channel_name not in channels[category]:
                        continue

                    # 提取该频道的所有URL，先去重
                    all_urls = list(set(channels[category][channel_name]))

                    # 按IPv4/IPv6分别过滤排序（已包含三级协议优先级）
                    ipv4_urls = sort_and_filter_urls([u for u in all_urls if not is_ipv6(u)], written_urls_ipv4)
                    ipv6_urls = sort_and_filter_urls([u for u in all_urls if is_ipv6(u)], written_urls_ipv6)

                    # 写入IPv4文件（特殊webview→普通webview→HTTP）
                    for idx, url in enumerate(ipv4_urls, start=1):
                        write_to_files(f_m3u4, f_txt4, category, channel_name, idx, url)

                    # 写入IPv6文件（特殊webview→普通webview→HTTP）
                    for idx, url in enumerate(ipv6_urls, start=1):
                        write_to_files(f_m3u6, f_txt6, category, channel_name, idx, url)

            # 写入文件末尾空行，优化格式
            f_txt4.write("\n")
            f_txt6.write("\n")

        logging.info(f"所有输出文件生成完成，保存路径：{OUTPUT_DIR}")
        logging.info("URL排列顺序：webview://https://yangshipin.cn → 其他webview → HTTP（按IP版本优先级排序）")
    except IOError as e:
        logging.error(f"文件写入失败 ❌，错误信息：{e}")
        raise

if __name__ == "__main__":
    try:
        # 第一步：初始化日志和文件夹
        init_logging()
        
        # 第二步：执行核心流程：过滤源URL + 生成输出文件
        matched_channels, template_channels = filter_source_urls(TEMPLATE_FILE)
        updateChannelUrlsM3U(matched_channels, template_channels)
        
        logging.info("程序运行完成 ✅")
    except Exception as e:
        logging.error(f"程序运行异常终止 ❌，错误信息：{e}")