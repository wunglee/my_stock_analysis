"""
数据质量API服务单元测试
"""

import json
from unittest.mock import Mock, patch

import pytest

from app.api_service import DataQualityAPIService


class TestDataQualityAPIService:
    """数据质量API服务测试"""
    
    @pytest.fixture
    def mock_quality_monitor(self):
        """Mock质量监控器"""
        monitor = Mock()
        monitor.get_quality_history.return_value = [
            {
                'timestamp': '2024-01-01T12:00:00',
                'overall_score': 0.95,
                'anomaly_count': 2,
                'error_count': 1
            },
            {
                'timestamp': '2024-01-01T13:00:00',
                'overall_score': 0.98,
                'anomaly_count': 1,
                'error_count': 0
            }
        ]
        monitor.get_alert_history.return_value = [
            {'level': 'critical', 'severity': 'high', 'data_source': 'yahoo'},
            {'level': 'warning', 'severity': 'medium', 'data_source': 'tushare'},
            {'level': 'critical', 'severity': 'high', 'data_source': 'yahoo'}
        ]
        monitor.get_performance_statistics.return_value = {
            'uptime_human': '2 days',
            'uptime_seconds': 172800,
            'throughput': 1000,
            'success_rate': 0.98,
            'reliability': 0.95,
            'stability_score': 0.97
        }
        monitor.generate_comprehensive_report.return_value = {
            'report_id': 'test_report_123',
            'quality_analysis': {'avg_score': 0.96},
            'alert_analysis': {'total': 10},
            'performance_analysis': {'throughput': 1000}
        }
        return monitor
    
    @pytest.fixture
    def api_service(self, mock_quality_monitor):
        """创建API服务实例"""
        return DataQualityAPIService(mock_quality_monitor)
    
    @pytest.fixture
    def client(self, api_service):
        """Flask测试客户端"""
        api_service.app.config['TESTING'] = True
        return api_service.app.test_client()
    
    def test_init(self, api_service, mock_quality_monitor):
        """测试初始化"""
        assert api_service.quality_monitor == mock_quality_monitor
        assert api_service.app is not None
    
    def test_get_current_quality_success(self, client):
        """测试获取当前质量数据 - 成功"""
        response = client.get('/api/v1/quality/current?hours=24')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['status'] == 'success'
        assert 'data' in data
        assert 'timestamp' in data
        assert 'metadata' in data
        
        metadata = data['metadata']
        assert metadata['data_points'] == 2
        assert metadata['time_range'] == 'last_24_hours'
        assert 'quality_score_avg' in metadata
        assert 'anomaly_count_total' in metadata
    
    def test_get_current_quality_default_hours(self, client):
        """测试获取当前质量数据 - 默认时间范围"""
        response = client.get('/api/v1/quality/current')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['metadata']['time_range'] == 'last_24_hours'
    
    def test_generate_quality_report_json(self, client):
        """测试生成质量报告 - JSON格式"""
        response = client.get('/api/v1/quality/report?period=7d&format=json&include_details=true')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['status'] == 'success'
        assert 'report' in data
        assert 'timestamp' in data
        assert 'report_id' in data
        
        report = data['report']
        assert report['report_id'] == 'test_report_123'
        assert 'quality_analysis' in report
        assert 'alert_analysis' in report
    
    def test_generate_quality_report_without_details(self, client):
        """测试生成质量报告 - 不包含详细信息"""
        response = client.get('/api/v1/quality/report?include_details=false')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        report = data['report']
        assert 'quality_analysis' not in report
        assert 'alert_analysis' not in report
        assert 'performance_analysis' not in report
    
    def test_get_alerts_no_filter(self, client):
        """测试获取警报 - 无过滤"""
        response = client.get('/api/v1/alerts?hours=24')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['status'] == 'success'
        assert 'alerts' in data
        assert 'pagination' in data
        assert 'summary' in data
        
        assert data['summary']['total_alerts'] == 3
        assert len(data['alerts']) == 3
    
    def test_get_alerts_with_level_filter(self, client):
        """测试获取警报 - 按级别过滤"""
        response = client.get('/api/v1/alerts?hours=24&level=critical')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['summary']['total_alerts'] == 2
        assert all(alert['level'] == 'critical' for alert in data['alerts'])
    
    def test_get_alerts_with_severity_filter(self, client):
        """测试获取警报 - 按严重性过滤"""
        response = client.get('/api/v1/alerts?severity=high')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert all(alert['severity'] == 'high' for alert in data['alerts'])
    
    def test_get_alerts_with_pagination(self, client):
        """测试获取警报 - 分页"""
        response = client.get('/api/v1/alerts?page=1&per_page=2')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        pagination = data['pagination']
        assert pagination['page'] == 1
        assert pagination['per_page'] == 2
        assert pagination['total'] == 3
        assert pagination['pages'] == 2
        assert len(data['alerts']) == 2
    
    def test_get_performance(self, client):
        """测试获取性能统计"""
        response = client.get('/api/v1/performance')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['status'] == 'success'
        assert 'performance' in data
        assert 'timestamp' in data
        
        performance = data['performance']
        assert 'uptime_human' in performance
        assert 'throughput' in performance
        assert 'success_rate' in performance
        assert 'system_health' in performance
        assert 'trend_analysis' in performance
        assert 'recommendations' in performance
    
    def test_get_metrics(self, client):
        """测试获取监控指标"""
        response = client.get('/api/v1/metrics?type=all&time_range=24h&aggregation=hourly')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['status'] == 'success'
        assert 'metrics' in data
        assert 'metadata' in data
        
        metadata = data['metadata']
        assert metadata['metric_type'] == 'all'
        assert metadata['time_range'] == '24h'
        assert metadata['aggregation'] == 'hourly'
    
    def test_system_status(self, client):
        """测试系统状态"""
        response = client.get('/api/v1/status')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['status'] == 'success'
        assert 'system_status' in data
        assert 'timestamp' in data
        
        status = data['system_status']
        assert 'overall_status' in status
        assert 'performance_metrics' in status
    
    def test_get_config(self, client):
        """测试获取配置"""
        response = client.get('/api/v1/config')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['status'] == 'success'
        assert 'config' in data
        assert 'timestamp' in data
    
    def test_update_config_success(self, client):
        """测试更新配置 - 成功"""
        new_config = {
            'monitoring': {'threshold': 0.9},
            'api_settings': {'timeout': 60}
        }
        
        response = client.put(
            '/api/v1/config',
            data=json.dumps(new_config),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['status'] == 'success'
        assert data['message'] == '配置更新成功'
    
    def test_update_config_invalid(self, client):
        """测试更新配置 - 无效数据"""
        response = client.put('/api/v1/config', data='', content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        
        assert data['status'] == 'error'
        assert data['error_code'] == 'INVALID_CONFIG'
    
    def test_error_handler_404(self, client):
        """测试404错误处理"""
        response = client.get('/api/v1/nonexistent')
        
        assert response.status_code == 404
        data = json.loads(response.data)
        
        assert data['status'] == 'error'
        assert data['error_code'] == 'ENDPOINT_NOT_FOUND'

    def test_group_by_level(self, api_service):
        """测试按级别分组"""
        alerts = [
            {'level': 'critical'},
            {'level': 'critical'},
            {'level': 'warning'}
        ]
        
        grouped = api_service.controllers.group_by_level(alerts)
        
        assert grouped['critical'] == 2
        assert grouped['warning'] == 1
    
    def test_group_by_severity(self, api_service):
        """测试按严重性分组"""
        alerts = [
            {'severity': 'high'},
            {'severity': 'high'},
            {'severity': 'medium'}
        ]
        
        grouped = api_service.controllers.group_by_severity(alerts)
        
        assert grouped['high'] == 2
        assert grouped['medium'] == 1
    
    def test_group_by_source(self, api_service):
        """测试按数据源分组"""
        alerts = [
            {'data_source': 'yahoo'},
            {'data_source': 'yahoo'},
            {'data_source': 'tushare'}
        ]
        
        grouped = api_service.controllers.group_by_source(alerts)
        
        assert grouped['yahoo'] == 2
        assert grouped['tushare'] == 1
    
    def test_calculate_system_health_healthy(self, api_service):
        """测试计算系统健康度 - 健康"""
        stats = {
            'success_rate': 0.95,
            'uptime_seconds': 172800,
            'stability_score': 0.98
        }
        
        health = api_service.controllers.calculate_system_health(stats)
        
        assert health['status'] == 'healthy'
        assert health['score'] >= 80
        assert 'indicators' in health
    
    def test_calculate_system_health_degraded(self, api_service):
        """测试计算系统健康度 - 降级"""
        stats = {
            'success_rate': 0.70,
            'uptime_seconds': 3600,
            'stability_score': 0.65
        }
        
        health = api_service.controllers.calculate_system_health(stats)
        
        assert health['status'] in ['degraded', 'unhealthy']
        assert health['score'] < 80
    
    def test_analyze_performance_trend(self, api_service):
        """测试性能趋势分析"""
        stats = {'success_rate': 0.95, 'throughput': 1000}
        
        trend = api_service.controllers.analyze_performance_trend(stats)
        
        assert 'trend' in trend
        assert 'direction' in trend
        assert 'volatility' in trend
        assert 'confidence' in trend
    
    def test_generate_performance_recommendations(self, api_service):
        """测试生成性能建议 - 已迁移到monitoring_service"""
        # 此方法已迁移到 quality_monitor._generate_recommendations
        # 现在由监控服务负责，不再API服务的直接职责
        pass


class TestBatchIntradayData:
    """测试批量获取分时数据接口"""
    
    @pytest.fixture
    def mock_config(self):
        """Mock配置管理器"""
        from core.share.config_manager import ConfigManager
        return ConfigManager()
    
    @pytest.fixture
    def mock_chart_assembler(self):
        """Mock图表数据组装器"""
        from unittest.mock import Mock
        assembler = Mock()
        # 模拟批量请求返回数据
        assembler.assemble_intraday_data.return_value = {
            'symbol': '600036.SH',
            'name': '招商银行',
            'times': ['09:30:00', '09:31:00', '09:32:00'],
            'prices': [10.0, 10.1, 10.2],
            'volumes': [1000, 1100, 1200],
            'order_book': {'bids': [[10.0, 100]], 'asks': [[10.1, 100]]},
            'should_poll': True
        }
        return assembler
    
    @pytest.fixture
    def api_service(self, mock_config):
        """Create API service instance"""
        return DataQualityAPIService(mock_config)
    
    @pytest.fixture
    def client(self, api_service):
        """Flask测试客户端"""
        api_service.app.config['TESTING'] = True
        return api_service.app.test_client()
    
    @patch('app.chart_data.ChartDataAssembler')
    def test_batch_request_multiple_batches(self, mock_assembler_class, client):
        """测试批量请求多个批次"""
        # 配置Mock返回
        mock_instance = Mock()
        mock_instance.assemble_intraday_data.return_value = {
            'symbol': '600036.SH',
            'name': '招商银行',
            'times': ['09:30:00', '09:31:00', '09:32:00'],
            'prices': [10.0, 10.1, 10.2],
            'volumes': [1000, 1100, 1200],
            'order_book': {'bids': [[10.0, 100]], 'asks': [[10.1, 100]]},
            'should_poll': True
        }
        mock_assembler_class.return_value = mock_instance
        
        batches = [
            {"index": 1, "timestamp": 1000},
            {"index": 2, "timestamp": 1001},
            {"index": 3, "timestamp": 1002}
        ]
        
        resp = client.get(
            '/api/v1/intraday/data?symbol=600036.SH&'
            f'batches={json.dumps(batches)}&'
            'simulation_mode=intraday'
        )
        
        assert resp.status_code == 200
        data = json.loads(resp.data)
        
        assert data['status'] == 'success'
        assert 'data' in data
        assert 'times' in data['data']
        assert len(data['data']['times']) > 0
    
    @patch('app.chart_data.ChartDataAssembler')
    def test_batch_request_before_open_mode(self, mock_assembler_class, client):
        """测试盘前模式批量请求"""
        # 配置Mock返回 - 盘前模式只有盘口数据
        mock_instance = Mock()
        mock_instance.assemble_intraday_data.return_value = {
            'symbol': '600036.SH',
            'name': '招商银行',
            'times': [],  # 盘前没有分时tick
            'prices': [],
            'volumes': [],
            'order_book': {'bids': [[10.0, 100]], 'asks': [[10.1, 100]]},
            'should_poll': True
        }
        mock_assembler_class.return_value = mock_instance
        
        batches = [{"index": 1, "timestamp": 1000}]
        
        resp = client.get(
            '/api/v1/intraday/data?symbol=600036.SH&'
            f'batches={json.dumps(batches)}&'
            'simulation_mode=before_open'
        )
        
        assert resp.status_code == 200
        data = json.loads(resp.data)
        
        assert data['status'] == 'success'
        assert 'data' in data
        # 盘前模式应该只有盘口数据，没有分时tick
        assert len(data['data']['times']) == 0
        assert 'order_book' in data['data']
    
    @patch('app.chart_data.ChartDataAssembler')
    def test_batch_request_different_batch_ranges(self, mock_assembler_class, client):
        """测试不同批次范围的请求"""
        mock_instance = Mock()
        
        # 第一次调用返回批次[1,2,3]的数据
        mock_instance.assemble_intraday_data.side_effect = [
            {
                'symbol': '600036.SH',
                'name': '招商银行',
                'times': ['09:30:00', '10:00:00', '10:30:00'],
                'prices': [10.0, 10.1, 10.2],
                'volumes': [1000, 1100, 1200],
                'order_book': {'bids': [[10.0, 100]], 'asks': [[10.1, 100]]},
                'should_poll': True
            },
            {
                'symbol': '600036.SH',
                'name': '招商银行',
                'times': ['11:00:00', '13:30:00', '14:00:00'],
                'prices': [10.3, 10.4, 10.5],
                'volumes': [1300, 1400, 1500],
                'order_book': {'bids': [[10.3, 100]], 'asks': [[10.4, 100]]},
                'should_poll': True
            }
        ]
        mock_assembler_class.return_value = mock_instance
        
        # 第一批：批次[1,2,3]
        batches1 = [
            {"index": 1, "timestamp": 1000},
            {"index": 2, "timestamp": 1001},
            {"index": 3, "timestamp": 1002}
        ]
        resp1 = client.get(
            '/api/v1/intraday/data?symbol=600036.SH&'
            f'batches={json.dumps(batches1)}&'
            'simulation_mode=intraday'
        )
        data1 = json.loads(resp1.data)['data']
        
        # 第二批：批次[4,5,6]
        batches2 = [
            {"index": 4, "timestamp": 1003},
            {"index": 5, "timestamp": 1004},
            {"index": 6, "timestamp": 1005}
        ]
        resp2 = client.get(
            '/api/v1/intraday/data?symbol=600036.SH&'
            f'batches={json.dumps(batches2)}&'
            'simulation_mode=intraday'
        )
        data2 = json.loads(resp2.data)['data']
        
        # 验证两批数据的时间范围不同
        assert len(data1['times']) > 0
        assert len(data2['times']) > 0
        # 第二批的时间应该晚于第一批
        assert data1['times'][0] == '09:30:00'
        assert data2['times'][0] == '11:00:00'
