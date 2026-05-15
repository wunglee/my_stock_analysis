#!/usr/bin/env python3
"""
Yahoo Finance 限速集成测试

验证当前方案是否能达到官方限速标准：
- 每小时 2000 次
- 每分钟几十次
- 即每 2 秒允许 1 次

测试方法：连续请求 10 次，间隔 2-3 秒

Note:
    这是集成测试，需要真实网络请求
    位置符合规范：tests/integration/core/data/providers/
"""

import pandas as pd
import time

from core.data.providers.yahoo_provider import YahooFinanceDataProvider
from core.share.config_manager import ConfigManager

print("=" * 70)
print("Yahoo Finance 限速测试")
print("=" * 70)

# 读取配置
config = ConfigManager()
provider_config = config.get_provider_config()
yahoo_provider = next((p for p in provider_config.providers if p.get('id') == 'yahoo'), {})
use_proxy = yahoo_provider.get('use_proxy', False)
proxy_config = config.get_proxies_from_config() if use_proxy else None

print(f"\n📋 当前配置:")
print(f"   use_proxy: {use_proxy}")
if use_proxy and proxy_config:
    print(f"   代理地址: {proxy_config.get('http')}")
else:
    print(f"   代理地址: 直连")

print(f"\n🎯 测试目标: 每 2 秒请求 1 次，共 10 次")
print(f"   预期结果: 全部成功（符合 Yahoo 官方限速）")
print(f"   实际限速: 2000次/小时 ≈ 每2秒1次\n")

provider = YahooFinanceDataProvider()

# 测试不同股票代码（避免缓存）
test_symbols = ['^GSPC', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 
                'TSLA', 'NVDA', 'META', 'NFLX', 'AMD']

success_count = 0
fail_count = 0
results = []

start_time = time.time()

for i, symbol in enumerate(test_symbols[:10], 1):
    print(f"[{i}/10] 请求 {symbol}... ", end='', flush=True)
    
    try:
        request_start = time.time()
        data = provider.get_index_prices(
            symbol, 
            pd.Timestamp.now() - pd.Timedelta(days=3), 
            pd.Timestamp.now()
        )
        request_time = time.time() - request_start
        
        print(f"✅ 成功 ({len(data.records)} 条数据, {request_time:.2f}s)")
        success_count += 1
        results.append({'symbol': symbol, 'status': 'success', 'time': request_time})
        
    except Exception as e:
        error_msg = str(e)
        request_time = time.time() - request_start
        
        if '429' in error_msg or 'Too Many Requests' in error_msg or 'Rate limit' in error_msg:
            print(f"❌ 限速 ({request_time:.2f}s)")
            fail_count += 1
            results.append({'symbol': symbol, 'status': 'rate_limited', 'time': request_time})
        else:
            print(f"❌ 错误: {error_msg[:50]}... ({request_time:.2f}s)")
            fail_count += 1
            results.append({'symbol': symbol, 'status': 'error', 'time': request_time, 'error': error_msg})
    
    # 间隔 2 秒（符合官方限速）
    if i < 10:
        time.sleep(2)

total_time = time.time() - start_time

print("\n" + "=" * 70)
print("测试结果汇总")
print("=" * 70)
print(f"\n✅ 成功: {success_count}/10")
print(f"❌ 失败: {fail_count}/10")
print(f"⏱️  总耗时: {total_time:.2f}s")
print(f"📊 平均速率: {10 / total_time * 3600:.0f} 次/小时")

print(f"\n📋 详细结果:")
for r in results:
    status_icon = "✅" if r['status'] == 'success' else "❌"
    print(f"   {status_icon} {r['symbol']:6s} - {r['status']:15s} ({r['time']:.2f}s)")

print(f"\n🎯 结论:")
if success_count >= 8:
    print(f"   ✅ 通过！当前方案符合 Yahoo Finance 官方限速标准")
    print(f"   📈 成功率: {success_count/10*100:.0f}%")
else:
    print(f"   ❌ 未通过！当前方案存在问题")
    print(f"   📉 成功率: {success_count/10*100:.0f}% (预期 >= 80%)")
    print(f"\n💡 可能原因:")
    print(f"   1. 代理配置问题")
    print(f"   2. HTTP/2 补丁未生效")
    print(f"   3. Yahoo 对某些 IP 限制更严格")
    print(f"   4. 请求头/User-Agent 被识别为机器人")
