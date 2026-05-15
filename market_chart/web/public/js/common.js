/**
 * DeepSeekQuant 应用层通用 JavaScript 工具库
 */

// ========== 全局配置 ==========
const AppConfig = {
    apiBaseUrl: '/api/v1',
    refreshInterval: 5000,
    chartColors: {
        primary: '#2563eb',
        success: '#10b981',
        warning: '#f59e0b',
        danger: '#ef4444',
        info: '#3b82f6'
    }
};

// ========== 导航激活状态 ==========
function setActiveNav() {
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
}

// ========== ECharts 空状态渲染 ==========
function showChartEmpty(chart, text = '暂无数据') {
    chart.setOption({
        xAxis: { show: false },
        yAxis: { show: false },
        series: [],
        graphic: [{
            type: 'text',
            left: 'center',
            top: 'center',
            style: {
                text: text,
                fontSize: 16,
                fill: '#999'
            }
        }]
    }, true);
}

// ========== 图表加载状态管理 ==========
function showChartLoading(chart, show, text = '加载中...') {
    if (show) {
        // 使用 replace 模式，确保加载状态 graphic 被正确设置
        chart.setOption({
            graphic: [{
                id: 'loading-overlay',  // 设置唯一ID用于识别
                type: 'text',
                left: 'center',
                top: 'center',
                style: {
                    text: text,
                    fontSize: 16,
                    fill: '#999'
                }
            }]
        }, false);  // 使用 true 确保替换整个配置
    } else {
        // 移除加载状态 graphic
        chart.setOption({
            graphic: [{
                id: 'loading-overlay',
                $action: 'remove'  // ECharts 专用语法移除元素
            }]
        }, false);  // 使用 merge 模式仅移除指定元素
    }
}

// ========== API 请求封装 ==========
async function apiRequest(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : `${AppConfig.apiBaseUrl}${endpoint}`;
    
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API请求失败:', error);
        showToast('请求失败: ' + error.message, 'danger');
        throw error;
    }
}

// ========== 轻量级提示框 ==========
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        padding: 12px 20px;
        background: ${type === 'success' ? '#10b981' : type === 'danger' ? '#ef4444' : '#3b82f6'};
        color: white;
        border-radius: 6px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        z-index: 9999;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ========== 日期格式化 ==========
function formatDate(dateString, format = 'YYYY-MM-DD HH:mm:ss') {
    const date = new Date(dateString);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    
    return format
        .replace('YYYY', year)
        .replace('MM', month)
        .replace('DD', day)
        .replace('HH', hours)
        .replace('mm', minutes)
        .replace('ss', seconds);
}

// ========== 数字格式化 ==========
function formatNumber(num, decimals = 2) {
    if (num === null || num === undefined) return '-';
    return Number(num).toFixed(decimals);
}

function formatPercent(num, decimals = 2) {
    if (num === null || num === undefined) return '-';
    return (Number(num) * 100).toFixed(decimals) + '%';
}

// ========== 安全获取嵌套属性 ==========
function getNestedValue(obj, path, defaultValue = null) {
    return path.split('.').reduce((acc, part) => acc?.[part], obj) ?? defaultValue;
}

// ========== 防抖函数 ==========
function debounce(func, wait = 300) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ========== 节流函数 ==========
function throttle(func, limit = 300) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// ========== 加载状态管理 ==========
function showLoading(element) {
    if (typeof element === 'string') {
        element = document.querySelector(element);
    }
    if (element) {
        element.innerHTML = '<div class="loading"></div>';
    }
}

function hideLoading(element, content = '') {
    if (typeof element === 'string') {
        element = document.querySelector(element);
    }
    if (element) {
        element.innerHTML = content;
    }
}

// ========== 表格渲染工具 ==========
function renderTable(tableId, data, columns) {
    const table = document.getElementById(tableId);
    if (!table) return;
    
    const tbody = table.querySelector('tbody');
    if (!tbody) return;
    
    if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="' + columns.length + '" class="text-center text-muted">暂无数据</td></tr>';
        return;
    }
    
    tbody.innerHTML = data.map(row => {
        return '<tr>' + columns.map(col => {
            const value = typeof col.field === 'function' 
                ? col.field(row) 
                : getNestedValue(row, col.field);
            return '<td>' + (col.format ? col.format(value, row) : value || '-') + '</td>';
        }).join('') + '</tr>';
    }).join('');
}

// ========== 系统状态检查 ==========
async function checkSystemHealth() {
    try {
        const response = await apiRequest('/health');
        const indicator = document.querySelector('.status-indicator');
        if (indicator) {
            indicator.style.background = response.status === 'healthy' ? '#10b981' : '#ef4444';
        }
        return response.status === 'healthy';
    } catch (error) {
        const indicator = document.querySelector('.status-indicator');
        if (indicator) {
            indicator.style.background = '#ef4444';
        }
        return false;
    }
}

