

import numpy as np
import pandas as pd
from typing import Dict, Any
import logging

from core.share.config_manager import ConfigManager

# 加载历史事件配置
config_manager = ConfigManager()
HISTORICAL_EVENT_PARAMS = config_manager.get('event_window.historical_events', {})

logger = logging.getLogger('Tests.MockData')


class MockHistoricalDataProvider:
    """
    测试用Mock历史数据提供者（仅用于测试fixtures）
    - 分段生成价格：事件前(EWMA重尾) + 事件期(精确下跌+负偏重尾) + 事件后(EWMA重尾)
    - 成交量与绝对收益相关，体现波动聚类
    
    重构说明（2025-12-02）：
    - 从 core/data/providers/historical_data_provider.py 迁移而来
    - 事件参数现在使用共享配置 HISTORICAL_EVENT_PARAMS
    """

    def __init__(self):
        # 使用共享配置代替内联定义
        self.event_params = HISTORICAL_EVENT_PARAMS

    def _generate_prices_with_event_window(self,
                                           dates: pd.DatetimeIndex,
                                           initial_price: float,
                                           event_start: pd.Timestamp,
                                           event_end: pd.Timestamp,
                                           event_decline: float,
                                           event_vol: float,
                                           base_volatility: float,
                                           start_date: str,
                                           end_date: str,
                                           cal: dict | None = None) -> np.ndarray:
        np.random.seed(hash(start_date + end_date) % 2**32)
        n_days = len(dates)
        prices = np.zeros(n_days)
        prices[0] = initial_price

        # 定位事件段索引
        event_start_idx = None
        event_end_idx = None
        for i, date in enumerate(dates):
            if event_start_idx is None and date >= event_start:
                event_start_idx = i
            if event_end_idx is None and date > event_end:
                event_end_idx = i - 1
                break
        if event_start_idx is None:
            event_start_idx = 0
        if event_end_idx is None:
            event_end_idx = n_days - 1

        # 事件前：EWMA + 重尾
        if event_start_idx > 0:
            lambda_ = (cal.get('lambda_pre', 0.94) if cal else 0.94)
            sigma = (cal.get('sigma_pre', base_volatility) if cal else base_volatility)
            sigma2 = sigma * sigma
            r_prev = 0.0
            for i in range(1, event_start_idx):
                epsilon = np.random.standard_t(df=(cal.get('df_pre', 6) if cal else 6))
                r = sigma * epsilon
                prices[i] = prices[i-1] * (1 + r)
                sigma2 = ((cal.get('omega', 1e-6) if cal else 1e-6)) + ((cal.get('alpha', 0.1) if cal else 0.1)) * (r_prev * r_prev) + ((cal.get('beta', 0.85) if cal else 0.85)) * (sigma2)
                sigma = float(np.sqrt(sigma2))
                r_prev = r

        # 事件期：精确下跌 + 负偏重尾
        if event_end_idx >= event_start_idx:
            event_period_days = event_end_idx - event_start_idx + 1
            base_drift = (1.0 + event_decline) ** (1.0 / event_period_days) - 1.0 if event_period_days > 0 else 0.0
            lambda_ = (cal.get('lambda_event', 0.92) if cal else 0.92)
            sigma = (cal.get('sigma_event', base_volatility * event_vol) if cal else base_volatility * event_vol)
            sigma2 = sigma * sigma
            r_prev = 0.0
            event_start_price = prices[event_start_idx - 1] if event_start_idx > 0 else initial_price
            for i in range(event_start_idx, event_end_idx):
                p_neg = (cal.get('p_neg', 0.2) if cal else 0.2)
                if np.random.rand() < p_neg:
                    epsilon = np.random.standard_t(df=(cal.get('df_event', 5) if cal else 5)) - 0.5
                else:
                    epsilon = np.random.standard_t(df=(cal.get('df_event', 6) if cal else 6))
                r = base_drift + sigma * 0.4 * epsilon
                prices[i] = prices[i-1] * (1 + r)
                sigma2 = ((cal.get('omega', 1e-6) if cal else 1e-6)) + ((cal.get('alpha', 0.1) if cal else 0.1)) * (r_prev * r_prev) + ((cal.get('beta', 0.85) if cal else 0.85)) * (sigma2)
                sigma = float(np.sqrt(sigma2))
                r_prev = r
            target_event_end_price = event_start_price * (1 + event_decline)
            prices[event_end_idx] = target_event_end_price

        # 事件后：EWMA + 重尾
        if event_end_idx < n_days - 1:
            lambda_ = (cal.get('lambda_post', 0.94) if cal else 0.94)
            sigma = (cal.get('sigma_post', base_volatility) if cal else base_volatility)
            sigma2 = sigma * sigma
            r_prev = 0.0
            for i in range(event_end_idx + 1, n_days):
                epsilon = np.random.standard_t(df=(cal.get('df_post', 6) if cal else 6))
                r = sigma * epsilon
                prices[i] = prices[i-1] * (1 + r)
                sigma2 = ((cal.get('omega', 1e-6) if cal else 1e-6)) + ((cal.get('alpha', 0.1) if cal else 0.1)) * (r_prev * r_prev) + ((cal.get('beta', 0.85) if cal else 0.85)) * (sigma2)
                sigma = float(np.sqrt(sigma2))
                r_prev = r

        return prices

    def get_index_prices(self, symbol: str, start_date: pd.Timestamp | str, end_date: pd.Timestamp | str, current_time: pd.Timestamp) -> pd.DataFrame:
        """
        获取指数价格数据
        
        Args:
            symbol: 指数代码
            start_date: 开始日期（pd.Timestamp 或 str）
            end_date: 结束日期（pd.Timestamp 或 str）
            current_time: 当前时间（pd.Timestamp）
        
        Returns:
            DataFrame with columns: ['date', 'open', 'high', 'low', 'close', 'volume']
            符合 HistoricalDataProvider 协议标准
        """
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        dates = pd.date_range(start, end, freq='B')
        n_days = len(dates)
        initial_price = 3000.0
        base_volatility = 0.015
        
        # 生成seed字符串（在两个分支之前）
        seed_str = str(start_date) + str(end_date)

        # 事件期匹配（交集判定）
        event_decline = 0.0
        event_vol = 1.0
        matched_event_start = None
        matched_event_end = None
        for _, params in self.event_params.items():
            es = pd.to_datetime(params['period'][0])
            ee = pd.to_datetime(params['period'][1])
            if not (end < es or start > ee):
                event_decline = params['expected_decline']
                event_vol = params['volatility_multiplier']
                matched_event_start = es
                matched_event_end = ee
                break

        if event_decline != 0.0 and matched_event_start is not None:
            prices = self._generate_prices_with_event_window(
                dates=dates,
                initial_price=initial_price,
                event_start=matched_event_start,
                event_end=matched_event_end,
                event_decline=event_decline,
                event_vol=event_vol,
                base_volatility=base_volatility,
                start_date=start_date,
                end_date=end_date,
                cal=None
            )
        else:
            # 非事件期：随机游走
            np.random.seed(hash(seed_str) % 2**32)
            daily_returns = np.random.normal(0, base_volatility, n_days)
            prices = initial_price * np.cumprod(1 + daily_returns)

        # 成交量与绝对收益相关
        daily_returns = np.insert(np.diff(prices) / prices[:-1], 0, 0.0)
        base_volume = 100000000
        volumes = base_volume * (1 + 3.0 * np.clip(np.abs(daily_returns), 0, 0.2) + np.random.uniform(-0.1, 0.1, n_days))
        volumes = np.clip(volumes, 0, None)
        
        # 生成 OHLC 数据（基于 close 价格）
        # 使用随机波动生成 high/low，open 使用前一天 close
        np.random.seed(hash(seed_str + 'ohlc') % 2**32)
        high_ratio = 1 + np.abs(np.random.normal(0, base_volatility * 0.5, n_days))
        low_ratio = 1 - np.abs(np.random.normal(0, base_volatility * 0.5, n_days))
        
        highs = prices * high_ratio
        lows = prices * low_ratio
        
        # open 价格：第一天等于 initial_price，其余天等于前一天的 close
        opens = np.roll(prices, 1)
        opens[0] = initial_price

        return pd.DataFrame({
            'date': dates,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': prices,
            'volume': volumes
        })

    def get_index_returns(self, symbol: str, start_date: pd.Timestamp | str, end_date: pd.Timestamp | str) -> pd.Series:
        df = self.get_index_prices(symbol, start_date, end_date, pd.Timestamp.now())
        returns = df['close'].pct_change().fillna(0)
        returns.index = df['date']
        return returns

    def get_stock_prices(self, symbol: str, start_date: pd.Timestamp | str, end_date: pd.Timestamp | str) -> pd.DataFrame:
        """
        获取个股价格数据（Mock实现，接口与YahooFinanceDataProvider一致）
        
        Args:
            symbol: 股票代码
            start_date: 开始日期（pd.Timestamp 或 str）
            end_date: 结束日期（pd.Timestamp 或 str）
        
        Returns:
            DataFrame with columns: ['date', 'open', 'high', 'low', 'close', 'volume']
            符合 HistoricalDataProvider 协议标准
        """
        # 支持 str 和 datetime
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        dates = pd.date_range(start, end, freq='B')
        n_days = len(dates)
        
        # 基础参数
        base_volatility = 0.02
        initial_price = 100.0 if symbol.endswith('.SS') or symbol.endswith('.SZ') else 50.0
        
        # 随机游走生成价格
        np.random.seed(hash(str(start) + str(end) + symbol) % 2**32)
        daily_returns = np.random.normal(0, base_volatility, n_days)
        prices = initial_price * np.cumprod(1 + daily_returns)
        
        # 成交量与绝对收益相关
        base_volume = 5_000_000
        volumes = base_volume * (
            1 + 2.0 * np.clip(np.abs(daily_returns), 0, 0.2) + np.random.uniform(-0.05, 0.05, n_days)
        )
        volumes = np.clip(volumes, 0, None)
        
        # 生成 OHLC 数据
        seed_str = str(start) + str(end) + symbol
        np.random.seed(hash(seed_str + 'ohlc') % 2**32)
        high_ratio = 1 + np.abs(np.random.normal(0, base_volatility * 0.5, n_days))
        low_ratio = 1 - np.abs(np.random.normal(0, base_volatility * 0.5, n_days))
        
        highs = prices * high_ratio
        lows = prices * low_ratio
        opens = np.roll(prices, 1)
        opens[0] = initial_price
        
        return pd.DataFrame({
            'date': dates,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': prices,
            'volume': volumes
        })
    
    def get_volatility_index(self, symbol: str, start_date: pd.Timestamp | str, end_date: pd.Timestamp | str) -> pd.Series:
        """
        获取波动率指数（Mock实现，接口与YahooFinanceDataProvider一致）
        
        Args:
            symbol: 指数代码
            start_date: 开始日期（pd.Timestamp 或 str）
            end_date: 结束日期（pd.Timestamp 或 str）
        
        Returns:
            pd.Series: 波动率指数序列，范围 [0.05, 0.5]
        """
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        dates = pd.date_range(start, end, freq='B')
        n_days = len(dates)
        
        np.random.seed(hash(str(start) + str(end) + symbol) % 2**32)
        vol = np.random.normal(0.2, 0.05, n_days)
        vol = np.clip(vol, 0.05, 0.5)
        return pd.Series(vol, index=dates)
    
    def validate_data_quality(self, data) -> Dict[str, Any]:
        """TODO：数据质量验证（简化版，无DataQualityChecker依赖）"""
        total_rows = len(data)
        missing_values = int(data.isna().sum().sum())
        
        # 简单的异常检测（IQR方法）
        outliers_detected = 0
        if 'close' in data.columns:
            Q1 = data['close'].quantile(0.25)
            Q3 = data['close'].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            outliers_detected = ((data['close'] < lower_bound) | (data['close'] > upper_bound)).sum()
        
        completeness = 1.0 - (missing_values / (total_rows * len(data.columns))) if total_rows > 0 else 0.0
        consistency = 1.0 - (outliers_detected / total_rows) if total_rows > 0 else 1.0
        
        return {
            'completeness_score': completeness,
            'consistency_score': consistency,
            'accuracy_score': 0.95,  # 默认值
            'outliers_detected': outliers_detected,
            'total_rows': total_rows,
            'missing_values': missing_values,
        }

    def get_event_window_data(self, symbol: str, event_date: str,
                              window_days: int = 30, baseline_days: int = 252) -> Dict[str, pd.DataFrame]:
        event_dt = pd.to_datetime(event_date)
        baseline_start = event_dt - pd.Timedelta(days=baseline_days + window_days + 100)
        baseline_end = event_dt - pd.Timedelta(days=1)
        event_start = event_dt - pd.Timedelta(days=window_days + 30)
        event_end = event_dt + pd.Timedelta(days=window_days + 30)

        baseline_data = self.get_index_prices(symbol, baseline_start.strftime('%Y-%m-%d'), baseline_end.strftime('%Y-%m-%d'), pd.Timestamp.now())
        # 基于baseline统计进行校准生成事件段数据
        r = baseline_data['close'].pct_change().dropna().values
        if r.size > 5:
            m = float(np.mean(r)); m2 = float(np.mean((r - m) ** 2))
            m3 = float(np.mean((r - m) ** 3)); m4 = float(np.mean((r - m) ** 4))
            skew = 0.0 if m2 == 0.0 else float(m3 / (m2 ** 1.5))
            kurt = 3.0 if m2 == 0.0 else float(m4 / (m2 ** 2))
            rsq = r ** 2
            acf_sq = float(np.corrcoef(rsq[:-1], rsq[1:])[0, 1]) if rsq.size > 1 else 0.9
        else:
            skew = 0.0; kurt = 3.5; acf_sq = 0.9; m2 = (0.015 ** 2)
        sigma_pre = float(np.sqrt(m2))
        lambda_pre = max(0.85, min(acf_sq, 0.99))
        lambda_event = max(0.85, min(lambda_pre * 0.97, 0.99))
        lambda_post = lambda_pre
        df_est = 6.0 if kurt <= 3.01 else max(4.5, min(50.0, 6.0 / (kurt - 3.0) + 4.0))
        df_pre = df_est
        df_event = max(4.5, min(50.0, df_est - 1.0))
        df_post = df_pre
        p_neg = min(0.7, 0.25 + 0.3 * min(abs(skew), 1.0)) if skew < 0 else max(0.05, 0.25 - 0.2 * min(skew, 1.0))
        # GARCH(1,1)参数估计（简化自标定）
        beta = max(0.60, min(0.95, acf_sq))
        alpha = max(0.05, min(0.25, 1.0 - beta - 0.02))
        omega = float(m2 * max(1e-6, (1.0 - alpha - beta)))
        cal = {'sigma_pre': sigma_pre, 'sigma_event': sigma_pre * 1.0, 'sigma_post': sigma_pre,
               'lambda_pre': lambda_pre, 'lambda_event': lambda_event, 'lambda_post': lambda_post,
               'df_pre': df_pre, 'df_event': df_event, 'df_post': df_post, 'p_neg': p_neg,
               'alpha': alpha, 'beta': beta, 'omega': omega}

        event_dates = pd.date_range(event_start.strftime('%Y-%m-%d'), event_end.strftime('%Y-%m-%d'), freq='B')
        # 匹配事件参数
        event_decline = -0.10; event_vol = 2.0; matched_period = None
        for _, params in self.event_params.items():
            es = pd.to_datetime(params['period'][0]); ee = pd.to_datetime(params['period'][1])
            if event_dt >= es and event_dt <= ee:
                event_decline = params['expected_decline']; event_vol = params['volatility_multiplier']; matched_period = (es, ee)
                break
        prices = self._generate_prices_with_event_window(
            dates=event_dates,
            initial_price=3000.0,
            event_start=(matched_period[0] if matched_period else event_dates[0]),
            event_end=(matched_period[1] if matched_period else event_dates[-1]),
            event_decline=event_decline,
            event_vol=event_vol,
            base_volatility=sigma_pre,
            start_date=event_start.strftime('%Y-%m-%d'),
            end_date=event_end.strftime('%Y-%m-%d'),
            cal=cal
        )
        daily_returns_event = np.insert(np.diff(prices) / prices[:-1], 0, 0.0)
        base_volume = 100000000
        volumes_event = base_volume * (1 + 3.0 * np.clip(np.abs(daily_returns_event), 0, 0.2) + np.random.uniform(-0.1, 0.1, len(event_dates)))
        volumes_event = np.clip(volumes_event, 0, None)
        event_data = pd.DataFrame({'date': event_dates, 'close': prices, 'volume': volumes_event})

        baseline_filtered = baseline_data.tail(baseline_days)
        event_filtered = event_data[(event_data['date'] >= event_dt - pd.Timedelta(days=window_days)) &
                                    (event_data['date'] <= event_dt + pd.Timedelta(days=window_days))]
        return {'event_window': event_filtered, 'baseline': baseline_filtered}
