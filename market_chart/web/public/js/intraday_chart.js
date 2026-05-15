/**
 * 分时图模块 - 完全独立的分时图管理
 * 职责：管理分时图的布局、数据加载、渲染
 */

// ==================== IntradayChart 模块对象 ====================
// 使用块级作用域避免 IIFE，支持更好的调试体验
{
    // ==================== 私有状态 ====================
    let intradayPriceChart = null
    let intradayVolumeChart = null
    let intradayData = null
    let intradayUpdateTimer = null
    let lastIntradayBatchIndex = 0
    let lastIntradayRequestTime = 0
    let virtualIntradayTime = 0  // 🎮 虚拟交易时间（秒），用于模拟模式
    let symbol = null
    let current_market_code = 'CN'
    let use_mock_mode = false
    let mock_trading_phase = 'trading'
    
    // ==================== 私有函数 ====================
    function getCharts() {
        return { price: intradayPriceChart, volume: intradayVolumeChart };
    }
    
    function getData() {
        return intradayData;
    }
    
    function setData(data) {
        intradayData = data;
    }

    function getBatchIndex() {
        return lastIntradayBatchIndex;
    }
    
    function setBatchIndex(index) {
        lastIntradayBatchIndex = index;
    }
    
    function getRequestTime() {
        return lastIntradayRequestTime;
    }
    
    function setRequestTime(time) {
        lastIntradayRequestTime = time;
    }
    
    function getVirtualTime() {
        return virtualIntradayTime;
    }
    
    function setVirtualTime(time) {
        virtualIntradayTime = time;
    }
    
    function generateTradingTimesInternal(tradingTimes, start, end, stepSeconds = 5) {
        if (!tradingTimes) {
            tradingTimes = []
        }
    
        // 将开始和结束时间转换为总秒数（从当天00:00:00开始计算）
        const startTotalSeconds = start[0] * 3600 + start[1] * 60;
        const endTotalSeconds = end[0] * 3600 + end[1] * 60; // 结束时间是XX:XX:00
    
        // 循环从开始时间到结束时间，按stepSeconds步长递增
        for (let totalSeconds = startTotalSeconds; totalSeconds <= endTotalSeconds; totalSeconds += stepSeconds) {
            // 将总秒数转换回时、分、秒
            const hour = Math.floor(totalSeconds / 3600);
            const minute = Math.floor((totalSeconds % 3600) / 60);
            const second = totalSeconds % 60;
    
            // 检查是否超出结束时间
            if (hour > end[0] || (hour === end[0] && minute > end[1])) continue;
    
            const timeStr = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:${String(second).padStart(2, '0')}`;
    
            // 避免重复添加时间点
            if (!tradingTimes.includes(timeStr)) {
                tradingTimes.push(timeStr);
            }
        }
    
        return tradingTimes
    }
    
    function initializeIntradayTimeAxis() {
        if (!current_market_code) {
            console.warn('⚠️ 当前市场代码未设置，无法初始化时间轴')
            return
        }
        console.log('🔍 initializeIntradayTimeAxis - 当前市场:', current_market_code)
        // 生成当前市场的完整交易时间轴
        const timeAxisInfo = getFullTradingTimes()
        const fullTradingTimes = timeAxisInfo.tradingTimes
        const lunchBreakRange = timeAxisInfo.lunchBreakRange
        console.log('🔍 initializeIntradayTimeAxis - 时间轴长度:', fullTradingTimes.length, '午休范围:', lunchBreakRange)
    
        // 🔧 根据市场配置动态生成半小时时间点
        const axisLabelConfig = generateTimeAxisLabelConfig(fullTradingTimes)
    
        // 设置图表的基础配置（与具体股票无关的时间轴和分割线）
        const charts = getCharts()
        console.log('🔍 initializeIntradayTimeAxis - 图表实例:', charts)
    
        if (charts.price && charts.volume) {
            // 准备基础markLine配置（用于午休分割线等）
            const markLineData = makeLunchBreakLine()
            console.log('🔍 initializeIntradayTimeAxis - markLineData:', markLineData)
    
            // 为价格图表设置完整的基础配置
            charts.price.setOption({
                // 标题配置占位（数据相关部分在renderIntradayCharts中设置）
                title: {
                    text: '',
                    left: 'center',
                    textStyle: { fontSize: 14 },
                    subtext: '',
                    subtextStyle: { fontSize: 11 }
                },
                // tooltip配置
                tooltip: {
                    trigger: 'axis',
                    formatter: function(params) {
                        let result = params[0].axisValue + '<br/>'
                        params.forEach(item => {
                            // 处理null值
                            if (item.value === null || item.value === undefined) {
                                return
                            }
                            const value = parseFloat(item.value)
                            result += item.marker + item.seriesName + ': ' + value.toFixed(2) + '<br/>'
                        })
                        return result
                    }
                },
                // 网格配置
                grid: { left: '50px', right: '50px', top: '60px', bottom: '30px' },
                // x轴配置（时间轴）
                xAxis: {
                    type: 'category',
                    data: fullTradingTimes,  // 使用全局初始化的时间轴
                    boundaryGap: false,
                    axisLabel: axisLabelConfig  // 🔧 使用动态计算的刻度配置
                },
                // y轴配置
                yAxis: {
                    type: 'value',
                    scale: true,
                    splitLine: {
                        lineStyle: { type: 'dashed', color: '#e5e7eb' }
                    },
                    axisLine: { onZero: false }
                },
                // 系列配置（基础结构）
                series: [
                    {
                        name: '价格',
                        type: 'line',
                        data: [],  // 初始为空，等待 renderCharts 填充
                        smooth: 0.6,
                        symbol: 'none',
                        showSymbol: false,
                        lineStyle: { width: 2 },
                        itemStyle: { color: '#2563eb' },
                        areaStyle: {
                            color: {
                                type: 'linear',
                                x: 0, y: 0, x2: 0, y2: 1,
                                colorStops: [
                                    { offset: 0, color: 'rgba(37, 99, 235, 0.3)' },
                                    { offset: 1, color: 'rgba(37, 99, 235, 0.05)' }
                                ]
                            }
                        },
                        connectNulls: true,
                        markLine: {
                            symbol: 'none',
                            silent: false,
                            animation: false,
                            data: markLineData  // 午休分割线
                        }
                    },
                    {
                        name: '均价',
                        type: 'line',
                        data: [],  // 初始为空，等待 renderCharts 填充
                        smooth: 0.6,
                        symbol: 'none',
                        showSymbol: false,
                        lineStyle: { width: 1.5, color: '#f59e0b', type: 'dashed' },
                        connectNulls: true
                    }
                ]
            }, true)  // 关键：使用true完全替换，清除旧市场配置
    
            // 为成交量图表设置完整的基础配置
            charts.volume.setOption({
                // 标题配置
                title: {
                    text: '成交量',
                    left: 'center',
                    textStyle: { fontSize: 12 }
                },
                // tooltip配置
                tooltip: {
                    trigger: 'axis',
                    formatter: function(params) {
                        if (!params || params.length === 0) return ''
                        const volume = params[0].value
                        // 处理null值
                        if (volume === null || volume === undefined) {
                            return params[0].axisValue + '<br/>' + params[0].marker + '成交量: 无数据'
                        }
                        return params[0].axisValue + '<br/>' + params[0].marker + '成交量: ' + volume.toLocaleString() + '手'
                    }
                },
                // 网格配置
                grid: { left: '50px', right: '50px', top: '40px', bottom: '20px' },
                // x轴配置（时间轴）
                xAxis: {
                    type: 'category',
                    data: fullTradingTimes,
                    show: false,
                    axisLabel: axisLabelConfig  // 🔧 使用相同的刻度配置
                },
                // y轴配置
                yAxis: {
                    type: 'value',
                    splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } }
                },
                // 系列配置（基础结构）
                series: [{
                    name: '成交量',
                    type: 'bar',
                    data: [],  // 初始为空，等待 renderCharts 填充
                    barWidth: '80%',
                    markLine: {
                        symbol: 'none',
                        silent: false,
                        animation: false,
                        data: markLineData  // 合并后的markLine数据（包含午休分割线和保留的其他线）
                    }
                }]
            }, true)  // 关键：使用true完全替换，清除旧市场配置
            showLoading(true)
        }
    }
    
    function getModeConfig(isInitial) {
        const lastRequestTime = getRequestTime();
    
        if (use_mock_mode) {
                return {
                    pollInterval: 5000,
                    setupInitialState: function() {
                        const virtualStartTime = '2024-12-14 09:30:00';
                        setVirtualTime(virtualStartTime);
                    },
                    getCurrentTime: function(isInitial) {
                        if (isInitial) {
                            // 首次加载：使用已设置的虚拟时间 (09:30:00)
                            return getVirtualTime();
                        } else {
                            // 增量更新：虚拟时间递增 1 分钟
                            const lastVirtualTime = getVirtualTime();
                            // 🔧 直接字符串操作：解析时间并增加 1 分钟
                            const [date, time] = lastVirtualTime.split(' ');
                            const [hours, minutes, seconds] = time.split(':').map(Number);
                            const totalMinutes = hours * 60 + minutes + 1;  // +1分钟
                            const newHours = Math.floor(totalMinutes / 60);
                            const newMinutes = totalMinutes % 60;
                            const newTime = `${date} ${String(newHours).padStart(2, '0')}:${String(newMinutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
                            setVirtualTime(newTime);
                            return newTime;
                        }
                    },
                    getUpdateTimeRange: function(lastRequestTime, currentTime) {
                        // 模拟模式：使用虚拟时间
                        return {
                            start: lastRequestTime,  // 从上次结束时间开始
                            end: currentTime
                        };
                    },
                    buildUrl: function(symbol, tickRange) {
                        let url = `/api/v1/intraday/mock?symbol=${encodeURIComponent(symbol.id)}&trading_phase=${mock_trading_phase}`;
    
                        // 🔧 传递last_price（用于保证价格连续性）
                        const intradayData = getData();
                        if (intradayData && intradayData.current_price) {
                            url += `&last_price=${intradayData.current_price}`;
                        }
    
                        if (tickRange) {
                            url += `&tick_range=${encodeURIComponent(JSON.stringify(tickRange))}`;
                        }
    
                        return url;
                    },
                    shouldGenerateTickRange: mock_trading_phase === 'trading', // 属性而不是方法
                    shouldRecordFullTimestamp: false
                };
            }else{
                return {
                    pollInterval: 1000,
                    setupInitialState: function() {
                        // 真实模式下不需要特殊初始化
                    },
                    getCurrentTime: function(isInitial) {
                        // 📊 真实模式：使用系统实际时间
                        return Math.floor(Date.now() / 1000);  // 当前时间（秒）
                    },
                    getUpdateTimeRange: function(lastRequestTime, currentTime) {
                        // 🔧 真实模式：使用市场时间，而不是浏览器时间
                        // 应该从后端API获取准确的市场时间，暂时使用服务器时间
                        marketTimezone=AppUtils.getMarketTimezone(current_market_code);
                        const marketDateTimeStr = AppUtils.formatToMarketDateTimeStr(new Date(), marketTimezone);
                        const dateStr = AppUtils.extractFromDateStr(marketDateTimeStr, marketTimezone);  // YYYY-MM-DD
                        const timeStr = AppUtils.extractFromTimeStr(marketDateTimeStr, marketTimezone); // HH:MM:SS
                        const newEndTime = `${dateStr} ${timeStr}`;
    
                        // 如果有lastRequestTime，使用它；否则使用开盘时间
                        let newStartTime;
                        if (lastRequestTime) {
                            newStartTime = lastRequestTime;
                        } else {
                            // 首次增量更新，从开盘到现在
                            // 根据当前市场代码获取正确的开盘时间
                            const marketConfig = window.marketConfig || {};
                            const marketInfo = marketConfig[current_market_code];
    
                            if (marketInfo && marketInfo.trading_hours) {
                                // 解析交易时间字符串，获取开盘时间
                                const tradingHours = AppUtils.parseTradingHoursString(marketInfo.trading_hours);
                                if (tradingHours && tradingHours.open) {
                                    newStartTime = `${dateStr} ${tradingHours.open}`;
                                } else {
                                    // 如果解析失败，抛出异常
                                    console.error(`❌解析市场 ${current_market_code} 交易时间失败，无法获取开盘时间`);
                                    throw new Error(`解析市场 ${current_market_code} 交易时间失败，无法获取开盘时间`);
                                }
                            } else {
                                // 如果没有市场配置，抛出异常
                                console.error(`❌无法获取市场 ${current_market_code} 的配置信息`);
                                throw new Error(`无法获取市场 ${current_market_code} 的配置信息`);
                            }
                        }
    
                        return {
                            start: newStartTime,
                            end: newEndTime
                        };
                    },
                    buildUrl: function(symbol, tickRange) {
                        let url = `/api/v1/intraday/data?symbol=${encodeURIComponent(symbol.id)}`;
    
                        if (tickRange) {
                            url += `&tick_range=${encodeURIComponent(JSON.stringify(tickRange))}`;
                        }
    
                        return url;
                    },
                    shouldGenerateTickRange: !isInitial && lastRequestTime, // 属性而不是方法
                    shouldRecordFullTimestamp: true
                };
        }
    }
    
    function getFullTradingTimesInternal() {
       // 优先使用统一的全局配置对象
        const market = window.marketConfig?.[current_market_code.toUpperCase()] ||
                       window.marketsConfig?.find(m => m.code.toUpperCase() === current_market_code.toUpperCase()) ||
                       (window.marketsConfig && typeof window.marketsConfig === 'object' ?
                        window.marketsConfig[current_market_code.toUpperCase()] : null);
    
        if (!market) {
            console.error(`❌ 未找到市场 ${current_market_code} 的配置，无法生成时间轴`)
            throw new Error(`未找到市场 ${current_market_code} 的配置，无法生成时间轴`)
        }
        // 检查 window.marketTradingTimes 是否已正确初始化
        if (typeof window.marketTradingTimes === 'undefined') {
            window.marketTradingTimes = {};
        }
    
        // 返回缓存的时间轴（包含午休范围信息）
        if (window.marketTradingTimes[current_market_code]) {
            return window.marketTradingTimes[current_market_code]
        }
    
        // 解构市场配置 - 根据配置格式处理
        const tradingHours = market.detailed_trading_hours ||
                        (market.trading_hours ? AppUtils.parseTradingHoursString(market.trading_hours) : {});
    
        const { open, close, lunch_start, lunch_end } = tradingHours;
    
        if (!open || !close) {
            console.error(`❌ 市场 ${current_market_code} 缺少交易时间配置，无法生成时间轴`)
            throw new Error(`市场 ${current_market_code} 缺少交易时间配置，无法生成时间轴`)
        }
    
        // 🔧 返回包含午休范围信息的时间轴
        let result = {
            tradingTimes: [],
            lunchBreakRange: null
        }
        // 解析开始和结束时间
        const start = open.split(':').map(Number)
        const end = close.split(':').map(Number)
    
        if (lunch_start && lunch_end) {
            const firstEnd = lunch_start.split(':').map(Number)
            const secondStart = lunch_end.split(':').map(Number)
            result = generateTradingTimesWithLunchBreak(result.tradingTimes, start, firstEnd, secondStart, end)
        } else {
            result.tradingTimes = generateTradingTimes(result.tradingTimes, start, end)
        }
        window.marketTradingTimes[current_market_code] = result
        return result
    }
    
    function makeLunchBreakLine() {
        // 如果有午休时间，则添加午休分割线
        const upperMarketCode = current_market_code?.toUpperCase()
        console.log('🔍 makeLunchBreakLine - 当前市场代码:', upperMarketCode)
    
        const market = window.marketConfig[upperMarketCode] || {}
        console.log('🔍 makeLunchBreakLine - 市场配置:', market)
    
        const { lunch_start, lunch_end } = market.detailed_trading_hours || {}
        console.log('🔍 makeLunchBreakLine - 午休时间:', { lunch_start, lunch_end })
    
        const markLineData = []
        if (lunch_start && lunch_end) {
            // 确保午休时间格式与数据时间格式一致
            const lunchStartTime = lunch_start + ':00'
            const lunchEndTime = lunch_end + ':00'
    
            console.log('🔍 makeLunchBreakLine - 生成分割线:', lunchStartTime, lunchEndTime)
    
            // 只添加两条分割线，中间的空白间隔由时间轴的null数据自然形成
            markLineData.push(
                {
                    id: 'lunch-start-line',  // 设置唯一ID用于识别
                    // 午休开始分割线
                    xAxis: lunchStartTime,
                    label: {
                        show: false,
                    },
                    lineStyle: {
                        color: '#000000',  // 黑色线条
                        type: 'dashed',
                        width: 1  // 细线
                    }
                },
                {
                    id: 'lunch-end-line',  // 设置唯一ID用于识别
                    // 午休结束分割线
                    xAxis: lunchEndTime,
                    label: {
                        show: false,
                    },
                    lineStyle: {
                        color: '#000000',  // 黑色线条
                        type: 'dashed',
                        width: 1  // 细线
                    }
                }
            )
        } else {
            console.log('🔍 makeLunchBreakLine - 无午休时间，返回空数组')
        }
    
        console.log('🔍 makeLunchBreakLine - 返回数据:', markLineData)
        return markLineData
    }
    /**
     * 🔥 彻底重建分时图布局（从最外层容器开始重建）
     * @param {boolean} isStock - 是否是股票（true=股票，左右布局; false=指数，单列布局）
     */
    function rebuildLayout(isStock=false) {
        const container = document.getElementById('intradayContainer')
        if (!container) {
            console.error('❌ 找不到分时图容器')
            return
        }
        container.innerHTML=''
        // 🔧 5. 根据类型重建布局
        if (isStock) {
            // 股票：左右布局（左侧图表 + 右侧盘口/成交）
            container.innerHTML += `
                <div style="display:grid; grid-template-columns: 2fr 1fr; gap:12px; width:100%;">
                    <!-- 左侧：分时曲线+成交量容器 -->
                    <div style="min-width:0; overflow:hidden; display:flex; flex-direction:column;">
                        <div id="intradayPriceChart" style="height:360px; width:100%;"></div>
                        <div id="intradayVolumeChart" style="height:180px; width:100%; margin-top:8px;"></div>
                    </div>
                    <!-- 右侧：挂单+成交明细 -->
                    <div style="min-width:0; overflow:hidden;">
                        <div style="height:280px; border:1px solid #e5e7eb; border-radius:6px; padding:8px; overflow-y:auto;">
                            <div style="font-size:12px; font-weight:600; margin-bottom:8px; color:#374151;">买卖盘口</div>
                            <table style="width:100%; font-size:11px;">
                                <thead style="background:#f9fafb;">
                                    <tr>
                                        <th style="padding:4px; text-align:left; width:25%;"></th>
                                        <th style="padding:4px; text-align:center; width:40%;">价格</th>
                                        <th style="padding:4px; text-align:right; width:35%;">数量</th>
                                    </tr>
                                </thead>
                                <tbody id="orderBookBody"></tbody>
                            </table>
                        </div>
                        <div style="height:140px; margin-top:8px; border:1px solid #e5e7eb; border-radius:6px; padding:8px; overflow-y:auto;">
                            <div style="font-size:12px; font-weight:600; margin-bottom:8px; color:#374151;">成交明细</div>
                            <div id="tickerList" style="font-size:11px;"></div>
                        </div>
                    </div>
                </div>
            `
        } else {
            // 指数：单列布局（只有图表）
            container.innerHTML += `
                <div style="display:flex; flex-direction:column;">
                    <div id="intradayPriceChart" style="height:360px; width:100%;"></div>
                    <div id="intradayVolumeChart" style="height:180px; width:100%; margin-top:8px;"></div>
                </div>
            `
        }

        // 🔧 6. 重新初始化图表实例
        const priceChartDom = document.getElementById('intradayPriceChart')
        const volumeChartDom = document.getElementById('intradayVolumeChart')

        if (priceChartDom && volumeChartDom) {
            intradayPriceChart = echarts.init(priceChartDom)
            intradayVolumeChart = echarts.init(volumeChartDom)
            // 连接两个图表，确保 tooltip 同步
            echarts.connect([intradayPriceChart, intradayVolumeChart])
            // 显示分时图相关元素
                    // 🔧 布局变化后，需要 resize 图表
            setTimeout(() => {
                const charts = getCharts()
                if (charts.price) charts.price.resize()
                if (charts.volume) charts.volume.resize()
            }, 50)
            document.getElementById('klineContainer').style.display = 'none'
            document.getElementById('intradayContainer').style.display = 'block'
        } else {
            console.error('❌ 无法找到图表DOM元素')
        }
    }



    /**
     * 显示/隐藏分时图加载状态
     */
    function showLoading(show) {
        if (!intradayPriceChart || !intradayVolumeChart) return

        // 使用通用的加载状态函数
        AppUtils.showChartLoading(intradayPriceChart, show, '加载中...');
        AppUtils.showChartLoading(intradayVolumeChart, show, '加载中...');
    }

    // 🔧 删除：isTradingTime() - 前端不再判断交易时段，完全依赖后端 should_poll
    // 原因：所有控制前端行为的参数必须来自后端

    /**
     * 根据市场配置动态生成时间轴标签配置
     * @param {Array} fullTradingTimes - 完整的交易时间数组
     * @returns {Object} - ECharts x轴标签配置对象
     */
    function generateTimeAxisLabelConfig(fullTradingTimes) {
        // 获取市场配置
        const market = window.marketConfig?.[current_market_code?.toUpperCase()] ||
                       window.marketsConfig?.find(m => m.code.toUpperCase() === current_market_code?.toUpperCase());

        const tradingHours = market?.detailed_trading_hours || {};
        const { open, close, lunch_start, lunch_end } = tradingHours;

        // 解析时间
        const [openHour, openMin] = open?.split(':').map(Number)|| [undefined, undefined];
        const [closeHour, closeMin] = close?.split(':').map(Number)|| [undefined, undefined];
        const [lunchStartHour, lunchStartMin] = lunch_start?.split(':').map(Number) || [undefined, undefined];
        const [lunchEndHour, lunchEndMin] = lunch_end?.split(':').map(Number)|| [undefined, undefined];
        // 🔧 动态生成半小时时间点
        const displayTimes = new Set();

        // 从开盘时间开始，每30分钟生成一个时间点，直到收盘
        let currentHour = openHour;
        let currentMinute = openMin;

        while (currentHour < closeHour || (currentHour === closeHour && currentMinute <= closeMin)) {
            const timeStr = `${String(currentHour).padStart(2, '0')}:${String(currentMinute).padStart(2, '0')}:00`;
            displayTimes.add(timeStr);

            // 记录当前时间，用于判断是否遇到午休开始
            const prevHour = currentHour;
            const prevMinute = currentMinute;

            // 添加30分钟
            currentMinute += 30;
            if (currentMinute >= 60) {
                currentMinute -= 60;
                currentHour += 1;
            }

            // 🔧 如果遇到午休开始时间，先添加午休开始时间，然后跳到午休结束时间

            if (prevHour === lunchStartHour && prevMinute === lunchStartMin) {
                // 确保午休开始时间已添加（已在上面的displayTimes.add中添加）
                // 跳到午休结束时间
                currentHour = lunchEndHour;
                currentMinute = lunchEndMin;
            }
        }

        // 确保收盘时间显示，但排除午休结束时间
        const closeTimeStr = `${String(closeHour).padStart(2, '0')}:${String(closeMin).padStart(2, '0')}:00`;
        displayTimes.add(closeTimeStr);
        // 从显示时间集合中移除午休结束时间（如果存在）
        if(lunchEndHour!=undefined && lunchEndMin!=undefined){
            const lunchEndTimeStr = `${String(lunchEndHour).padStart(2, '0')}:${String(lunchEndMin).padStart(2, '0')}:00`;
            displayTimes.delete(lunchEndTimeStr);
        }
        console.log('🔍 动态生成的时间点:', Array.from(displayTimes).sort());

        // 🔧 创建自定义的 formatter，只显示指定的时间点
        return {
            interval: 0,  // 显示所有标签，由 formatter 控制哪些显示
            formatter: function(value, index) {
                // 只显示指定的时间点，其他时间返回空字符串
                if (displayTimes.has(value)) {
                    return window.AppUtils.formatTimeAxisLabel(value);
                }
                return '';
            },
            showMinLabel: true,
            showMaxLabel: true
        };
    }

    /**
     * 显示图表加载状态（通用函数）
     */


    /**
     * 显示分时图错误信息
     */
    function showError(message) {
        showLoading(false)

        // 在图表上显示错误
        const errorOption = {
            title: {
                text: '加载失败',
                subtext: message,
                left: 'center',
                top: 'center',
                textStyle: { fontSize: 16, color: '#ef4444' },
                subtextStyle: { fontSize: 12, color: '#9ca3af' }
            },
            xAxis: { show: false },
            yAxis: { show: false },
            series: []
        }

        intradayPriceChart.setOption(errorOption, true)
        intradayVolumeChart.setOption(errorOption, true)

        // 盘口和成交明细显示错误
        const tbody = document.getElementById('orderBookBody')
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="3" style="text-align:center; padding:20px; color:#ef4444;">${message}</td></tr>`
        }

        const tickerList = document.getElementById('tickerList')
        if (tickerList) {
            tickerList.innerHTML = `<div style="text-align:center; padding:20px; color:#ef4444;">${message}</div>`
        }
    }

    function generateTradingTimes(tradingTimes,start,end,stepSeconds = 5) {
        if (!tradingTimes) {
            tradingTimes = []
        }

        // 将开始和结束时间转换为总秒数（从当天00:00:00开始计算）
        const startTotalSeconds = start[0] * 3600 + start[1] * 60;
        const endTotalSeconds = end[0] * 3600 + end[1] * 60; // 结束时间是XX:XX:00

        // 循环从开始时间到结束时间，按stepSeconds步长递增
        for (let totalSeconds = startTotalSeconds; totalSeconds <= endTotalSeconds; totalSeconds += stepSeconds) {
            // 将总秒数转换回时、分、秒
            const hour = Math.floor(totalSeconds / 3600);
            const minute = Math.floor((totalSeconds % 3600) / 60);
            const second = totalSeconds % 60;

            // 检查是否超出结束时间
            if (hour > end[0] || (hour === end[0] && minute > end[1])) continue;

            const timeStr = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:${String(second).padStart(2, '0')}`;

            // 避免重复添加时间点
            if (!tradingTimes.includes(timeStr)) {
                tradingTimes.push(timeStr);
            }
        }

        return tradingTimes
    }

    /**
     * 初始化分时图时间轴
     */
    function initializeIntradayTimeAxis() {
        if (!current_market_code) {
            console.warn('⚠️ 当前市场代码未设置，无法初始化时间轴')
            return
        }
        console.log('🔍 initializeIntradayTimeAxis - 当前市场:', current_market_code)
        // 生成当前市场的完整交易时间轴
        const timeAxisInfo = getFullTradingTimes()
        const fullTradingTimes = timeAxisInfo.tradingTimes
        const lunchBreakRange = timeAxisInfo.lunchBreakRange
        console.log('🔍 initializeIntradayTimeAxis - 时间轴长度:', fullTradingTimes.length, '午休范围:', lunchBreakRange)

        // 🔧 根据市场配置动态生成半小时时间点
        const axisLabelConfig = generateTimeAxisLabelConfig(fullTradingTimes)

        // 设置图表的基础配置（与具体股票无关的时间轴和分割线）
        const charts = getCharts()
        console.log('🔍 initializeIntradayTimeAxis - 图表实例:', charts)

        if (charts.price && charts.volume) {
            // 准备基础markLine配置（用于午休分割线等）
            const markLineData = makeLunchBreakLine()
            console.log('🔍 initializeIntradayTimeAxis - markLineData:', markLineData)

            // 为价格图表设置完整的基础配置
            charts.price.setOption({
                // 标题配置占位（数据相关部分在renderIntradayCharts中设置）
                title: {
                    text: '',
                    left: 'center',
                    textStyle: { fontSize: 14 },
                    subtext: '',
                    subtextStyle: { fontSize: 11 }
                },
                // tooltip配置
                tooltip: {
                    trigger: 'axis',
                    formatter: function(params) {
                        let result = params[0].axisValue + '<br/>'
                        params.forEach(item => {
                            // 处理null值
                            if (item.value === null || item.value === undefined) {
                                return
                            }
                            const value = parseFloat(item.value)
                            result += item.marker + item.seriesName + ': ' + value.toFixed(2) + '<br/>'
                        })
                        return result
                    }
                },
                // 网格配置
                grid: { left: '50px', right: '50px', top: '60px', bottom: '30px' },
                // x轴配置（时间轴）
                xAxis: {
                    type: 'category',
                    data: fullTradingTimes,  // 使用全局初始化的时间轴
                    boundaryGap: false,
                    axisLabel: axisLabelConfig  // 🔧 使用动态计算的刻度配置
                },
                // y轴配置
                yAxis: {
                    type: 'value',
                    scale: true,
                    splitLine: {
                        lineStyle: { type: 'dashed', color: '#e5e7eb' }
                    },
                    axisLine: { onZero: false }
                },
                // 系列配置（基础结构）
                series: [
                    {
                        name: '价格',
                        type: 'line',
                        data: [],  // 初始为空，等待 renderCharts 填充
                        smooth: 0.6,
                        symbol: 'none',
                        showSymbol: false,
                        lineStyle: { width: 2 },
                        itemStyle: { color: '#2563eb' },
                        areaStyle: {
                            color: {
                                type: 'linear',
                                x: 0, y: 0, x2: 0, y2: 1,
                                colorStops: [
                                    { offset: 0, color: 'rgba(37, 99, 235, 0.3)' },
                                    { offset: 1, color: 'rgba(37, 99, 235, 0.05)' }
                                ]
                            }
                        },
                        connectNulls: true,
                        markLine: {
                            symbol: 'none',
                            silent: false,
                            animation: false,
                            data: markLineData  // 午休分割线
                        }
                    },
                    {
                        name: '均价',
                        type: 'line',
                        data: [],  // 初始为空，等待 renderCharts 填充
                        smooth: 0.6,
                        symbol: 'none',
                        showSymbol: false,
                        lineStyle: { width: 1.5, color: '#f59e0b', type: 'dashed' },
                        connectNulls: true
                    }
                ]
            }, true)  // 关键：使用true完全替换，清除旧市场配置

            // 为成交量图表设置完整的基础配置
            charts.volume.setOption({
                // 标题配置
                title: {
                    text: '成交量',
                    left: 'center',
                    textStyle: { fontSize: 12 }
                },
                // tooltip配置
                tooltip: {
                    trigger: 'axis',
                    formatter: function(params) {
                        if (!params || params.length === 0) return ''
                        const volume = params[0].value
                        // 处理null值
                        if (volume === null || volume === undefined) {
                            return params[0].axisValue + '<br/>' + params[0].marker + '成交量: 无数据'
                        }
                        return params[0].axisValue + '<br/>' + params[0].marker + '成交量: ' + volume.toLocaleString() + '手'
                    }
                },
                // 网格配置
                grid: { left: '50px', right: '50px', top: '40px', bottom: '20px' },
                // x轴配置（时间轴）
                xAxis: {
                    type: 'category',
                    data: fullTradingTimes,
                    show: false,
                    axisLabel: axisLabelConfig  // 🔧 使用相同的刻度配置
                },
                // y轴配置
                yAxis: {
                    type: 'value',
                    splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } }
                },
                // 系列配置（基础结构）
                series: [{
                    name: '成交量',
                    type: 'bar',
                    data: [],  // 初始为空，等待 renderCharts 填充
                    barWidth: '80%',
                    markLine: {
                        symbol: 'none',
                        silent: false,
                        animation: false,
                        data: markLineData  // 合并后的markLine数据（包含午休分割线和保留的其他线）
                    }
                }]
            }, true)  // 关键：使用true完全替换，清除旧市场配置
            showLoading(true)
        }
    }

    /**
     * 根据市场配置生成完整交易时段的时间轴
     * @returns {Object} 包含tradingTimes和lunchBreakRange的对象
     */
    function getFullTradingTimes() {
       // 优先使用统一的全局配置对象
        const market = window.marketConfig?.[current_market_code.toUpperCase()] ||
                       window.marketsConfig?.find(m => m.code.toUpperCase() === current_market_code.toUpperCase()) ||
                       (window.marketsConfig && typeof window.marketsConfig === 'object' ?
                        window.marketsConfig[current_market_code.toUpperCase()] : null);

        if (!market) {
            console.error(`❌ 未找到市场 ${current_market_code} 的配置，无法生成时间轴`)
            throw new Error(`未找到市场 ${current_market_code} 的配置，无法生成时间轴`)
        }
        // 检查 window.marketTradingTimes 是否已正确初始化
        if (typeof window.marketTradingTimes === 'undefined') {
            window.marketTradingTimes = {};
        }

        // 返回缓存的时间轴（包含午休范围信息）
        if (window.marketTradingTimes[current_market_code]) {
            return window.marketTradingTimes[current_market_code]
        }

        // 解构市场配置 - 根据配置格式处理
        const tradingHours = market.detailed_trading_hours ||
                        (market.trading_hours ? AppUtils.parseTradingHoursString(market.trading_hours) : {});

        const { open, close, lunch_start, lunch_end } = tradingHours;

        if (!open || !close) {
            console.error(`❌ 市场 ${current_market_code} 缺少交易时间配置，无法生成时间轴`)
            throw new Error(`市场 ${current_market_code} 缺少交易时间配置，无法生成时间轴`)
        }

        // 🔧 返回包含午休范围信息的时间轴
        let result = {
            tradingTimes: [],
            lunchBreakRange: null
        }
        // 解析开始和结束时间
        const start = open.split(':').map(Number)
        const end = close.split(':').map(Number)

        if (lunch_start && lunch_end) {
            const firstEnd = lunch_start.split(':').map(Number)
            const secondStart = lunch_end.split(':').map(Number)
            result = generateTradingTimesWithLunchBreak(result.tradingTimes, start, firstEnd, secondStart, end)
        } else {
            result.tradingTimes = generateTradingTimes(result.tradingTimes, start, end)
        }
        window.marketTradingTimes[current_market_code] = result
        return result
    }

    /**
     * 渲染分时图表
     * @param {Object} data - 分时图数据
     */
    function renderCharts(data, marketTimezone) {
        if (!data) {
            console.error('❌ renderCharts: 数据为null')
            return
        }

        // 🔧 关键修复：盘前时段（times为空）也要渲染空的图表框架
        const hasTicks = data.times && data.times.length > 0
        if (!hasTicks) {
            console.log('🕒 盘前或无数据时段，渲染空的分时图框架')
        }

        const yesterdayClose = parseFloat(data.yesterday_close)
        const currentPrice = parseFloat(data.current_price)
        const change = parseFloat(data.change)
        const changePercent = parseFloat(data.change_percent)

        const timeAxisInfo = getFullTradingTimes()
        const fullTradingTimes = timeAxisInfo.tradingTimes
        const lunchBreakRange = timeAxisInfo.lunchBreakRange

        // 重新初始化数据数组长度以匹配时间轴
        const priceData = new Array(fullTradingTimes.length).fill(null)
        const avgPriceData = new Array(fullTradingTimes.length).fill(null)
        const volumeData = new Array(fullTradingTimes.length).fill(null)

        // 🔧 关键修复：只有hasTicks为true时才映射数据（盘前为空）
        if (hasTicks) {
            data.times.forEach((time, idx) => {
                const timeIndex = fullTradingTimes.indexOf(time)
                if (timeIndex !== -1) {
                    // 🔧 关键修复：强制转换为数字类型，并验证有效性
                    const price = parseFloat(data.prices[idx])
                    const avgPrice = parseFloat(data.avg_prices[idx])
                    const volume = parseInt(data.volumes[idx])

                    // 只有有效数字才赋值
                    if (!isNaN(price) && isFinite(price)) {
                        priceData[timeIndex] = price
                    }
                    if (!isNaN(avgPrice) && isFinite(avgPrice)) {
                        avgPriceData[timeIndex] = avgPrice
                    }
                    if (!isNaN(volume) && isFinite(volume)) {
                        volumeData[timeIndex] = volume
                    }
                }
            })
        }

        const charts = getCharts()

        if (!charts.price) {
            console.error('❌ 价格图表实例为空，无法渲染！')
            return
        }
        if (!charts.volume) {
            console.error('❌ 成交量图表实例为空，无法渲染！')
            return
        }

        // 🔧 优化markLine数据处理：获取现有配置并添加/更新昨收线
        const markLineData = updateMarkLineWithYesterdayClose(charts.price, yesterdayClose)

        console.log('🔍 renderCharts - markLineData长度:', markLineData.length)

        // 更新价格图表（只设置数据相关的配置）
        charts.price.setOption({
            title: {
                text: (symbol ? symbol.name : '') + ' 分时图 (' + AppUtils.formatToMarketDateTimeStr(new Date(), marketTimezone) + ')',
                subtext: `昨收: ${yesterdayClose.toFixed(2)}  现价: ${currentPrice.toFixed(2)}  涨跌: ${change >= 0 ? '+' : ''}${change.toFixed(2)} (${changePercent.toFixed(2)}%)`,
                subtextStyle: {
                    color: change >= 0 ? '#ef4444' : '#10b981'
                }
            },
            tooltip: {
                formatter: function(params) {
                    let result = params[0].axisValue + '<br/>'
                    params.forEach(item => {
                        // 处理null值
                        if (item.value === null || item.value === undefined) {
                            return
                        }
                        const value = parseFloat(item.value)
                        const change = value - yesterdayClose
                        const changePercent = ((change / yesterdayClose) * 100).toFixed(2)
                        result += item.marker + item.seriesName + ': ' + value.toFixed(2) + ' (' + (change >= 0 ? '+' : '') + change.toFixed(2) + ' ' + changePercent + '%)<br/>'
                    })
                    return result
                }
            },
            series: [
                {
                    data: priceData,
                    markLine: {
                        symbol: 'none',
                        silent: false,
                        animation: false,
                        data: markLineData  // 重新设置markLine数据，包含午休分割线和昨收线
                    }
                },
                { data: avgPriceData }
            ]
        })

        // 更新成交量图表
        charts.volume.setOption({
            title: {
                subtext: `成交量: ${data.total_volume || 0}`,
                left: 'center',
                textStyle: { fontSize: 11 }
            },
            series: [{
                data: volumeData
            }]
        })
        showLoading(false)
    }

    /**
     * 增量更新分时图表
     * @param {Object} newData - 新的分时图数据
     */
    function updateChartsIncremental(newData, marketTimezone) {
        if (!intradayData || !newData) return

        // 🔧 关键：昨收价格从首次加载的 intradayData 中获取，不使用 newData
        const yesterdayClose = parseFloat(intradayData.yesterday_close)

        const hasNewData = newData.times && newData.times.length > 0

        let currentPrice, change, changePercent
        if (hasNewData) {
            // 有新数据：使用 newData 的价格
            currentPrice = parseFloat(newData.current_price)
            change = parseFloat(newData.change)
            changePercent = parseFloat(newData.change_percent)
        } else {
            // 无新数据：保持 intradayData 的原价格
            currentPrice = parseFloat(intradayData.current_price)
            change = parseFloat(intradayData.change)
            changePercent = parseFloat(intradayData.change_percent)
            console.log('⚠️ 增量更新无新数据，保持原价格:', currentPrice)
        }

        // 🔧 生成完整交易时段（与 renderCharts 相同，5秒级别）
        // 🔧 使用统一的 getFullTradingTimes 函数，避免重复逻辑和时间计算错误
        const timeAxisInfo = getFullTradingTimes() || { tradingTimes: [] }
        const fullTradingTimes = timeAxisInfo.tradingTimes
        const lunchBreakRange = timeAxisInfo.lunchBreakRange

        if (hasNewData) {
            newData.times.forEach((time, idx) => {
                // 检查是否已存在（避免重复）
                if (!intradayData.times.includes(time)) {
                    intradayData.times.push(time)
                    intradayData.prices.push(newData.prices[idx])
                    intradayData.avg_prices.push(newData.avg_prices[idx])
                    intradayData.volumes.push(newData.volumes[idx])
                }
            })
        }

        const priceData = new Array(fullTradingTimes.length).fill(null)
        const avgPriceData = new Array(fullTradingTimes.length).fill(null)
        const volumeData = new Array(fullTradingTimes.length).fill(null)

        intradayData.times.forEach((time, idx) => {
            const timeIndex = fullTradingTimes.indexOf(time)
            if (timeIndex !== -1) {
                priceData[timeIndex] = intradayData.prices[idx]
                avgPriceData[timeIndex] = intradayData.avg_prices[idx]
                volumeData[timeIndex] = intradayData.volumes[idx]
            }
        })

        // 获取已有的markLine配置，避免重复创建基础分割线
        const charts = getCharts()
        if (!charts.price || !charts.volume) {
            console.error('❌ 图表实例为空，无法更新！')
            return
        }

        // 使用优化的markLine数据处理方法更新昨收线
        const markLineData = updateMarkLineWithYesterdayClose(charts.price, yesterdayClose)

        // 更新价格图表
        charts.price.setOption({
            title: {
                subtext: `昨收: ${yesterdayClose.toFixed(2)}  现价: ${currentPrice.toFixed(2)}  涨跌: ${change >= 0 ? '+' : ''}${change.toFixed(2)} (${changePercent.toFixed(2)}%)`,
                subtextStyle: {
                    fontSize: 11,
                    color: change >= 0 ? '#ef4444' : '#10b981'
                }
            },
            series: [
                {
                    data: priceData,
                    markLine: {
                        symbol: 'none',
                        silent: false,
                        animation: false,
                        data: markLineData  // 使用优化后的markLine数据
                    }
                },
                { data: avgPriceData }
            ]
        })

        // 更新成交量图表
        charts.volume.setOption({
            series: [{
                data: volumeData
            }]
        })
    }

    /**
     * 创建午休分割线
     * @returns {Array} markLine数据
     */
    function makeLunchBreakLine() {
        // 如果有午休时间，则添加午休分割线
        const upperMarketCode = current_market_code?.toUpperCase()
        console.log('🔍 makeLunchBreakLine - 当前市场代码:', upperMarketCode)

        const market = window.marketConfig[upperMarketCode] || {}
        console.log('🔍 makeLunchBreakLine - 市场配置:', market)

        const { lunch_start, lunch_end } = market.detailed_trading_hours || {}
        console.log('🔍 makeLunchBreakLine - 午休时间:', { lunch_start, lunch_end })

        const markLineData = []
        if (lunch_start && lunch_end) {
            // 确保午休时间格式与数据时间格式一致
            const lunchStartTime = lunch_start + ':00'
            const lunchEndTime = lunch_end + ':00'

            console.log('🔍 makeLunchBreakLine - 生成分割线:', lunchStartTime, lunchEndTime)

            // 只添加两条分割线，中间的空白间隔由时间轴的null数据自然形成
            markLineData.push(
                {
                    id: 'lunch-start-line',  // 设置唯一ID用于识别
                    // 午休开始分割线
                    xAxis: lunchStartTime,
                    label: {
                        show: false,
                    },
                    lineStyle: {
                        color: '#000000',  // 黑色线条
                        type: 'dashed',
                        width: 1  // 细线
                    }
                },
                {
                    id: 'lunch-end-line',  // 设置唯一ID用于识别
                    // 午休结束分割线
                    xAxis: lunchEndTime,
                    label: {
                        show: false,
                    },
                    lineStyle: {
                        color: '#000000',  // 黑色线条
                        type: 'dashed',
                        width: 1  // 细线
                    }
                }
            )
        } else {
            console.log('🔍 makeLunchBreakLine - 无午休时间，返回空数组')
        }

        console.log('🔍 makeLunchBreakLine - 返回数据:', markLineData)
        return markLineData
    }

    /**
     * 优化的markLine数据处理：获取现有配置并添加/更新昨收线
     * @param {Object} chart - ECharts实例
     * @param {number} yesterdayClose - 昨收价
     * @returns {Array} 更新后的markLine数据
     */
    function updateMarkLineWithYesterdayClose(chart, yesterdayClose) {
        // 获取现有的markLine配置
        const existingOption = chart.getOption();
        let existingMarkLineData = [];

        if (existingOption.series && existingOption.series[0] &&
            existingOption.series[0].markLine && existingOption.series[0].markLine.data) {
            existingMarkLineData = existingOption.series[0].markLine.data;
        }

        // 过滤掉旧的昨收线（通过ID识别），保留其他markLine元素
        const filteredMarkLineData = existingMarkLineData.filter(line => line.id !== 'yesterday-close-line');

        // 添加新的昨收线（带有ID便于后续更新或删除）
        const yesterdayCloseLine = {
            id: 'yesterday-close-line',  // 设置唯一ID用于识别
            // 昨收横线（股票相关的分割线）
            yAxis: yesterdayClose,
            label: {
                show: true,
                formatter: '昨收: {c}',
                position: 'end',
                color: '#000000',  // 黑色文字
                fontSize: 12,
                fontWeight: 'bold'
            },
            lineStyle: {
                color: '#000000',  // 黑色线条
                type: 'dashed',
                width: 1,  // 细线
                opacity: 1.0
            },
            z: 100  // 确保在最上层
        };

        // 合并过滤后的现有数据和新的昨收线
        return [...filteredMarkLineData, yesterdayCloseLine];
    }

    /**
     * 提取午休时间段处理逻辑为独立方法
     * @param {Array} tradingTimes - 当前的交易时间数组
     * @param {Array} firstStart - 上午开始时间 [小时, 分钟]
     * @param {Array} firstEnd - 上午结束时间/午休开始时间 [小时, 分钟]
     * @param {Array} secondStart - 下午开始时间/午休结束时间 [小时, 分钟]
     * @param {Array} secondEnd - 下午结束时间 [小时, 分钟]
     * @returns {Object} 包含更新后的tradingTimes和lunchBreakRange的对象
     */
    function generateTradingTimesWithLunchBreak(tradingTimes, firstStart, firstEnd, secondStart, secondEnd) {
        let updatedTradingTimes = [...tradingTimes];
        let lunchBreakRange = null;

        // 生成上午交易时段（5秒间隔）
        updatedTradingTimes = generateTradingTimes(updatedTradingTimes, firstStart, firstEnd);

        // 🔧 记录午休时间段的开始索引
        const lunchStartIndex = updatedTradingTimes.length;

        // 🔧 使用 generateTradingTimes 生成午休时间段（5分钟间隔）
        updatedTradingTimes = generateTradingTimes(updatedTradingTimes, firstEnd, secondStart, 600);  // 从firstEnd到secondStart是午休时间

        // 🔧 记录午休时间段的结束索引
        const lunchEndIndex = updatedTradingTimes.length - 1;

        // 🔧 保存午休时间段范围
        lunchBreakRange = { start: lunchStartIndex, end: lunchEndIndex };

        console.log('🔍 getFullTradingTimes - 午休间隔已生成，范围:', lunchStartIndex, lunchEndIndex);

        // 生成下午交易时段（5秒间隔）
        updatedTradingTimes = generateTradingTimes(updatedTradingTimes, secondStart, secondEnd);

        return { tradingTimes: updatedTradingTimes, lunchBreakRange };
    }


    function clearChart() {
            intradayData = null
            lastIntradayBatchIndex = 0
            lastIntradayRequestTime = 0
            virtualIntradayTime = 0  // 🎮 虚拟交易时间（秒），用于模拟模式
            symbol = null
            current_market_code = 'CN'
            use_mock_mode = false
            mock_trading_phase = 'trading'
            // 🔧 1. 停止定时器
            if (intradayUpdateTimer) {
                clearInterval(intradayUpdateTimer)
                intradayUpdateTimer = null
            }
            // 🔧 2. 销毁旧的图表实例
            if (intradayPriceChart) {
                try {
                    intradayPriceChart.dispose()
                } catch(e) {
                    console.warn('销毁价格图失败:', e)
                }
                intradayPriceChart = null
            }
            if (intradayVolumeChart) {
                try {
                    intradayVolumeChart.dispose()
                } catch(e) {
                    console.warn('销毁成交量图失败:', e)
                }
                intradayVolumeChart = null
            }
    }
    function stopIntradayUpdateTimer() {
        if (intradayUpdateTimer) {
            clearInterval(intradayUpdateTimer)
            intradayUpdateTimer = null;
        }
    }
    function startIntradayUpdateTimer() {
        stopIntradayUpdateTimer()
        const modeConfig = getModeConfig(true);
        const pollInterval = modeConfig.pollInterval;
        intradayUpdateTimer = window.setInterval(() => {
            loadData(false)
        }, pollInterval)
    }
    /**
     * 加载分时图数据
     * @param {boolean} isInitial - 是否为首次加载
     */
    function loadData(isInitial = true) {
        // 获取模式配置
        const modeConfig = getModeConfig(isInitial);
        // 🔧 只有首次加载才清空旧数据和显示加载状态
        if (isInitial) {
            setData(null)
            setBatchIndex(0)  // 重置批次序号
            setRequestTime(0)  // 重置时间
            // 设置初始状态（根据模式）
            modeConfig.setupInitialState();
            initializeIntradayTimeAxis()
        }
        showLoading(true)
        // 🔧 计算 TickRange（时间范围）
        let currentTime = modeConfig.getCurrentTime(isInitial);

        let tickRange = null
        const lastRequestTime = getRequestTime()

        let shouldGenerateTickRange = modeConfig.shouldGenerateTickRange;

        if (shouldGenerateTickRange) {
            if (isInitial) {
                // 🎯 首次加载：加载约 1 小时的数据（09:30 ~ 10:30）
                const startTime = currentTime  // 当前虚拟时间："2024-12-14 09:30:00"
                // 🔧 计算 1 小时后的时间
                const [date, time] = currentTime.split(' ')
                const [hours, minutes, seconds] = time.split(':').map(Number)
                const endHours = hours + 1  // +1小时
                const endTime = `${date} ${String(endHours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`

                tickRange = {
                    start_time: startTime,
                    end_time: endTime,
                    period_seconds: 5
                }

                setVirtualTime(endTime)
                setRequestTime(endTime)
            } else {
                // 🎯 增量更新：每次增加 1 分钟（从上次结束时间到新的结束时间）
                const lastRequestTime = getRequestTime()
                const updateTimeRange = modeConfig.getUpdateTimeRange(lastRequestTime, currentTime);
                const newStartTime = updateTimeRange.start;
                const newEndTime = updateTimeRange.end;

                tickRange = {
                    start_time: newStartTime,
                    end_time: newEndTime,
                    period_seconds: 5
                }
                setRequestTime(newEndTime)
            }
        }

        // 构建请求URL
        let url = modeConfig.buildUrl(symbol, tickRange);

        fetch(url)
            .then(r => {
                // 无论状态码如何，都尝试解析JSON
                return r.json().then(data => {
                    if (!r.ok) {
                        console.error(`❌ HTTP ${r.status}: ${r.statusText}`);
                        throw new Error(data.message || `HTTP ${r.status}: ${r.statusText}`)
                    }
                    return data
                })
            })
            .then(res => {
                if (res.status !== 'success') {
                    console.error('加载失败:', res.message)
                    if (isInitial) {
                        showError('加载失败: ' + res.message)
                    }
                    return
                }

                if (isInitial) {
                    setData(res.data)
                    marketTimezone=AppUtils.getMarketTimezone(current_market_code)
                    if (res.data.times && res.data.times.length > 0) {
                        const lastTime = res.data.times[res.data.times.length - 1]
                        if (modeConfig.shouldRecordFullTimestamp) {
                            // 根据模式配置决定是否记录完整时间戳（日期+时间）
                            const marketDateTimeStr = AppUtils.formatToMarketDateTimeStr(new Date(), marketTimezone)
                            const dateStr = AppUtils.extractFromDateStr(marketDateTimeStr, marketTimezone)  // YYYY-MM-DD
                            const lastRequestTime = `${dateStr} ${lastTime}`
                            setRequestTime(lastRequestTime)
                        }
                    }

                    renderCharts(res.data, marketTimezone)
                    stopIntradayUpdateTimer()

                    if (res.data.should_poll) {
                        startIntradayUpdateTimer()
                    }

                    // 🔧 如果不是指数，更新盘口和成交明细（等待DOM渲染完成）
                    if (!res.data.is_index) {
                        // 使用 setTimeout 确保DOM元素已经完全创建
                        setTimeout(() => {
                            updateOrderBook(res.data.order_book)
                            updateTicker(res.data.trade_records)
                        }, 50)
                    }

                    // 🔧 布局变化后，需要 resize 图表
                    setTimeout(() => {
                        const charts = getCharts()
                        if (charts.price) charts.price.resize()
                        if (charts.volume) charts.volume.resize()
                    }, 50)
                } else {
                    const intradayData = getData()
                    if (!intradayData) {
                        return
                    }

                    if (intradayData.times && intradayData.times.length > 0 &&
                        res.data.times && res.data.times.length > 0) {
                        const lastTime = intradayData.times[intradayData.times.length - 1]
                        const newLastTime = res.data.times[res.data.times.length - 1]
                        if (lastTime === newLastTime) {
                            return
                        }
                    }

                    intradayData.current_price = res.data.current_price
                    intradayData.change = res.data.change
                    intradayData.change_percent = res.data.change_percent

                    updateChartsIncremental(res.data, marketTimezone)

                    if (!res.data.is_index) {
                        updateOrderBook(res.data.order_book)
                        updateTicker(res.data.trade_records)
                    }
                }
            })
            .catch(err => {
                console.error('加载分时数据失败:', err)
                if (isInitial) {
                    showError('加载失败: ' + err.message)
                }
            })
    }

    
    // ==================== 公共接口 ====================
    window.IntradayChart = {
        // 只导出data_explorer.html中使用的函数
        setCurrent: function(currentSymbol,isStock,marketCode,useMockMode,mockTradingPhase='trading')  {
            clearChart();
            symbol = currentSymbol;
            current_market_code = marketCode;
            use_mock_mode=useMockMode;
            mock_trading_phase=mockTradingPhase;
            rebuildLayout(isStock=isStock);
            loadData(true);
        },
        stopIntradayUpdateTimer:stopIntradayUpdateTimer
    };
} // End of IntradayChart module block


