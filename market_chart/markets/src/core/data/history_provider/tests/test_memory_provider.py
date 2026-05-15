"""
MemoryCacheProvider 单元测试

TDD 原则：先写测试，再实现代码。
测试覆盖：fetch / set / known_empty 全部路径。
"""

import pytest
import pandas as pd
import numpy as np


class TestMemoryCacheProvider:
    """MemoryCacheProvider 测试类"""

    @pytest.fixture
    def provider(self):
        """创建空的 MemoryCacheProvider 实例"""
        from ..memory_provider import MemoryCacheProvider
        return MemoryCacheProvider()

    @pytest.fixture
    def sample_df(self):
        """创建示例日线数据 DataFrame"""
        dates = pd.date_range('2024-01-01', '2024-01-10', freq='B')  # 8个交易日
        return pd.DataFrame({
            'trade_date': dates,
            'open': [100.0 + i for i in range(len(dates))],
            'high': [101.0 + i for i in range(len(dates))],
            'low': [99.0 + i for i in range(len(dates))],
            'close': [100.5 + i for i in range(len(dates))],
            'volume': [1000000 + i * 1000 for i in range(len(dates))],
        })

    # === fetch 测试 ===

    def test_fetch_empty_no_symbol(self, provider):
        """未写入任何数据时，fetch 返回 None"""
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-10'))
        assert result is None

    def test_fetch_empty_symbol_no_data(self, provider, sample_df):
        """写入了 A 的数据，查 B 时返回 None"""
        provider.set('SH000001', sample_df)
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-10'))
        assert result is None

    def test_fetch_full_hit(self, provider, sample_df):
        """完全命中：请求范围完全在已缓存范围内"""
        provider.set('SH600519', sample_df)
        result = provider.fetch(
            'SH600519',
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-10')
        )
        assert result is not None
        assert len(result) == 8
        assert list(result.columns) == ['trade_date', 'open', 'high', 'low', 'close', 'volume']

    def test_fetch_partial_hit(self, provider, sample_df):
        """部分命中：请求范围部分在已缓存范围内"""
        provider.set('SH600519', sample_df)
        result = provider.fetch(
            'SH600519',
            pd.Timestamp('2024-01-03'),
            pd.Timestamp('2024-01-08')
        )
        assert result is not None
        assert len(result) == 4  # 1/3, 1/4, 1/5, 1/8 (跳过周末)
        assert result['trade_date'].iloc[0] == pd.Timestamp('2024-01-03')
        assert result['trade_date'].iloc[-1] == pd.Timestamp('2024-01-08')

    def test_fetch_out_of_range(self, provider, sample_df):
        """请求范围完全在已缓存范围外，返回 None"""
        provider.set('SH600519', sample_df)
        result = provider.fetch(
            'SH600519',
            pd.Timestamp('2024-02-01'),
            pd.Timestamp('2024-02-10')
        )
        assert result is None

    def test_fetch_exact_boundary(self, provider, sample_df):
        """精确边界测试：请求第一日和最后一日"""
        provider.set('SH600519', sample_df)
        result = provider.fetch(
            'SH600519',
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-01')
        )
        assert result is not None
        assert len(result) == 1
        assert result['trade_date'].iloc[0] == pd.Timestamp('2024-01-01')

    # === set 测试 ===

    def test_set_new_symbol(self, provider, sample_df):
        """首次写入新 symbol"""
        provider.set('SH600519', sample_df)
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-10'))
        assert result is not None
        assert len(result) == 8

    def test_set_merge_no_overlap(self, provider, sample_df):
        """合并无重叠的数据"""
        provider.set('SH600519', sample_df)

        # 新数据：1/11 ~ 1/17（与原有数据无重叠）
        new_dates = pd.date_range('2024-01-11', '2024-01-17', freq='B')
        new_df = pd.DataFrame({
            'trade_date': new_dates,
            'open': [200.0 + i for i in range(len(new_dates))],
            'high': [201.0 + i for i in range(len(new_dates))],
            'low': [199.0 + i for i in range(len(new_dates))],
            'close': [200.5 + i for i in range(len(new_dates))],
            'volume': [2000000 + i * 1000 for i in range(len(new_dates))],
        })

        provider.set('SH600519', new_df)
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-17'))
        assert result is not None
        assert len(result) == 13  # 8 + 5

    def test_set_dedup_keep_last(self, provider, sample_df):
        """合并有重叠的数据，重复日期保留后写入的"""
        provider.set('SH600519', sample_df)

        # 覆盖 1/1 ~ 1/3 的数据
        overlap_dates = pd.date_range('2024-01-01', '2024-01-03', freq='B')
        new_df = pd.DataFrame({
            'trade_date': overlap_dates,
            'open': [999.0, 999.0, 999.0],
            'high': [999.0, 999.0, 999.0],
            'low': [999.0, 999.0, 999.0],
            'close': [999.0, 999.0, 999.0],
            'volume': [999, 999, 999],
        })

        provider.set('SH600519', new_df)
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-10'))
        assert result is not None
        assert len(result) == 8  # 总行数不变

        # 验证重叠日期被覆盖
        jan1_row = result[result['trade_date'] == pd.Timestamp('2024-01-01')]
        assert jan1_row['open'].iloc[0] == 999.0

        # 验证未重叠日期保留原值
        jan5_row = result[result['trade_date'] == pd.Timestamp('2024-01-05')]
        assert jan5_row['open'].iloc[0] == 104.0

    def test_set_empty_dataframe(self, provider):
        """写入空 DataFrame 不应报错"""
        empty_df = pd.DataFrame(columns=['trade_date', 'open', 'high', 'low', 'close', 'volume'])
        provider.set('SH600519', empty_df)
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-10'))
        # 空DataFrame写入后，fetch应返回None
        assert result is None

    # === known_empty 测试 ===

    def test_known_empty_check(self, provider):
        """known_empty 区间应被识别"""
        provider.mark_known_empty(
            'SH600519',
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-10')
        )
        assert provider.is_known_empty('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-10'))

    def test_known_empty_partial_not_match(self, provider):
        """部分重叠的 known_empty 不应被视为完全匹配"""
        provider.mark_known_empty(
            'SH600519',
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-10')
        )
        # 请求范围大于 known_empty 范围
        assert not provider.is_known_empty('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-15'))

    def test_known_empty_after_set_data(self, provider, sample_df):
        """写入数据后，known_empty 应被清除（该区间不再为空）"""
        provider.mark_known_empty(
            'SH600519',
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-10')
        )
        provider.set('SH600519', sample_df)
        assert not provider.is_known_empty('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-10'))

    # === 多 symbol 测试 ===

    def test_multiple_symbols(self, provider, sample_df):
        """多个 symbol 独立存储，互不干扰"""
        provider.set('SH600519', sample_df)

        df2 = sample_df.copy()
        df2['open'] = df2['open'] + 1000
        provider.set('SH000001', df2)

        result1 = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-10'))
        result2 = provider.fetch('SH000001', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-10'))

        assert result1['open'].iloc[0] == 100.0
        assert result2['open'].iloc[0] == 1100.0

    # === earliest_date 测试 ===

    def test_earliest_date_tracking(self, provider, sample_df):
        """写入数据后应记录最早日期"""
        provider.set('SH600519', sample_df)
        earliest = provider.get_earliest_date('SH600519')
        assert earliest == pd.Timestamp('2024-01-01')
