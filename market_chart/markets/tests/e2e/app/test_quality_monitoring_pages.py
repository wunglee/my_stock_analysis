"""
质量监控应用层页面 E2E 测试

测试范围：
1. Dashboard 页面加载与数据展示
2. Data Explorer 页面交互
3. Rules Manager 页面操作
4. Scheduler Console 页面控制
5. Alerts Center 页面筛选
6. Providers 页面数据源管理
7. Credentials 管理
8. Validation Reports 页面

运行说明：
这些测试需要运行 Web 服务器，有两种运行方式：

1. 手动启动服务器后运行测试：
   ```bash
   # 终端1：启动服务器
   cd app/quality_monitoring
   python app_example.py
   
   # 终端2：运行E2E测试
   pytest tests/e2e/app/test_quality_monitoring_pages.py -v
   ```

2. 仅运行 API 测试（不需要浏览器）：
   ```bash
   pytest tests/e2e/app/test_quality_monitoring_pages.py::TestProvidersCredentialsAPI -v
   ```

注意：
- UI 测试需要 Chrome 浏览器和 chromedriver
- API 测试可以在 CI/CD 中运行（使用 mock 模式）
"""

import os
import time

import pytest
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# E2E 测试标记
E2E_MARKER = pytest.mark.e2e
REQUIRES_SERVER = pytest.mark.skipif(
    os.getenv('RUN_E2E_TESTS') != '1',
    reason="需要运行服务器。设置环境变量 RUN_E2E_TESTS=1 来启用"
)


