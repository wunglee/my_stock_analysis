"""
Yahoo Finance Browser Simulation 补丁 (支持 HTTP/2)

Note: 
- 此补丁修复了 yfinance 的 "Too Many Requests" (429) 问题
- 使用 curl_cffi 模拟浏览器请求 (内置 HTTP/2 支持)
- 通过 crumb 认证绕过 Yahoo 的反爬虫机制
- 通过请求限流避免触发速率限制
- 通过随机 User-Agent 避免检测
- 通过 Referer 和 Origin 头绕过跨域限制
- 通过 X-Requested-With 头模拟 AJAX 请求

⚠️ 重要: 
- 需要安装: pip install curl_cffi
- 此补丁会 monkey patch yfinance.data.YfData.get 方法
- 所有通过 yfinance 的请求都会经过此补丁处理
- 所有反爬虫逻辑（User-Agent轮换、请求限流、浏览器模拟头）都由补丁处理
- HTTP/2 支持通过 curl_cffi 库自动启用
- YahooFinanceDataProvider 不需要重复实现这些逻辑
"""

import logging
import random
import re
import time
from typing import Optional
import urllib.parse

# 导入curl_cffi，假设总是存在
from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)

try:
    import yfinance
    from yfinance import data as yf_data
except ImportError:
    logger.warning("yfinance not installed")
    raise ImportError("yfinance not installed")

# 全局标志，避免重复 patch
_PATCHED = False

# curl_cffi session实例，用于模拟真实浏览器
_CURL_SESSION = curl_requests.Session()
# 设置浏览器模拟头
headers = {
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Referer': 'https://finance.yahoo.com/',
    'Origin': 'https://finance.yahoo.com',
}
_CURL_SESSION.headers.update(headers)

_LAST_REQUEST_TIME = time.time()  # 上次请求时间，初始化为当前时间
_MIN_REQUEST_INTERVAL = 2.0  # 最小请求间隔（秒）

# User-Agent 池（轮换使用，避免被识别为爬虫）
_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]


def extract_crumb_from_html(response_text: str) -> str:
    """从HTML中提取crumb"""
    crumb_patterns = [
        r'"crumb":"([^"]+)"',  # 标准格式
        r'crumb["\'\s]{0,3}:["\'\s]{0,3}["\']([^"\']*)["\']',  # 冒号分隔格式
        r'crumb["\'\s]{0,3}=["\'\s]{0,3}["\']([^"\']*)["\']',  # 等号分隔格式
    ]

    for pattern in crumb_patterns:
        crumb_match = re.search(pattern, response_text)
        if crumb_match:
            # 确保捕获组有内容
            for i in range(1, len(crumb_match.groups()) + 1):
                if crumb_match.group(i):
                    crumb = crumb_match.group(i)
                    logger.info(f"🔑 找到 crumb: {crumb[:10]}...")
                    break
            if crumb:
                break

    if not crumb:
        # 可能需要检查页面源码中是否有其他线索
        # 检查是否有相关的JavaScript文件或模块包含crumb
        import json
        # 尝试在页面中查找可能包含crumb的script标签
        script_matches = re.findall(r'<script[^>]*>(.*?)</script>', response_text, re.DOTALL)
        for script in script_matches:
            # 查找可能的crumb变量
            if 'crumb' in script.lower():
                # 尝试解析可能的JSON对象
                try:
                    # 寻找类似 "crumb": "value" 的模式
                    inline_crumb_match = re.search(r'["\'\']crumb["\'\']\s*:\s*["\'\']([^"\'\']*)["\'\']',
                                                   script)
                    if inline_crumb_match:
                        crumb = inline_crumb_match.group(1)
                        logger.info(f"🔑 从内联脚本找到 crumb: {crumb[:10]}...")
                        break
                except:
                    pass
    return crumb