// ========== 页面初始化 ==========
document.addEventListener('DOMContentLoaded', function() {
    // 设置导航激活状态
    setActiveNav();
    
    // 定期检查系统健康状态
    checkSystemHealth();
    setInterval(checkSystemHealth, 30000);
    
    // 添加动画样式
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
    `;
    document.head.appendChild(style);
});

// ========== 市场时区相关工具函数 ==========

/**
 * 获取指定时间在指定市场时区的格式化时间字符串
 * @param {Date} date - Date对象（必须传入）
 * @param {string} marketTimezone - 市场时区
 * @returns {string} 指定市场时区的格式化时间字符串
 */
function formatToMarketDateTimeStr(date, marketTimezone) {
    if (!date || !(date instanceof Date)) {
        console.error('formatToMarketDateTimeStr: 必须传入有效的Date对象');
        return '';
    }

    if (!marketTimezone) {
        console.error('formatToMarketDateTimeStr: 必须传入有效的市场时区');
        return '';
    }

    try {
        return date.toLocaleString('zh-CN', {
            timeZone: marketTimezone,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    } catch (e) {
        console.error('格式化市场时间失败:', e);
        return '';
    }
}

/**
 * 从完整日期时间字符串中提取日期部分（YYYY-MM-DD格式）
 * @param {string} dateTimeStr - 完整的日期时间字符串
 * @param {string} marketTimezone - 市场时区
 * @returns {string} 日期部分（YYYY-MM-DD格式）
 */
function extractFromDateStr(dateTimeStr, marketTimezone) {
    if (!dateTimeStr || typeof dateTimeStr !== 'string') {
        console.error('extractFromDateStr: 必须传入有效的日期时间字符串');
        return '';
    }
    
    try {
        // 支持多种日期格式的提取
        const dateMatch = dateTimeStr.match(/(\d{4}-\d{2}-\d{2})/);
        if (dateMatch) {
            return dateMatch[1];
        }
        
        // 如果标准格式不匹配，尝试解析并重新格式化
        const date = extractFromMarketDateTimeStr(dateTimeStr, marketTimezone);
        if (date) {
            return date.toISOString().split('T')[0];
        }
        
        console.error('extractFromDateStr: 无法解析日期时间字符串:', dateTimeStr);
        return '';
    } catch (e) {
        console.error('extractFromDateStr: 提取日期部分失败:', e);
        return '';
    }
}

/**
 * 从完整日期时间字符串中提取时间部分（HH:MM:SS格式）
 * @param {string} dateTimeStr - 完整的日期时间字符串
 * @param {string} marketTimezone - 市场时区
 * @returns {string} 时间部分（HH:MM:SS格式）
 */
function extractFromTimeStr(dateTimeStr, marketTimezone) {
    if (!dateTimeStr || typeof dateTimeStr !== 'string') {
        console.error('extractFromTimeStr: 必须传入有效的日期时间字符串');
        return '';
    }
    
    try {
        // 支持多种时间格式的提取
        const timeMatch = dateTimeStr.match(/(\d{2}:\d{2}:\d{2})/);
        if (timeMatch) {
            return timeMatch[1];
        }
        
        // 如果标准格式不匹配，尝试解析并重新格式化
        const date = extractFromMarketDateTimeStr(dateTimeStr, marketTimezone);
        if (date) {
            const hours = String(date.getHours()).padStart(2, '0');
            const minutes = String(date.getMinutes()).padStart(2, '0');
            const seconds = String(date.getSeconds()).padStart(2, '0');
            return `${hours}:${minutes}:${seconds}`;
        }
        
        console.error('extractFromTimeStr: 无法解析日期时间字符串:', dateTimeStr);
        return '';
    } catch (e) {
        console.error('extractFromTimeStr: 提取时间部分失败:', e);
        return '';
    }
}

/**
 * 将时间字符串解析为指定市场时区的Date对象
 * @param {string} timeString - 时间字符串（支持多种格式）
 * @param {string} marketTimezone - 市场时区
 * @returns {Date} 指定市场时区的Date对象
 */
function extractFromMarketDateTimeStr(timeString, marketTimezone) {
    if (!timeString || typeof timeString !== 'string') {
        console.error('extractFromMarketDateTimeStr: 必须传入有效的时间字符串');
        return null;
    }
    
    if (!marketTimezone) {
        console.error('extractFromMarketDateTimeStr: 必须传入有效的市场时区');
        return null;
    }
    
    try {
        // 支持多种时间格式的解析
        let date;
        
        // 尝试解析ISO格式
        if (timeString.includes('T')) {
            date = new Date(timeString);
        } 
        // 尝试解析中文格式（如：2024-01-15 14:30:00）
        else if (timeString.includes('-') && timeString.includes(':')) {
            // 将中文格式转换为ISO格式
            const isoString = timeString.replace(' ', 'T');
            date = new Date(isoString);
        }
        // 尝试解析时间戳
        else if (/^\d+$/.test(timeString)) {
            date = new Date(parseInt(timeString));
        }
        // 其他格式使用默认解析
        else {
            date = new Date(timeString);
        }
        
        if (isNaN(date.getTime())) {
            console.error('extractFromMarketDateTimeStr: 无法解析时间字符串:', timeString);
            return null;
        }
        
        // 正确的时区转换方法：使用时区偏移量调整
        const timezoneOffset = getTimezoneOffset(marketTimezone);
        const localOffset = date.getTimezoneOffset();
        const adjustedTime = new Date(date.getTime() + (timezoneOffset - localOffset) * 60000);
        
        return adjustedTime;
        
    } catch (e) {
        console.error('extractFromMarketDateTimeStr: 解析时间字符串失败:', e);
        return null;
    }
}

/**
 * 获取指定时区的分钟偏移量
 * @param {string} timezone - 时区名称
 * @returns {number} 分钟偏移量
 */
function getTimezoneOffset(timezone) {
    const date = new Date();
    const utcDate = new Date(date.toLocaleString('en-US', { timeZone: 'UTC' }));
    const tzDate = new Date(date.toLocaleString('en-US', { timeZone: timezone }));
    return (utcDate.getTime() - tzDate.getTime()) / 60000;
}

/**
 * 统一解析交易时间字符串
 * @param {string} tradingHoursStr - 交易时间字符串，格式如 "09:30-11:30,13:00-15:00" 或 "09:30-15:00"
 * @returns {Object} 包含open, close, lunch_start, lunch_end的对象
 */
function parseTradingHoursString(tradingHoursStr) {
    if (!tradingHoursStr || typeof tradingHoursStr !== 'string') {
        return {};
    }

    // 检查是否包含午休时段（逗号分隔）
    if (tradingHoursStr.includes(',')) {
        const segments = tradingHoursStr.split(',');
        const morning = segments[0].trim();
        const afternoon = segments[1].trim();

        const morningParts = morning.split('-');
        const afternoonParts = afternoon.split('-');

        return {
            open: morningParts[0]?.trim(),
            close: afternoonParts[1]?.trim(),
            lunch_start: morningParts[1]?.trim(),
            lunch_end: afternoonParts[0]?.trim()
        };
    } else {
        // 没有午休时段的格式，如 "09:30-15:00"
        const parts = tradingHoursStr.split('-');
        return {
            open: parts[0]?.trim(),
            close: parts[1]?.trim(),
            lunch_start: null,
            lunch_end: null
        };
    }
}
/**
 * 根据当前选择的市场获取对应时区（从markets配置中获取）
 * @returns {string} 时区字符串
 */
function getMarketTimezone(marketCode) {
    if (!window.marketsConfig || !Array.isArray(window.marketsConfig)) {
        console.error('❌错误：markets配置未加载');
        throw new Error('markets配置未加载');
    }
    const market = window.marketsConfig.find(m => m.code === marketCode);
    if (!market) {
        console.error(`❌未找到市场代码 ${marketCode} 的配置`);
        throw new Error(`未找到市场代码 ${marketCode} 的配置`);
    }
    return market.timezone;
}
/**
 * 时间轴标签格式化函数
 * @param {string|number} value - 时间值
 * @returns {string} 格式化后的时间标签
 */
function formatTimeAxisLabel(value) {
    // 只显示整分钟的标签（HH:MM:00）
    if (value && value.endsWith && value.endsWith(':00')) {
        return value.substring(0, 5);  // 去掉秒，显示HH:MM
    }
    // 对于非整分钟或非字符串值，返回格式化的时刻显示
    if (typeof value === 'string' && value.length >= 5) {
        return value.substring(0, 5);  // 显示HH:MM格式
    }
    return value;  // 如果不是字符串则返回原值
}


// ========== 导出工具函数 ==========
window.AppUtils = {
    setActiveNav,
    apiRequest,
    showToast,
    showChartEmpty,
    showChartLoading,
    formatDate,
    formatNumber,
    formatPercent,
    getNestedValue,
    debounce,
    throttle,
    showLoading,
    hideLoading,
    renderTable,
    checkSystemHealth,
    // 市场时区相关工具函数
    formatToMarketDateTimeStr,
    extractFromDateStr,
    extractFromTimeStr,
    extractFromMarketDateTimeStr,
    getTimezoneOffset,
    parseTradingHoursString,
    formatTimeAxisLabel,
    getMarketTimezone
};