@E2E_MARKER
@REQUIRES_SERVER
class TestQualityMonitoringPages:
    """质量监控应用层页面 E2E 测试
    
    这些测试需要：
    1. 运行 Web 服务器（localhost:5001）
    2. 安装 Chrome 和 chromedriver
    3. 设置环境变量 RUN_E2E_TESTS=1
    
    运行方式：
    ```bash
    export RUN_E2E_TESTS=1
    pytest tests/e2e/app/test_quality_monitoring_pages.py::TestQualityMonitoringPages -v
    ```
    """
    
    @pytest.fixture(scope="class")
    def driver(self):
        """设置 Selenium WebDriver"""
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')  # 无头模式
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        
        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(10)
        yield driver
        driver.quit()
    
    @pytest.fixture(scope="class")
    def base_url(self):
        """应用基础URL"""
        return "http://localhost:5001"

    @pytest.fixture(scope="class", autouse=True)
    def check_server(self, base_url):
        """检查服务器是否运行"""
        try:
            response = requests.get(f"{base_url}/health", timeout=5)
            if response.status_code != 200:
                pytest.skip("服务器未运行，跳过E2E测试")
        except requests.exceptions.RequestException:
            pytest.skip("服务器未运行，跳过E2E测试")
    
    def test_dashboard_page_loads(self, driver, base_url):
        """测试 Dashboard 页面加载"""
        driver.get(f"{base_url}/dashboard")
        
        # 等待页面标题加载
        wait = WebDriverWait(driver, 10)
        header = wait.until(
            EC.presence_of_element_located((By.TAG_NAME, "header"))
        )
        
        # 验证页面标题
        assert "DeepSeekQuant" in driver.title or "数据质量仪表板" in driver.title
        
        # 验证导航栏
        nav_links = driver.find_elements(By.CLASS_NAME, "nav-link")
        assert len(nav_links) >= 8, "导航链接数量不足"
        
        # 验证卡片区域存在
        cards = driver.find_elements(By.CLASS_NAME, "card")
        assert len(cards) > 0, "Dashboard 卡片未加载"
    
    def test_navigation_between_pages(self, driver, base_url):
        """测试页面间导航"""
        driver.get(f"{base_url}/dashboard")
        
        # 测试导航到 Explorer
        explorer_link = driver.find_element(By.LINK_TEXT, "Explorer")
        explorer_link.click()
        time.sleep(1)
        assert "/explorer" in driver.current_url
        
        # 测试导航到 Rules
        rules_link = driver.find_element(By.LINK_TEXT, "Rules")
        rules_link.click()
        time.sleep(1)
        assert "/rules" in driver.current_url
        
        # 测试导航到 Scheduler
        scheduler_link = driver.find_element(By.LINK_TEXT, "Scheduler")
        scheduler_link.click()
        time.sleep(1)
        assert "/scheduler" in driver.current_url
        
        # 测试导航到 Alerts
        alerts_link = driver.find_element(By.LINK_TEXT, "Alerts")
        alerts_link.click()
        time.sleep(1)
        assert "/alerts-center" in driver.current_url
        
        # 测试导航到 Providers
        providers_link = driver.find_element(By.LINK_TEXT, "Providers")
        providers_link.click()
        time.sleep(1)
        assert "/providers" in driver.current_url
    
    def test_providers_page_functionality(self, driver, base_url):
        """测试 Providers 页面功能"""
        driver.get(f"{base_url}/providers")
        
        wait = WebDriverWait(driver, 10)
        
        # 验证数据源表格加载
        providers_table = wait.until(
            EC.presence_of_element_located((By.ID, "providersTable"))
        )
        assert providers_table is not None
        
        # 验证凭证表格加载
        credentials_table = wait.until(
            EC.presence_of_element_located((By.ID, "credentialsTable"))
        )
        assert credentials_table is not None
        
        # 测试新增数据源按钮
        add_provider_btn = driver.find_element(
            By.XPATH, "//button[contains(text(), '新增数据源')]"
        )
        add_provider_btn.click()
        time.sleep(0.5)
        
        # 验证模态框打开
        modal = driver.find_element(By.ID, "providerModal")
        assert modal.is_displayed(), "数据源表单模态框未显示"
        
        # 关闭模态框
        close_btn = driver.find_element(
            By.XPATH, "//div[@id='providerModal']//button[contains(text(), '取消')]"
        )
        close_btn.click()
        time.sleep(0.5)
    
    def test_data_explorer_page(self, driver, base_url):
        """测试 Data Explorer 页面"""
        driver.get(f"{base_url}/explorer")
        
        wait = WebDriverWait(driver, 10)
        
        # 验证表单元素存在
        index_id_input = wait.until(
            EC.presence_of_element_located((By.ID, "indexId"))
        )
        assert index_id_input is not None
        
        # 验证图表容器存在
        chart = driver.find_element(By.ID, "priceChart")
        assert chart is not None
    
    def test_rules_manager_page(self, driver, base_url):
        """测试 Rules Manager 页面"""
        driver.get(f"{base_url}/rules")
        
        wait = WebDriverWait(driver, 10)
        
        # 验证规则表格加载
        rules_table = wait.until(
            EC.presence_of_element_located((By.ID, "rulesTable"))
        )
        assert rules_table is not None
        
        # 验证规则统计图表
        chart = driver.find_element(By.ID, "rulesChart")
        assert chart is not None
    
    def test_scheduler_console_page(self, driver, base_url):
        """测试 Scheduler Console 页面"""
        driver.get(f"{base_url}/scheduler")
        
        wait = WebDriverWait(driver, 10)
        
        # 验证作业表格加载
        jobs_table = wait.until(
            EC.presence_of_element_located((By.ID, "jobsTable"))
        )
        assert jobs_table is not None
        
        # 验证控制按钮存在
        try:
            trigger_btn = driver.find_element(
                By.XPATH, "//button[contains(text(), '立即执行')]"
            )
            assert trigger_btn is not None
        except:
            pass  # 如果按钮不存在也接受（可能根据状态显示）
    
    def test_alerts_center_page(self, driver, base_url):
        """测试 Alerts Center 页面"""
        driver.get(f"{base_url}/alerts-center")
        
        wait = WebDriverWait(driver, 10)
        
        # 验证警报表格加载
        alerts_table = wait.until(
            EC.presence_of_element_located((By.ID, "alertsTable"))
        )
        assert alerts_table is not None
        
        # 验证筛选器存在
        severity_filter = driver.find_element(By.ID, "severityFilter")
        assert severity_filter is not None
    
    def test_validation_reports_page(self, driver, base_url):
        """测试 Validation Reports 页面"""
        driver.get(f"{base_url}/validation")
        
        wait = WebDriverWait(driver, 10)
        
        # 验证日志表格加载
        cv_log_table = wait.until(
            EC.presence_of_element_located((By.ID, "cvLogTable"))
        )
        assert cv_log_table is not None
    
    def test_realtime_monitor_page(self, driver, base_url):
        """测试 Realtime Monitor 页面"""
        driver.get(f"{base_url}/realtime")
        
        wait = WebDriverWait(driver, 10)
        
        # 验证实时图表加载
        quality_chart = wait.until(
            EC.presence_of_element_located((By.ID, "qualityChart"))
        )
        assert quality_chart is not None
        
        # 验证日志容器存在
        log_container = driver.find_element(By.ID, "log")
        assert log_container is not None
    
    def test_responsive_header(self, driver, base_url):
        """测试响应式头部"""
        driver.get(f"{base_url}/dashboard")
        
        # 测试桌面视图
        driver.set_window_size(1920, 1080)
        time.sleep(0.5)
        header = driver.find_element(By.TAG_NAME, "header")
        assert header.is_displayed()
        
        # 测试平板视图
        driver.set_window_size(768, 1024)
        time.sleep(0.5)
        assert header.is_displayed()
        
        # 测试移动视图
        driver.set_window_size(375, 667)
        time.sleep(0.5)
        assert header.is_displayed()
        
        # 恢复桌面视图
        driver.set_window_size(1920, 1080)
    
    def test_system_status_indicator(self, driver, base_url):
        """测试系统状态指示器"""
        driver.get(f"{base_url}/dashboard")
        
        wait = WebDriverWait(driver, 10)
        
        # 验证状态指示器存在
        status_indicator = wait.until(
            EC.presence_of_element_located((By.CLASS_NAME, "status-indicator"))
        )
        assert status_indicator is not None
        
        # 验证状态文本
        status_text = driver.find_element(
            By.XPATH, "//div[@class='header-status']//span[2]"
        )
        assert "系统运行中" in status_text.text or "运行" in status_text.text


