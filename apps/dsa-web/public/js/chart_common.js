/**
 * 图表模块公共工具库
 * 专供 K线图(kline_chart.js) 和 分时图(intraday_chart.js) 使用
 * 职责：ECharts图表状态管理、市场时区转换、交易时间解析
 * 注意：此文件不是系统级公共库，仅服务于图表模块，避免被其他业务污染
 */

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
        chart.setOption({
            graphic: [{
                id: 'loading-overlay',
                type: 'text',
                left: 'center',
                top: 'center',
                style: {
                    text: text,
                    fontSize: 16,
                    fill: '#999'
                }
            }]
        }, false);
    } else {
        chart.setOption({
            graphic: [{
                id: 'loading-overlay',
                $action: 'remove'
            }]
        }, false);
    }
}

// ========== 市场时区相关工具函数 ==========

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
 * 根据当前选择的市场获取对应时区（从markets配置中获取）
 * @param {string} marketCode - 市场代码
 * @returns {string} 时区字符串
 */
function getMarketTimezone(marketCode) {
    if (!window.marketsConfig || !Array.isArray(window.marketsConfig)) {
        console.error('markets配置未加载，使用默认时区 Asia/Shanghai');
        return 'Asia/Shanghai';
    }
    const market = window.marketsConfig.find(function(m) { return m.code === marketCode; });
    return market ? market.timezone : 'Asia/Shanghai';
}

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
        let date;
        if (timeString.includes('T')) {
            date = new Date(timeString);
        } else if (timeString.includes('-') && timeString.includes(':')) {
            date = new Date(timeString.replace(' ', 'T'));
        } else if (/^\d+$/.test(timeString)) {
            date = new Date(parseInt(timeString));
        } else {
            date = new Date(timeString);
        }
        if (isNaN(date.getTime())) {
            console.error('extractFromMarketDateTimeStr: 无法解析时间字符串:', timeString);
            return null;
        }
        const timezoneOffset = getTimezoneOffset(marketTimezone);
        const localOffset = date.getTimezoneOffset();
        return new Date(date.getTime() + (timezoneOffset - localOffset) * 60000);
    } catch (e) {
        console.error('extractFromMarketDateTimeStr: 解析时间字符串失败:', e);
        return null;
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
        const dateMatch = dateTimeStr.match(/(\d{4}-\d{2}-\d{2})/);
        if (dateMatch) {
            return dateMatch[1];
        }
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
        const timeMatch = dateTimeStr.match(/(\d{2}:\d{2}:\d{2})/);
        if (timeMatch) {
            return timeMatch[1];
        }
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
 * 统一解析交易时间字符串
 * @param {string} tradingHoursStr - 交易时间字符串，格式如 "09:30-11:30,13:00-15:00" 或 "09:30-15:00"
 * @returns {Object} 包含open, close, lunch_start, lunch_end的对象
 */
function parseTradingHoursString(tradingHoursStr) {
    if (!tradingHoursStr || typeof tradingHoursStr !== 'string') {
        return {};
    }
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
 * 时间轴标签格式化函数
 * @param {string|number} value - 时间值
 * @returns {string} 格式化后的时间标签
 */
function formatTimeAxisLabel(value) {
    if (value && value.endsWith && value.endsWith(':00')) {
        return value.substring(0, 5);
    }
    if (typeof value === 'string' && value.length >= 5) {
        return value.substring(0, 5);
    }
    return value;
}

// ========== 导出到 ChartUtils 命名空间 ==========
window.ChartUtils = {
    showChartEmpty,
    showChartLoading,
    getTimezoneOffset,
    getMarketTimezone,
    formatToMarketDateTimeStr,
    extractFromMarketDateTimeStr,
    extractFromDateStr,
    extractFromTimeStr,
    parseTradingHoursString,
    formatTimeAxisLabel
};
