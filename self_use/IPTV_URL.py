# main.py
import re
import requests
import difflib
from urllib.parse import unquote, urlparse, urlunparse
import config

# 模拟浏览器请求头，避免被反爬
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/plain, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
}

class M3UMerger:
    def __init__(self):
        self.similarity_threshold = config.SIMILARITY_THRESHOLD
        # 核心存储：key=标准化后的URL，value=整合后的频道信息
        self.channel_dict = {}

    def _replace_github_domain(self, url, new_domain):
        """替换GitHub RAW链接的域名"""
        parsed = urlparse(url)
        if parsed.netloc in config.GITHUB_MIRRORS:
            new_parsed = parsed._replace(netloc=new_domain)
            return urlunparse(new_parsed)
        return url

    def _add_github_proxy(self, url, proxy_prefix):
        """给GitHub RAW链接添加代理前缀"""
        parsed = urlparse(url)
        if parsed.netloc in config.GITHUB_MIRRORS:
            return proxy_prefix + url
        return url

    def download_m3u(self, original_url):
        """
        下载M3U内容，支持GitHub镜像/代理自动重试
        :param original_url: 原始直播源URL
        :return: M3U内容字符串 | None
        """
        # 构建待尝试的URL列表
        urls_to_try = [original_url]
        
        # 1. 生成镜像域名的URL（如果是GitHub RAW链接）
        if any(mirror in original_url for mirror in config.GITHUB_MIRRORS):
            for mirror in config.GITHUB_MIRRORS[1:]:  # 跳过第一个（原始域名）
                urls_to_try.append(self._replace_github_domain(original_url, mirror))
        
        # 2. 生成带代理前缀的URL
        for proxy in config.PROXY_PREFIXES:
            urls_to_try.append(self._add_github_proxy(original_url, proxy))
        
        # 去重（避免重复尝试相同URL）
        urls_to_try = list(dict.fromkeys(urls_to_try))
        
        # 依次尝试每个URL
        for idx, url in enumerate(urls_to_try):
            try:
                resp = requests.get(
                    url, 
                    headers=HEADERS, 
                    timeout=config.REQUEST_TIMEOUT,
                    allow_redirects=True  # 允许重定向
                )
                resp.raise_for_status()  # 抛出HTTP错误（4xx/5xx）
                # 自动识别编码，避免乱码
                resp.encoding = resp.apparent_encoding if not resp.encoding else resp.encoding
                content = resp.text
                
                # 检测是否为M3U内容
                if "#EXTINF" not in content and "#EXTM3U" not in content:
                    if idx < len(urls_to_try)-1:
                        print(f"⚠️ {url} 下载的内容非M3U格式，尝试下一个链接...")
                        continue
                    else:
                        print(f"❌ 所有链接均未下载到有效M3U内容：{original_url}")
                        return None
                
                print(f"✅ 成功下载（尝试{idx+1}次）：{url}")
                return content
            except requests.exceptions.RequestException as e:
                if idx < len(urls_to_try)-1:
                    print(f"⚠️ 下载失败（尝试{idx+1}次）{url}: {str(e)[:30]}，重试下一个...")
                else:
                    print(f"❌ 所有链接均下载失败：{original_url}，错误：{str(e)[:50]}")
                    return None

    def parse_extinf_tags(self, m3u_content):
        """
        解析M3U内容，提取所有EXTINF标签和对应URL
        返回格式：[{"tvg-id": "", "tvg-name": "", "tvg-logo": "", "group-title": "", "url": ""}, ...]
        """
        # 匹配EXTINF行 + 下一行的URL（兼容各种空格/换行格式）
        pattern = re.compile(
            r'#EXTINF:-1\s*'
            r'(?:tvg-id="([^"]*)"\s*)?'       # 可选的tvg-id
            r'(?:tvg-name="([^"]*)"\s*)?'     # 可选的tvg-name
            r'(?:tvg-logo="([^"]*)"\s*)?'     # 可选的tvg-logo
            r'(?:group-title="([^"]*)"\s*)?'  # 可选的group-title
            r'.*?\n'                          # 行尾剩余内容
            r'([^\r\n]+)',                    # 频道URL（非空行）
            re.IGNORECASE | re.MULTILINE
        )
        
        channels = []
        matches = pattern.findall(m3u_content)
        for tvg_id, tvg_name, tvg_logo, group_title, url in matches:
            # 标准化处理：去空格、解码URL、统一空值为""
            clean_url = unquote(url.strip())  # 解码URL中的特殊字符（如%20）
            channel = {
                "tvg-id": tvg_id.strip() or "",
                "tvg-name": tvg_name.strip() or "",
                "tvg-logo": tvg_logo.strip() or "",
                "group-title": group_title.strip() or "",
                "url": clean_url
            }
            # 过滤无效URL
            if channel["url"] and not channel["url"].startswith("#"):
                channels.append(channel)
        
        # 输出解析详情
        if len(channels) == 0:
            print("⚠️ 未提取到任何EXTINF信息（可能源文件格式不规范）")
        else:
            print(f"   解析出 {len(channels)} 个原始频道")
        return channels

    def calculate_similarity(self, chan1, chan2):
        """计算两个频道字段的相似度（仅用于URL不同时的近似判断）"""
        # 优先用tvg-id精确匹配
        if chan1["tvg-id"] and chan2["tvg-id"] and chan1["tvg-id"] == chan2["tvg-id"]:
            return 1.0
        
        # 计算tvg-name相似度（核心字段）
        name_sim = difflib.SequenceMatcher(None, chan1["tvg-name"], chan2["tvg-name"]).ratio()
        # 计算group-title相似度（辅助字段）
        group_sim = difflib.SequenceMatcher(None, chan1["group-title"], chan2["group-title"]).ratio()
        
        # 加权平均：tvg-name占70%，group-title占30%
        return (name_sim * 0.7) + (group_sim * 0.3)

    def merge_channel(self, new_channel):
        """
        合并频道：
        1. URL相同 → 保留信息更完整的EXTINF标签
        2. URL不同 → 字段相似度≥阈值才判定为重复，否则保留
        """
        url = new_channel["url"]
        
        # 1. URL去重优先：检查URL是否已存在
        if url in self.channel_dict:
            existing = self.channel_dict[url]
            # 整合信息：保留非空字段（新频道有值则覆盖旧的空值）
            self.channel_dict[url] = {
                "tvg-id": existing["tvg-id"] or new_channel["tvg-id"],
                "tvg-name": existing["tvg-name"] or new_channel["tvg-name"],
                "tvg-logo": existing["tvg-logo"] or new_channel["tvg-logo"],
                "group-title": existing["group-title"] or new_channel["group-title"],
                "url": url
            }
            return
        
        # 2. URL不同时，检查字段近似度（避免重复频道）
        for existing_url, existing_chan in self.channel_dict.items():
            sim_score = self.calculate_similarity(new_channel, existing_chan)
            if sim_score >= self.similarity_threshold:
                # 近似匹配：保留信息更完整的那个
                if self.count_non_empty_fields(new_channel) > self.count_non_empty_fields(existing_chan):
                    self.channel_dict[existing_url] = new_channel
                return
        
        # 3. 无重复，新增频道
        self.channel_dict[url] = new_channel

    def count_non_empty_fields(self, channel):
        """统计频道非空字段数量（用于判断信息完整性）"""
        return sum(1 for v in channel.values() if v and v != channel["url"])

    def generate_m3u_file(self):
        """生成最终的M3U文件，按group-title分组排序"""
        # 按group-title分组
        grouped_channels = {}
        for channel in self.channel_dict.values():
            group = channel["group-title"] or "未分组"
            if group not in grouped_channels:
                grouped_channels[group] = []
            grouped_channels[group].append(channel)
        
        # 写入M3U文件
        try:
            with open(config.OUTPUT_FILE, "w", encoding="utf-8") as f:
                # M3U标准头部
                f.write("#EXTM3U x-tvg-url=\"https://epg.112114.xyz/pp.xml\"\n\n")
                
                # 按分组名称排序，逐个写入
                for group in sorted(grouped_channels.keys()):
                    channels = sorted(grouped_channels[group], key=lambda x: x["tvg-name"].lower())
                    for chan in channels:
                        # 构建EXTINF行（只保留非空字段）
                        extinf_parts = ["#EXTINF:-1"]
                        if chan["tvg-id"]:
                            extinf_parts.append(f'tvg-id="{chan["tvg-id"]}"')
                        if chan["tvg-name"]:
                            extinf_parts.append(f'tvg-name="{chan["tvg-name"]}"')
                        if chan["tvg-logo"]:
                            extinf_parts.append(f'tvg-logo="{chan["tvg-logo"]}"')
                        if chan["group-title"]:
                            extinf_parts.append(f'group-title="{chan["group-title"]}"')
                    
                    # 写入一行EXTINF + 一行URL
                    f.write(" ".join(extinf_parts) + "\n")
                    f.write(chan["url"] + "\n\n")
            
            print(f"\n✅ 生成成功！文件路径：{config.OUTPUT_FILE}")
            print(f"📊 统计：原始去重后保留 {len(self.channel_dict)} 个有效频道")
        except Exception as e:
            print(f"❌ 写入文件失败：{e}")

    def run(self):
        """主执行流程"""
        print("🚀 开始处理直播源...")
        total_parsed = 0
        
        # 遍历所有直播源URL
        for idx, url in enumerate(config.LIVE_SOURCE_URLS, 1):
            print(f"\n[{idx}/{len(config.LIVE_SOURCE_URLS)}] 处理：{url}")
            # 下载M3U内容（自动重试镜像/代理）
            m3u_content = self.download_m3u(url)
            if not m3u_content:
                continue
            
            # 解析EXTINF标签
            channels = self.parse_extinf_tags(m3u_content)
            total_parsed += len(channels)
            
            # 逐个合并（去重+整合信息）
            for chan in channels:
                self.merge_channel(chan)
        
        # 生成最终文件
        self.generate_m3u_file()
        print(f"\n📈 总解析频道数：{total_parsed} | 去重后保留：{len(self.channel_dict)}")

if __name__ == "__main__":
    # 实例化并运行
    merger = M3UMerger()
    merger.run()