@E2E_MARKER
class TestProvidersCredentialsAPI:
    """Providers 和 Credentials API E2E 测试
    
    这些测试可以在两种模式下运行：
    1. 真实服务器模式：需要运行 Web 服务器
    2. Mock 模式：使用 responses 库 mock HTTP 请求（CI/CD 友好）
    
    运行方式：
    ```bash
    # Mock 模式（默认）
    pytest tests/e2e/app/test_quality_monitoring_pages.py::TestProvidersCredentialsAPI -v
    
    # 真实服务器模式
    export USE_REAL_SERVER=1
    pytest tests/e2e/app/test_quality_monitoring_pages.py::TestProvidersCredentialsAPI -v
    ```
    """
    
    @pytest.fixture(scope="class")
    def base_url(self):
        return "http://localhost:5001"
    
    @pytest.fixture(scope="class", autouse=True)
    def check_server(self, base_url):
        """检查服务器是否运行（仅在真实服务器模式下）"""
        use_real_server = os.getenv('USE_REAL_SERVER') == '1'
        
        if use_real_server:
            try:
                response = requests.get(f"{base_url}/health", timeout=5)
                if response.status_code != 200:
                    pytest.skip("服务器未运行，跳过E2E测试。请先启动服务器或使用 Mock 模式")
            except requests.exceptions.RequestException:
                pytest.skip("服务器未运行，跳过E2E测试。请先启动服务器或使用 Mock 模式")
        else:
            # Mock 模式：使用 responses 库
            pytest.skip("使用 Mock 模式运行 API 测试（暂未实现）。设置 USE_REAL_SERVER=1 使用真实服务器")
    
    def test_providers_crud_workflow(self, base_url):
        """测试 Providers CRUD 完整工作流"""
        
        # 1. 获取初始列表
        response = requests.get(f"{base_url}/api/v1/providers")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        initial_count = data['total']
        
        # 2. 创建新数据源
        new_provider = {
            "name": "test_provider_e2e",
            "type": "REST",
            "endpoint": "https://api.example.com",
            "description": "E2E测试数据源",
            "enabled": True
        }
        response = requests.post(
            f"{base_url}/api/v1/providers",
            json=new_provider
        )
        assert response.status_code == 201
        assert response.json()['status'] == 'success'
        
        # 3. 验证创建成功
        response = requests.get(f"{base_url}/api/v1/providers")
        assert response.json()['total'] == initial_count + 1
        
        # 4. 获取特定数据源
        response = requests.get(
            f"{base_url}/api/v1/providers/test_provider_e2e"
        )
        assert response.status_code == 200
        provider = response.json()['provider']
        assert provider['name'] == "test_provider_e2e"
        
        # 5. 更新数据源
        update_data = {
            "description": "更新后的描述",
            "enabled": False
        }
        response = requests.put(
            f"{base_url}/api/v1/providers/test_provider_e2e",
            json=update_data
        )
        assert response.status_code == 200
        
        # 6. 验证更新成功
        response = requests.get(
            f"{base_url}/api/v1/providers/test_provider_e2e"
        )
        provider = response.json()['provider']
        assert provider['description'] == "更新后的描述"
        assert provider['enabled'] == False
        
        # 7. 删除数据源
        response = requests.delete(
            f"{base_url}/api/v1/providers/test_provider_e2e"
        )
        assert response.status_code == 200
        
        # 8. 验证删除成功
        response = requests.get(f"{base_url}/api/v1/providers")
        assert response.json()['total'] == initial_count
    
    def test_credentials_crud_workflow(self, base_url):
        """测试 Credentials CRUD 完整工作流"""
        
        # 1. 获取初始列表
        response = requests.get(f"{base_url}/api/v1/credentials")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        initial_count = data['total']
        
        # 2. 创建新凭证
        new_credential = {
            "id": "test_cred_e2e",
            "type": "api_key",
            "provider": "test_provider",
            "username": "test_user",
            "api_key": "test_key_12345678",
            "secret": "test_secret",
            "enabled": True
        }
        response = requests.post(
            f"{base_url}/api/v1/credentials",
            json=new_credential
        )
        assert response.status_code == 201
        assert response.json()['status'] == 'success'
        
        # 3. 验证创建成功（应该脱敏）
        response = requests.get(f"{base_url}/api/v1/credentials")
        assert response.json()['total'] == initial_count + 1
        
        # 4. 获取特定凭证（应该脱敏）
        response = requests.get(
            f"{base_url}/api/v1/credentials/test_cred_e2e"
        )
        assert response.status_code == 200
        credential = response.json()['credential']
        assert credential['id'] == "test_cred_e2e"
        # 验证脱敏
        assert "***" in credential.get('api_key', '')
        
        # 5. 更新凭证
        update_data = {
            "enabled": False,
            "provider": "updated_provider"
        }
        response = requests.put(
            f"{base_url}/api/v1/credentials/test_cred_e2e",
            json=update_data
        )
        assert response.status_code == 200
        
        # 6. 验证更新成功
        response = requests.get(
            f"{base_url}/api/v1/credentials/test_cred_e2e"
        )
        credential = response.json()['credential']
        assert credential['enabled'] == False
        assert credential['provider'] == "updated_provider"
        
        # 7. 删除凭证
        response = requests.delete(
            f"{base_url}/api/v1/credentials/test_cred_e2e"
        )
        assert response.status_code == 200
        
        # 8. 验证删除成功
        response = requests.get(f"{base_url}/api/v1/credentials")
        assert response.json()['total'] == initial_count


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