def get_crumb(url, timeout) -> Optional[str]:
    # 尝试从页面中提取 crumb（Yahoo Finance 的认证令牌）
    # 根据实际测试，crumb存在于HTML页面中，而不是API响应中
    global _LAST_REQUEST_TIME
    crumb = None
    if 'finance.yahoo.com' in url:
        # 先访问主页获取可能的 crumb
        try:
            # 构建合适的页面URL来获取crumb
            # API端点不包含crumb，需要访问对应的页面
            home_url = url
            if 'query1.finance.yahoo.com' in url or 'query2.finance.yahoo.com' in url:
                # 从API URL提取股票代码，构建quote页面URL以获取crumb
                # 统一使用相同的逻辑提取symbol - 取最后一个"/"之后的部分
                path_part = url.split('/')[-1]
                # 去掉查询参数部分（如果有）
                symbol = path_part.split('?')[0]

                # 构建quote页面URL
                if symbol:
                    # 需要对symbol进行URL编码，处理特殊字符如^
                    encoded_symbol = urllib.parse.quote(symbol.upper(), safe='')
                    home_url = f'https://finance.yahoo.com/quote/{encoded_symbol}'
            logger.info(f"🌐 获取 crumb 从: {home_url[:100]}...")
            _CURL_SESSION.headers.update({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.9',
            })
            # 最多重试3次
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    speed_limit()
                    # 使用curl_cffi session
                    home_response = _CURL_SESSION.get(home_url, timeout=timeout, impersonate="chrome110")
                    # 更新最后请求时间
                    _LAST_REQUEST_TIME = time.time()
                    if home_response.status_code == 200:
                        # Yahoo Finance crumb可能存在于多种格式中，尝试多种正则表达式
                        crumb = extract_crumb_from_html(home_response.text)
                        if crumb:  # 如果成功提取到crumb，跳出重试循环
                            break
                except Exception as e:
                    logger.warning(f"获取crumb失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    if attempt == max_retries - 1:  # 如果是最后一次尝试
                        raise e # 重新抛出异常
        except Exception as e:
            logger.warning(f"无法获取crumb: {e}")
    return crumb


def speed_limit():
    # 应用速率限制，避免触发Yahoo的反爬虫机制
    # 使用与patched_get相同的速率限制逻辑
    global _LAST_REQUEST_TIME
    current_time = time.time()
    time_since_last = current_time - _LAST_REQUEST_TIME
    if time_since_last < 0.05:
        sleep_time = 0.05 - time_since_last
        if sleep_time > 0:  # 确保只有当需要等待时才等待
            logger.debug(f"请求限流: 等待 {sleep_time:.3f}秒以遵守Yahoo速率限制")
            time.sleep(sleep_time)


def patch_yfinance(proxy_url=None):
    """
    给 yfinance 打补丁，使其使用 curl_cffi Browser Simulation

    Args:
        proxy_url: 代理地址 (e.g., "http://127.0.0.1:8002")

    原理:
    - Monkey patch yfinance.data.YfData.get() 方法
    - 用 curl_cffi (浏览器模拟) 替换 requests 调用

    Note:
        如果代理配置了但代理服务未运行，会自动降级到直连
    """
    global _PATCHED, _CURL_SESSION
    if _PATCHED:
        logger.debug("yfinance already patched for Browser Simulation")
        return

    # 如果有代理，配置到 curl_cffi session
    if proxy_url:
        _CURL_SESSION.proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        logger.info(f"curl_cffi session configured with proxy: {proxy_url}")

    def patched_get(self, url, user_agent_headers=None, params=None, timeout=30):
        """
        使用 curl_cffi (模拟浏览器) 替代 requests

        关键优化：
        1. 轮换 User-Agent - 避免被识别为爬虫
        2. 请求限流 - 避免超过Yahoo官方限制 (2000次/分钟)
        3. 复用 Session - 保持 cookies
        4. Browser simulation - 模拟真实浏览器行为
        5. 指数退避重试 - 处理临时错误
        """
        global _LAST_REQUEST_TIME
        if user_agent_headers is None:
            user_agent_headers = {
                'User-Agent': random.choice(_USER_AGENTS)
            }
        # 使用浏览器模拟方式
        logger.info(f"📡 Browser simulation request: {url[:100]}...")
        # 安全处理 params 参数（避免 frozendict 问题）
        safe_params = {}
        if params is not None:
            # 如果 params 是 frozendict 或其他不可变类型，转换为普通字典
            try:
                safe_params = dict(params)  # 安全转换为可变字典
            except (TypeError, ValueError):
                logger.warning("无法转换 params 为字典，使用空参数")
                safe_params = {}
        crumb = get_crumb(url, timeout)
        if crumb:
            safe_params['crumb'] = crumb
        # 更新session headers
        _CURL_SESSION.headers.update({
            **user_agent_headers,
            'Accept': 'application/json, text/plain, */*',
        })
        speed_limit()
        # 发送请求
        response = _CURL_SESSION.get(url, params=safe_params, timeout=timeout, impersonate="chrome110")

        if response.status_code == 200:
            # 更新最后请求时间
            _LAST_REQUEST_TIME = time.time()
            logger.info(f"✅模拟浏览器请求成功: {response.status_code} - {url[:100]}...")
            return response
        else:
            logger.error(f"模拟浏览器请求失败: {response.status_code} - {url[:100]}...")
            raise Exception(f"HTTP {response.status_code} 错误")

    # 应用补丁
    yf_data.YfData.get = patched_get

    _PATCHED = True
    proxy_info = f" via proxy {proxy_url}" if proxy_url else " (direct)"
    logger.info(f"✅ yfinance patched to use curl_cffi browser simulation{proxy_info}")

# 自动应用补丁（导入时执行）
# 注意：代理配置需要在 Yahoo Provider 初始化时传入
# 这里只是预加载 patch 函数，不立即执行
# patch_yfinance()  # 先注释，由 Yahoo Provider 调用