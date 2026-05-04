/**
 * K线图模块 v2 - 单实例多Grid架构
 * 职责：管理K线图的渲染、数据加载、实时更新
 *
 * 架构分层：
 *   State        - 集中状态管理
 *   Layout       - DOM 构建与布局控制
 *   ChartBuilder - ECharts option 构建
 *   DataService  - 数据加载、缓存、合并
 *   Interaction  - 事件处理与用户交互
 *   Lifecycle    - 初始化、渲染、销毁
 */

{
    // ==================== 1. State 状态层 ====================
    const State = {
        // ECharts 单实例
        chartInstance: null,

        // 数据缓存
        data: {
            kline: [],
            events: [],
            indicators: {},
            chipDistribution: {}
        },

        // UI 状态
        ui: {
            period: 'daily',
            indicator: 'VOL',
            chipVisible: false,
            chipDate: '',
            chipWidth: 180
        },

        // 运行时状态
        runtime: {
            symbol: null,
            marketCode: 'CN',
            zoom: null,
            isLoadingNewStock: false,
            useMockMode: false,
            mockTradingPhase: 'trading',
            realtimeEnabled: true,
            loadAbort: null,
            loadSequence: 0,
            isLoadingMore: false,
            hasMoreData: true,
            lastLoadPosition: -1,
            lastStartValue: -1,
            userIsMoving: false,
            movingResetTimer: null,
            isAdjustingBySystem: false,
            infiniteScrollEnabled: false,
            initialLoadComplete: false,
            realtimeTimer: null,
            currentRealtimeKline: null
        }
    }

    // ==================== 2. 工具函数 ====================

    /**
     * 计算移动平均线
     * 【高保真迁移】原始 calcMA 函数
     */
    function calcMA(klineData, period) {
        const result = []
        for (let i = 0; i < klineData.length; i++) {
            if (i < period - 1) { result.push('-'); continue }
            let sum = 0
            for (let j = i - period + 1; j <= i; j++) sum += klineData[j].close
            result.push((sum / period).toFixed(2))
        }
        return result
    }

    /**
     * 日期格式转换
     * 【高保真迁移】原始 toDisplayKlineData 函数
     */
    function toDisplayKlineData() {
        return State.data.kline.map(d => {
            let dateStr = d.date
            if (typeof dateStr === 'string' && !/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
                const marketTimezone = AppUtils.getMarketTimezone(State.runtime.marketCode)
                const marketDate = AppUtils.extractFromMarketDateTimeStr(dateStr, marketTimezone)
                dateStr = AppUtils.extractFromDateStr(
                    AppUtils.formatToMarketDateTimeStr(marketDate, marketTimezone),
                    marketTimezone
                )
            }
            return { ...d, date: dateStr }
        })
    }

    /**
     * 获取模式配置
     * 【高保真迁移】原始 getModeConfig 函数
     */
    function getModeConfig(isInitial) {
        const symbol = State.runtime.symbol
        const period = State.ui.period
        const mockPhase = State.runtime.mockTradingPhase

        if (State.runtime.useMockMode) {
            return {
                pollInterval: 3000,
                buildUrl() {
                    return `/api/v1/chart/data/mock?symbol=${encodeURIComponent(symbol?.id || '')}&period=${period}&count=120&indicators=all&trading_phase=${mockPhase}`
                },
                buildRealtimeUrl() {
                    return `/api/v1/data/kline/realtime/mock?symbol=${encodeURIComponent(symbol?.id)}&trading_phase=${mockPhase}`
                },
                buildHistoryUrl(beforeDate) {
                    return `/api/v1/chart/data/mock?symbol=${encodeURIComponent(symbol?.id)}&period=${period}&count=60&before=${beforeDate}&indicators=all&trading_phase=${mockPhase}`
                }
            }
        }
        return {
            pollInterval: 3000,
            buildUrl() {
                return `/api/v1/chart/data?symbol=${encodeURIComponent(symbol?.id || '')}&period=${period}&count=120&indicators=all`
            },
            buildRealtimeUrl() {
                return `/api/v1/data/kline/realtime?symbol=${encodeURIComponent(symbol?.id)}&period=${period}`
            },
            buildHistoryUrl(beforeDate) {
                return `/api/v1/chart/data?symbol=${encodeURIComponent(symbol?.id)}&period=${period}&count=60&before=${beforeDate}&indicators=all`
            }
        }
    }

    // ==================== 3. Layout 布局层 ====================

    const Layout = {
        build() {
            const container = document.getElementById('klineContainer')
            if (!container) {
                console.error('找不到 k线图容器')
                return
            }

            container.style.position = 'relative'
            container.innerHTML = `
                <div class="kline-wrapper" style="position:absolute; inset:0; display:flex; flex-direction:column;">
                    <div class="kline-control-bar" style="display:flex; align-items:center; gap:12px; margin-bottom:8px; flex-shrink:0;">
                        <div id="periodSelector" class="segmented-control" style="flex:1;">
                            <button class="btn btn-segment active" data-period="daily">日</button>
                            <button class="btn btn-segment" data-period="weekly">周</button>
                            <button class="btn btn-segment" data-period="monthly">月</button>
                        </div>
                        <button id="chipToggleBtn" class="btn btn-segment" title="切换筹码分布">筹码</button>
                    </div>
                    <div id="indicatorSelector" class="segmented-control" style="margin-bottom:8px; flex-shrink:0;">
                        <button class="btn btn-segment active" data-indicator="VOL">VOL</button>
                        <button class="btn btn-segment" data-indicator="MACD">MACD</button>
                        <button class="btn btn-segment" data-indicator="RSI">RSI</button>
                        <button class="btn btn-segment" data-indicator="KDJ">KDJ</button>
                        <button class="btn btn-segment" data-indicator="OBV">OBV</button>
                    </div>
                    <div style="flex:1; min-height:0; position:relative;">
                        <div id="mainChart" style="position:absolute; inset:0;"></div>
                        <div id="chipResizeHandle" style="display:none; position:absolute; top:6%; bottom:58%; width:6px; cursor:col-resize; z-index:10; background:rgba(100,100,100,0.15); border-radius:3px; transition:background 0.2s;"></div>
                    </div>
                </div>
            `

            const chartDom = document.getElementById('mainChart')
            if (chartDom) {
                State.chartInstance = echarts.init(chartDom)
                this.bindEvents()
            }

            // 显示K线容器，隐藏分时容器
            container.style.display = 'block'
            const intradayContainer = document.getElementById('intradayContainer')
            if (intradayContainer) intradayContainer.style.display = 'none'
        },

        bindEvents() {
            // 事件委托：周期切换
            const periodSelector = document.getElementById('periodSelector')
            if (periodSelector) {
                periodSelector.addEventListener('click', (e) => {
                    const btn = e.target.closest('[data-period]')
                    if (!btn) return
                    periodSelector.querySelectorAll('.btn-segment').forEach(b => b.classList.remove('active'))
                    btn.classList.add('active')
                    Interaction.onPeriodChange(btn.dataset.period)
                })
            }

            // 筹码切换
            const chipToggleBtn = document.getElementById('chipToggleBtn')
            if (chipToggleBtn) {
                chipToggleBtn.addEventListener('click', () => {
                    Interaction.toggleChip()
                })
            }

            // 指标切换（事件委托）
            const indicatorSelector = document.getElementById('indicatorSelector')
            if (indicatorSelector) {
                indicatorSelector.addEventListener('click', (e) => {
                    const btn = e.target.closest('[data-indicator]')
                    if (!btn) return
                    indicatorSelector.querySelectorAll('.btn-segment').forEach(b => b.classList.remove('active'))
                    btn.classList.add('active')
                    Interaction.onIndicatorChange(btn.dataset.indicator)
                })
            }
        },

        updateChipButton(active) {
            const btn = document.getElementById('chipToggleBtn')
            if (btn) {
                if (active) btn.classList.add('active')
                else btn.classList.remove('active')
            }
        },

        updateSelectors() {
            // 恢复周期按钮状态
            const periodSelector = document.getElementById('periodSelector')
            if (periodSelector) {
                periodSelector.querySelectorAll('.btn-segment').forEach(b => {
                    b.classList.toggle('active', b.dataset.period === State.ui.period)
                })
            }
            // 恢复指标按钮状态
            const indicatorSelector = document.getElementById('indicatorSelector')
            if (indicatorSelector) {
                indicatorSelector.querySelectorAll('.btn-segment').forEach(b => {
                    b.classList.toggle('active', b.dataset.indicator === State.ui.indicator)
                })
            }
        },

        initResizeHandle() {
            const handle = document.getElementById('chipResizeHandle')
            if (!handle) return
            let startX = 0
            let startWidth = State.ui.chipWidth
            handle.addEventListener('mousedown', (e) => {
                e.preventDefault()
                startX = e.clientX
                startWidth = State.ui.chipWidth
                handle.style.background = 'rgba(100,100,100,0.4)'
                document.addEventListener('mousemove', onMove)
                document.addEventListener('mouseup', onUp)
            })
            const onMove = (e) => {
                const dx = startX - e.clientX
                let newWidth = startWidth + dx
                newWidth = Math.max(80, Math.min(400, newWidth))
                State.ui.chipWidth = newWidth
                Lifecycle.render()
            }
            const onUp = () => {
                handle.style.background = 'rgba(100,100,100,0.15)'
                document.removeEventListener('mousemove', onMove)
                document.removeEventListener('mouseup', onUp)
            }
        },

        updateResizeHandle() {
            const handle = document.getElementById('chipResizeHandle')
            if (!handle) return
            if (!State.ui.chipVisible) {
                handle.style.display = 'none'
                return
            }
            handle.style.display = 'block'
            const chipWidth = State.ui.chipWidth
            handle.style.right = (chipWidth + 10 - 3) + 'px'
        }
    }

    // ==================== 4. ChartBuilder 图表层 ====================

    const ChartBuilder = {
        /**
         * 构建完整 ECharts option
         * 单实例多 grid 核心：根据筹码面板状态动态调整 grid 数量
         */
        buildOption() {
            const displayData = toDisplayKlineData()
            const dates = displayData.map(d => d.date)
            const ohlc = displayData.map(d => [d.open, d.close, d.low, d.high])
            const zoom = State.runtime.zoom || { start: 75, end: 100 }
            const chipVisible = State.ui.chipVisible
            const chipWidth = State.ui.chipWidth
            const mainRight = chipVisible ? chipWidth + 20 : 40

            // ===== Grid 配置 =====
            const grids = [
                { left: 40, right: mainRight, top: '6%', bottom: '58%' },   // K线
                { left: 40, right: mainRight, top: '48%', bottom: '22%' }   // 指标
            ]

            if (chipVisible) {
                grids.push({
                    left: 'auto',
                    right: 10,
                    top: '6%',
                    bottom: '58%',
                    width: chipWidth
                })
            }

            // ===== X轴配置 =====
            const xAxes = [
                { gridIndex: 0, type: 'category', data: dates, boundaryGap: true },
                { gridIndex: 1, type: 'category', data: dates, boundaryGap: true }
            ]
            if (chipVisible) {
                xAxes.push({ gridIndex: 2, type: 'value', show: false })
            }

            // ===== 计算统一Y轴范围 =====
            const chipDate = State.ui.chipDate
            const chipData = State.data.chipDistribution[chipDate]
            let unifiedMin = Infinity, unifiedMax = -Infinity

            if (displayData.length > 0) {
                unifiedMin = Math.min(...displayData.map(d => d.low))
                unifiedMax = Math.max(...displayData.map(d => d.high))
            }

            if (chipVisible && chipData) {
                unifiedMin = Math.min(unifiedMin, chipData.minPrice)
                unifiedMax = Math.max(unifiedMax, chipData.maxPrice)
            }

            if (unifiedMin === Infinity) {
                unifiedMin = 0
                unifiedMax = 100
            }

            // ===== Y轴配置 =====
            const yAxes = [
                { gridIndex: 0, type: 'value', min: unifiedMin, max: unifiedMax },
                {
                    gridIndex: 1,
                    type: 'value',
                    axisLabel: {
                        formatter: function(value) {
                            if (value >= 100000000) return (value / 100000000).toFixed(1) + '亿'
                            if (value >= 10000) return (value / 10000).toFixed(1) + '万'
                            return value.toFixed(0)
                        }
                    }
                }
            ]

            if (chipVisible && chipData) {
                yAxes.push({
                    gridIndex: 2,
                    type: 'value',
                    min: unifiedMin,
                    max: unifiedMax,
                    show: false
                })
            }

            // ===== DataZoom 配置 =====
            const dataZoom = [
                {
                    type: 'inside',
                    xAxisIndex: [0, 1],
                    start: zoom.start,
                    end: zoom.end,
                    zoomOnMouseWheel: true,
                    moveOnMouseMove: true,
                    moveOnMouseWheel: true,
                    throttle: 50
                },
                {
                    type: 'slider',
                    xAxisIndex: [0, 1],
                    top: '82%',
                    height: '20px',
                    left: 40,
                    right: mainRight,
                    start: zoom.start,
                    end: zoom.end,
                    zoomLock: false,
                    realtime: true,
                    brushSelect: false,
                    handleIcon: 'path://M10.7,11.9v-1.3H9.3v1.3c-4.9,0.3-8.8,4.4-8.8,9.4c0,5,3.9,9.1,8.8,9.4v1.3h1.3v-1.3c4.9-0.3,8.8-4.4,8.8-9.4C19.5,16.3,15.6,12.2,10.7,11.9z M13.3,24.4H6.7V23h6.6V24.4z M13.3,19.6H6.7v-1.4h6.6V19.6z',
                    handleSize: '80%',
                    handleStyle: {
                        color: '#fff',
                        shadowBlur: 3,
                        shadowColor: 'rgba(0, 0, 0, 0.6)',
                        shadowOffsetX: 2,
                        shadowOffsetY: 2
                    },
                    textStyle: { color: '#333' },
                    borderColor: '#e5e7eb',
                    fillerColor: 'rgba(37, 99, 235, 0.2)',
                    dataBackground: {
                        lineStyle: { color: '#cbd5e1' },
                        areaStyle: { color: '#f1f5f9' }
                    }
                }
            ]

            // ===== Series 配置 =====
            const series = this.buildKlineSeries(ohlc, dates)
            series.push(...this.buildIndicatorSeries())

            if (chipVisible) {
                series.push(...this.buildChipSeries())
            }

            // ===== Graphic 配置（筹码统计） =====
            let graphic = []
            if (chipVisible) {
                graphic = this.buildChipGraphic()
            }

            return {
                animationDurationUpdate: 300,
                grid: grids,
                xAxis: xAxes,
                yAxis: yAxes,
                dataZoom,
                series,
                graphic,
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'cross' },
                    formatter: function(params) {
                        if (!params || !params.length) return ''
                        const idx = params[0].dataIndex
                        const kline = State.data.kline[idx]
                        if (!kline) return ''
                        const date = kline.date || ''
                        const open = kline.open !== undefined ? kline.open.toFixed(2) : '-'
                        const close = kline.close !== undefined ? kline.close.toFixed(2) : '-'
                        const high = kline.high !== undefined ? kline.high.toFixed(2) : '-'
                        const low = kline.low !== undefined ? kline.low.toFixed(2) : '-'
                        const volume = kline.volume !== undefined ? (kline.volume / 10000).toFixed(2) + '万' : '-'
                        const turnover = kline.turnover_rate !== undefined && kline.turnover_rate !== null
                            ? kline.turnover_rate.toFixed(2) + '%'
                            : '-'
                        const pct = kline.close !== undefined && kline.open !== undefined
                            ? ((kline.close - kline.open) / kline.open * 100).toFixed(2) + '%'
                            : '-'
                        return `<div style="font-size:12px;line-height:1.6">
                            <div style="font-weight:bold;margin-bottom:4px">${date}</div>
                            <div>开: ${open} &nbsp; 收: ${close} &nbsp; 幅: ${pct}</div>
                            <div>高: ${high} &nbsp; 低: ${low}</div>
                            <div>量: ${volume} &nbsp; 换手: ${turnover}</div>
                        </div>`
                    }
                }
            }
        },

        /**
         * K线系列配置
         * 【高保真迁移】原始 getKlineOption 中的 series 部分
         */
        buildKlineSeries(ohlc, dates) {
            const symbol = State.runtime.symbol
            const allData = State.data.kline

            return [
                {
                    name: 'K线',
                    type: 'candlestick',
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                    data: ohlc,
                    itemStyle: {
                        color: '#ef4444',
                        color0: '#10b981',
                        borderColor: '#ef4444',
                        borderColor0: '#10b981'
                    }
                },
                {
                    name: 'MA5',
                    type: 'line',
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                    data: calcMA(allData, 5),
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { opacity: 0.6, color: '#f59e0b', width: 1.5 }
                },
                {
                    name: 'MA10',
                    type: 'line',
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                    data: calcMA(allData, 10),
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { opacity: 0.6, color: '#6366f1', width: 1.5 }
                },
                {
                    name: 'MA20',
                    type: 'line',
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                    data: calcMA(allData, 20),
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { opacity: 0.6, color: '#22c55e', width: 1.5 }
                }
            ]
        },

        /**
         * 指标系列配置
         * 【高保真迁移】原始 getIndicatorOption 函数
         */
        buildIndicatorSeries() {
            const indicator = State.ui.indicator
            const displayData = toDisplayKlineData()

            if (indicator === 'VOL') {
                return [{
                    name: '成交量',
                    type: 'bar',
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    data: displayData.map(d => d.volume),
                    itemStyle: {
                        color: (params) => {
                            const idx = params.dataIndex
                            if (idx >= displayData.length) return '#64748b'
                            const data = displayData[idx]
                            if (!data || data.close === null || data.open === null) return '#64748b'
                            return data.close >= data.open ? '#ef4444' : '#10b981'
                        }
                    },
                    barWidth: '60%'
                }]
            }

            if (indicator === 'MACD') {
                const macdData = State.data.indicators.macd || []
                if (macdData.length === 0) return []

                return [
                    {
                        name: 'DIFF',
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        data: macdData.map(d => d.macd),
                        smooth: false,
                        symbol: 'none',
                        lineStyle: { width: 2, color: '#2563eb' },
                        z: 10
                    },
                    {
                        name: 'DEA',
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        data: macdData.map(d => d.signal),
                        smooth: false,
                        symbol: 'none',
                        lineStyle: { width: 2, color: '#ef4444' },
                        z: 10
                    },
                    {
                        name: 'MACD柱',
                        type: 'bar',
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        data: macdData.map(d => d.histogram),
                        barWidth: '60%',
                        itemStyle: {
                            color: (params) => {
                                if (params.value === null || params.value === undefined) return '#cccccc'
                                return params.value >= 0 ? '#ef4444' : '#10b981'
                            }
                        },
                        z: 5
                    },
                    {
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        data: Array(macdData.length).fill(0),
                        symbol: 'none',
                        lineStyle: { color: '#6b7280', width: 1, type: 'solid' },
                        silent: true,
                        z: 1
                    }
                ]
            }

            if (indicator === 'RSI') {
                const rsiData = State.data.indicators.rsi || []
                if (rsiData.length === 0) return []

                return [
                    {
                        name: 'RSI',
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        data: rsiData.map(d => d.value),
                        smooth: false,
                        symbol: 'none',
                        lineStyle: { width: 2, color: '#8b5cf6' },
                        areaStyle: {
                            color: {
                                type: 'linear',
                                x: 0, y: 0, x2: 0, y2: 1,
                                colorStops: [
                                    { offset: 0, color: 'rgba(139, 92, 246, 0.3)' },
                                    { offset: 1, color: 'rgba(139, 92, 246, 0.05)' }
                                ]
                            }
                        }
                    },
                    {
                        name: '超买线',
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        data: Array(rsiData.length).fill(70),
                        lineStyle: { type: 'dashed', color: '#ef4444', width: 1, opacity: 0.6 },
                        symbol: 'none',
                        silent: true
                    },
                    {
                        name: '超卖线',
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        data: Array(rsiData.length).fill(30),
                        lineStyle: { type: 'dashed', color: '#10b981', width: 1, opacity: 0.6 },
                        symbol: 'none',
                        silent: true
                    }
                ]
            }

            if (indicator === 'KDJ') {
                const kdjData = State.data.indicators.kdj || []
                if (kdjData.length === 0) return []

                return [
                    {
                        name: 'K',
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        data: kdjData.map(d => d.k),
                        smooth: false,
                        symbol: 'none',
                        lineStyle: { width: 2, color: '#2563eb' }
                    },
                    {
                        name: 'D',
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        data: kdjData.map(d => d.d),
                        smooth: false,
                        symbol: 'none',
                        lineStyle: { width: 2, color: '#ef4444' }
                    },
                    {
                        name: 'J',
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        data: kdjData.map(d => d.j),
                        smooth: false,
                        symbol: 'none',
                        lineStyle: { width: 1.5, type: 'dashed', color: '#8b5cf6' }
                    },
                    {
                        name: '超买区',
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        data: Array(kdjData.length).fill(80),
                        lineStyle: { type: 'dashed', color: '#ef4444', width: 1, opacity: 0.5 },
                        symbol: 'none',
                        silent: true
                    },
                    {
                        name: '超卖区',
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        data: Array(kdjData.length).fill(20),
                        lineStyle: { type: 'dashed', color: '#10b981', width: 1, opacity: 0.5 },
                        symbol: 'none',
                        silent: true
                    }
                ]
            }

            if (indicator === 'OBV') {
                const obvData = State.data.indicators.obv || []
                if (obvData.length === 0) return []

                return [{
                    name: 'OBV',
                    type: 'line',
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    data: obvData.map(d => d.value),
                    smooth: false,
                    symbol: 'none',
                    lineStyle: { width: 2, color: '#f59e0b' },
                    areaStyle: {
                        color: {
                            type: 'linear',
                            x: 0, y: 0, x2: 0, y2: 1,
                            colorStops: [
                                { offset: 0, color: 'rgba(245, 158, 11, 0.3)' },
                                { offset: 1, color: 'rgba(245, 158, 11, 0.05)' }
                            ]
                        }
                    }
                }]
            }

            return []
        },

        /**
         * 筹码分布系列配置
         */
        buildChipSeries() {
            const chipDate = State.ui.chipDate
            const chipData = State.data.chipDistribution[chipDate]
            if (!chipData) return []

            const bins = chipData.bins || []
            if (bins.length === 0) return []

            const currentClose = State.data.kline.find(d => d.date === chipDate)?.close || 0
            const binCount = bins.length
            const binSize = binCount > 0 ? (chipData.maxPrice - chipData.minPrice) / binCount : 0

            const seriesData = bins.map(b => [
                b.volume,
                b.price,
                b.price - binSize / 2,
                b.price + binSize / 2,
                b.price <= currentClose ? '#ef4444' : '#10b981'
            ])

            return [{
                name: '筹码',
                type: 'custom',
                xAxisIndex: 2,
                yAxisIndex: 2,
                data: seriesData,
                renderItem(params, api) {
                    const volume = api.value(0)
                    const priceLow = api.value(2)
                    const priceHigh = api.value(3)
                    const color = api.value(4)

                    // 获取Y轴范围进行裁剪
                    const yAxis = State.chartInstance?.getModel()?.getComponent('yAxis', 2)
                    let yMin = -Infinity, yMax = Infinity
                    if (yAxis?.axis?.scale) {
                        const extent = yAxis.axis.scale.getExtent()
                        yMin = extent[0]
                        yMax = extent[1]
                    }

                    const clampedLow = Math.max(priceLow, yMin)
                    const clampedHigh = Math.min(priceHigh, yMax)
                    if (clampedHigh <= clampedLow) {
                        return null
                    }

                    const start = api.coord([0, clampedHigh])
                    const end = api.coord([volume, clampedLow])

                    return {
                        type: 'rect',
                        shape: {
                            x: start[0],
                            y: start[1],
                            width: end[0] - start[0],
                            height: end[1] - start[1]
                        },
                        style: {
                            fill: color,
                            opacity: 0.85
                        }
                    }
                },
                clip: true
            }]
        },

        /**
         * 筹码统计信息 graphic
         */
        buildChipGraphic() {
            const chipDate = State.ui.chipDate
            const chipData = State.data.chipDistribution[chipDate]
            if (!chipData) return []

            const currentClose = State.data.kline.find(d => d.date === chipDate)?.close || 0
            const avgCost = chipData.avgCost || 0
            const profitRatio = chipData.profitRatio || 0
            const lossRatio = chipData.lossRatio || 0
            const profitLossRatio = chipData.profitLossRatio

            const avgCostColor = avgCost <= currentClose ? '#ef4444' : '#10b981'
            const plText = profitLossRatio !== null && profitLossRatio !== undefined
                ? profitLossRatio.toFixed(2)
                : '—'

            const chartDom = document.getElementById('mainChart')
            const chartWidth = chartDom ? chartDom.clientWidth : 1200
            const chipWidth = State.ui.chipWidth
            const chipPanelLeft = chartWidth - 10 - chipWidth

            return [
                {
                    type: 'group',
                    left: chipPanelLeft + 10,
                    top: 65,
                    children: [{
                        type: 'text',
                        style: {
                            text: '筹码分布',
                            fill: '#94a3b8',
                            fontSize: 12,
                            fontWeight: 'bold'
                        }
                    }]
                },
                {
                    type: 'group',
                    left: chipPanelLeft + 10,
                    top: '55%',
                    children: [
                        {
                            type: 'text',
                            top: 0,
                            style: {
                                text: `日期: ${chipDate}`,
                                fill: '#e2e8f0',
                                fontSize: 11,
                                fontWeight: 'bold'
                            }
                        },
                        {
                            type: 'text',
                            top: 18,
                            style: {
                                text: `平均成本: ${avgCost.toFixed(2)}`,
                                fill: avgCostColor,
                                fontSize: 11
                            }
                        },
                        {
                            type: 'text',
                            top: 36,
                            style: {
                                text: `获利比例: ${profitRatio.toFixed(1)}%`,
                                fill: '#ef4444',
                                fontSize: 11
                            }
                        },
                        {
                            type: 'text',
                            top: 54,
                            style: {
                                text: `套牢比例: ${lossRatio.toFixed(1)}%`,
                                fill: '#10b981',
                                fontSize: 11
                            }
                        },
                        {
                            type: 'text',
                            top: 72,
                            style: {
                                text: `盈亏比: ${plText}`,
                                fill: '#e2e8f0',
                                fontSize: 11
                            }
                        }
                    ]
                }
            ]
        }
    }

    // ==================== 5. DataService 数据层 ====================

    const DataService = {
        /**
         * 初始数据加载
         * 【高保真迁移】原始 loadData 函数
         */
        loadInitial() {
            const rt = State.runtime
            console.log('开始加载K线数据:', { symbol: rt.symbol, useMockMode: rt.useMockMode })
            rt.isLoadingNewStock = true

            const mySequence = ++rt.loadSequence
            console.log('加载序列号:', mySequence)

            if (rt.loadAbort) {
                rt.loadAbort.abort()
            }
            rt.loadAbort = new AbortController()
            const abortSignal = rt.loadAbort.signal

            const modeConfig = getModeConfig(true)
            const url = modeConfig.buildUrl()
            console.log('请求URL:', url)

            this.showLoading(true)

            fetch(url, { signal: abortSignal })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
                    }
                    return response.json()
                })
                .then(result => {
                    if (abortSignal.aborted) {
                        console.log('请求已被取消，忽略响应')
                        return
                    }
                    if (mySequence !== rt.loadSequence) {
                        console.log('请求已过期，忽略响应')
                        return
                    }

                    this.showLoading(false)

                    if (result.status !== 'success') {
                        console.error('API返回错误:', result.message)
                        this.showEmpty(result.message || '数据加载失败')
                        return
                    }

                    const chartData = result.data || {}
                    State.data.kline = chartData.kline || []
                    State.data.events = chartData.events || []
                    State.data.indicators = chartData.indicators || {}
                    State.data.chipDistribution = chartData.chipDistribution || {}

                    console.log(`加载完成: ${State.data.kline.length}条K线, 指标类型:`, Object.keys(State.data.indicators), '筹码日期数:', Object.keys(State.data.chipDistribution).length)

                    if (!State.chartInstance) {
                        console.warn('图表实例已被销毁，跳过渲染')
                        return
                    }

                    // 计算默认 zoom
                    this.calcDefaultZoom()

                    // 渲染
                    Lifecycle.render()

                    rt.initialLoadComplete = true
                    rt.infiniteScrollEnabled = true
                    console.log('初始加载完成，启用无限滚动')

                    // 启动检测
                    Interaction.startInfiniteScroll()
                    this.startRealtimePoll()
                })
                .catch(error => {
                    if (error.name === 'AbortError') {
                        console.log('请求被取消:', error.message)
                        return
                    }
                    console.error('加载K线数据失败:', error)
                    this.showEmpty('数据加载失败，请稍后重试')
                })
                .finally(() => {
                    if (rt.loadAbort && rt.loadAbort.signal === abortSignal) {
                        rt.loadAbort = null
                    }
                })
        },

        /**
         * 计算默认 zoom（显示最近60天）
         */
        calcDefaultZoom() {
            const data = State.data.kline
            const rt = State.runtime

            if (rt.zoom) return  // 保留已有位置

            const totalDays = data.length
            const displayDays = 60

            if (totalDays <= displayDays) {
                rt.zoom = { start: 0, end: 100 }
            } else {
                const startPercent = ((totalDays - displayDays) / totalDays) * 100
                rt.zoom = { start: startPercent, end: 100 }
            }
            console.log(`加载新股票，显示最近${displayDays}天，dataZoom:`, rt.zoom)
            rt.isLoadingNewStock = false
        },

        /**
         * 加载更多历史数据
         * 【高保真迁移】原始 loadMoreHistoryData 函数
         */
        loadHistory(callback) {
            const rt = State.runtime
            console.log('开始加载更多历史数据...', { symbol: rt.symbol, useMockMode: rt.useMockMode })

            if (!State.data.kline || State.data.kline.length === 0) {
                console.warn('没有当前数据，无法加载更多')
                rt.lastLoadPosition = -1
                callback(false)
                return
            }

            const beforeDate = State.data.kline[0].date
            const modeConfig = getModeConfig(false)
            const url = modeConfig.buildHistoryUrl(beforeDate)
            console.log('加载更多URL:', url)

            fetch(url)
                .then(r => {
                    if (!r.ok) {
                        throw new Error(`HTTP ${r.status}: ${r.statusText}`)
                    }
                    return r.json()
                })
                .then(res => {
                    if (res.status !== 'success') {
                        console.error('加载失败:', res.message)
                        callback(false)
                        return
                    }

                    const chartData = res.data || {}
                    const newData = chartData.kline || []
                    const newEvents = chartData.events || []
                    const newIndicators = chartData.indicators || {}
                    const newChipData = chartData.chipDistribution || {}

                    console.log('API返回数据:', { newDataLength: newData.length, beforeDate })

                    if (newData.length === 0) {
                        console.warn('API返回空数据！已到达最早数据')
                        rt.lastLoadPosition = -1
                        callback(false)
                        return
                    }

                    // 去重合并
                    const existingDates = new Set(State.data.kline.map(d => d.date))
                    const uniqueNewData = newData.filter(d => !existingDates.has(d.date))
                    const uniqueNewEvents = newEvents.filter(e => !State.data.events.some(existing => existing.date === e.date))

                    if (uniqueNewData.length === 0) {
                        console.warn('所有返回数据均已存在，可能已到达最早数据')
                        rt.hasMoreData = false
                        rt.lastLoadPosition = -1
                        callback(false)
                        return
                    }

                    const oldLength = State.data.kline.length
                    State.data.kline = uniqueNewData.concat(State.data.kline)
                    State.data.events = uniqueNewEvents.concat(State.data.events)

                    // 合并指标数据
                    for (const indicatorName in newIndicators) {
                        if (State.data.indicators[indicatorName]) {
                            const indicatorSlice = newIndicators[indicatorName].slice(0, uniqueNewData.length)
                            State.data.indicators[indicatorName] = indicatorSlice.concat(State.data.indicators[indicatorName])
                        } else {
                            State.data.indicators[indicatorName] = newIndicators[indicatorName]
                        }
                    }

                    // 合并筹码数据
                    for (const dateKey in newChipData) {
                        State.data.chipDistribution[dateKey] = newChipData[dateKey]
                    }

                    console.log('加载成功：API返回', newData.length, '条，去重后新增', uniqueNewData.length, '条，总计', State.data.kline.length, '条')

                    // 更新图表（增量更新）
                    this.updateChartData()

                    // 调整 dataZoom 位置
                    this.adjustZoomAfterPrepend(oldLength, uniqueNewData.length)

                    rt.lastLoadPosition = -1
                    console.log('重置加载标记，允许下一次触发')

                    callback(true)
                })
                .catch(err => {
                    console.error('加载更多数据失败:', err)
                    rt.lastLoadPosition = -1
                    callback(false)
                })
        },

        /**
         * 增量更新图表数据
         * 【高保真迁移】原始 updateChartData 函数
         */
        updateChartData() {
            if (!State.chartInstance) return

            try {
                const displayData = toDisplayKlineData()
                const dates = displayData.map(d => d.date)
                const ohlc = displayData.map(d => [d.open, d.close, d.low, d.high])

                State.chartInstance.setOption({
                    xAxis: [
                        { data: dates },
                        { data: dates }
                    ],
                    series: [
                        { name: 'K线', data: ohlc },
                        { name: 'MA5', data: calcMA(State.data.kline, 5) },
                        { name: 'MA10', data: calcMA(State.data.kline, 10) },
                        { name: 'MA20', data: calcMA(State.data.kline, 20) }
                    ]
                }, { notMerge: false, lazyUpdate: true })

                // 同步更新指标
                this.updateIndicatorData()

                console.log('已更新图表数据，K线', displayData.length, '条')
            } catch (e) {
                console.error('更新图表数据失败:', e)
            }
        },

        /**
         * 更新指标图数据
         * 【高保真迁移】原始 updateIndicatorData 函数
         */
        updateIndicatorData() {
            if (!State.chartInstance) return

            try {
                const indicator = State.ui.indicator
                const displayData = toDisplayKlineData()
                const dates = displayData.map(d => d.date)

                if (indicator === 'VOL') {
                    State.chartInstance.setOption({
                        series: [{
                            name: '成交量',
                            data: displayData.map(d => d.volume)
                        }]
                    }, { notMerge: false, lazyUpdate: true })
                } else if (indicator === 'MACD') {
                    const macdData = State.data.indicators.macd || []
                    State.chartInstance.setOption({
                        series: [
                            { name: 'DIFF', data: macdData.map(d => d.macd) },
                            { name: 'DEA', data: macdData.map(d => d.signal) },
                            { name: 'MACD柱', data: macdData.map(d => d.histogram) }
                        ]
                    }, { notMerge: false, lazyUpdate: true })
                } else if (indicator === 'RSI') {
                    const rsiData = State.data.indicators.rsi || []
                    State.chartInstance.setOption({
                        series: [{ name: 'RSI', data: rsiData.map(d => d.value) }]
                    }, { notMerge: false, lazyUpdate: true })
                } else if (indicator === 'KDJ') {
                    const kdjData = State.data.indicators.kdj || []
                    State.chartInstance.setOption({
                        series: [
                            { name: 'K', data: kdjData.map(d => d.k) },
                            { name: 'D', data: kdjData.map(d => d.d) },
                            { name: 'J', data: kdjData.map(d => d.j) }
                        ]
                    }, { notMerge: false, lazyUpdate: true })
                } else if (indicator === 'OBV') {
                    const obvData = State.data.indicators.obv || []
                    State.chartInstance.setOption({
                        series: [{ name: 'OBV', data: obvData.map(d => d.value) }]
                    }, { notMerge: false, lazyUpdate: true })
                }
            } catch (e) {
                console.error('更新指标图数据失败:', e)
            }
        },

        /**
         * 调整 dataZoom 位置（数据前置后保持视图不跳跃）
         * 【高保真迁移】原始 adjustDataZoomAfterPrepend 函数
         */
        adjustZoomAfterPrepend(oldLength, prependLength) {
            if (!State.chartInstance) return

            try {
                const option = State.chartInstance.getOption()
                if (!option.dataZoom || !option.dataZoom[0]) return

                const oldZoom = option.dataZoom[0]
                const newLength = oldLength + prependLength

                const oldStartIndex = Math.floor((oldZoom.start || 0) / 100 * oldLength)
                const oldEndIndex = Math.floor((oldZoom.end || 100) / 100 * oldLength)

                const newStartIndex = oldStartIndex + prependLength
                const newEndIndex = oldEndIndex + prependLength

                const newStart = (newStartIndex / newLength) * 100
                const newEnd = (newEndIndex / newLength) * 100

                console.log('调整 dataZoom:', {
                    old: { start: oldZoom.start?.toFixed(2) + '%', end: oldZoom.end?.toFixed(2) + '%', length: oldLength },
                    new: { start: newStart.toFixed(2) + '%', end: newEnd.toFixed(2) + '%', length: newLength }
                })

                if (typeof window.__dataZoomAdjusting === 'function') {
                    window.__dataZoomAdjusting(true)
                }

                State.chartInstance.dispatchAction({
                    type: 'dataZoom',
                    dataZoomIndex: 0,
                    start: newStart,
                    end: newEnd
                })

                setTimeout(() => {
                    if (typeof window.__dataZoomAdjusting === 'function') {
                        window.__dataZoomAdjusting(false)
                    }
                }, 150)
            } catch (e) {
                console.error('调整 dataZoom 失败:', e)
            }
        },

        /**
         * 实时K线轮询
         * 【高保真迁移】原始 fetchRealtimeKline 函数
         */
        pollRealtime() {
            const rt = State.runtime
            if (!rt.realtimeEnabled || !rt.symbol) return

            const modeConfig = getModeConfig(false)
            const url = modeConfig.buildRealtimeUrl()
            console.log(`${rt.useMockMode ? 'Mock模式' : '真实模式'} - 获取实时K线 (period=${State.ui.period})`)

            fetch(url)
                .then(r => r.json())
                .then(res => {
                    if (res.status !== 'success') {
                        console.warn('获取实时K线失败:', res.message)
                        return
                    }

                    const realtimeData = res.data
                    console.log('实时K线数据:', realtimeData)

                    rt.currentRealtimeKline = realtimeData
                    this.applyRealtime(realtimeData)

                    if (realtimeData.should_poll) {
                        this.startRealtimePoll()
                    } else {
                        this.stopRealtimePoll()
                    }
                })
                .catch(err => {
                    console.error('获取实时K线失败:', err)
                })
        },

        startRealtimePoll() {
            this.stopRealtimePoll()
            const rt = State.runtime
            if (!rt.realtimeEnabled) return

            const modeConfig = getModeConfig(true)
            rt.realtimeTimer = setInterval(() => this.pollRealtime(), modeConfig.pollInterval)
            console.log('启动实时K线轮询')
        },

        stopRealtimePoll() {
            const rt = State.runtime
            if (rt.realtimeTimer) {
                clearInterval(rt.realtimeTimer)
                rt.realtimeTimer = null
                console.log('停止实时K线轮询')
            }
        },

        /**
         * 应用实时K线到图表
         * 【高保真迁移】原始 updateRealtimeKlineOnChart 函数
         */
        applyRealtime(realtimeData) {
            if (!State.data.kline || !State.data.kline.length) return
            if (realtimeData.trading_phase?.toLowerCase() !== 'trading') return
            if (!realtimeData.date) {
                console.error('实时K线数据缺少date字段:', realtimeData)
                return
            }

            console.log('更新实时K线:', {
                period: State.ui.period,
                date: realtimeData.date,
                open: realtimeData.open,
                close: realtimeData.close
            })

            const realtimeDate = realtimeData.date
            const existingIndex = State.data.kline.findIndex(d => {
                let dateStr = d.date
                if (typeof dateStr === 'string' && dateStr.includes('GMT')) {
                    dateStr = new Date(dateStr).toISOString().split('T')[0]
                }
                return dateStr === realtimeDate
            })

            if (existingIndex >= 0) {
                console.log(`更新K柱: ${realtimeDate}`)
                State.data.kline[existingIndex] = {
                    date: realtimeDate,
                    open: realtimeData.open,
                    high: realtimeData.high,
                    low: realtimeData.low,
                    close: realtimeData.close,
                    volume: realtimeData.volume
                }
            } else {
                console.log(`添加新K柱: ${realtimeDate}`)
                State.data.kline.push({
                    date: realtimeDate,
                    open: realtimeData.open,
                    high: realtimeData.high,
                    low: realtimeData.low,
                    close: realtimeData.close,
                    volume: realtimeData.volume
                })
            }

            this.updateChartData()
        },

        showLoading(show = true, text = '加载中...') {
            if (State.chartInstance) {
                if (show) State.chartInstance.showLoading({ text, color: '#2563eb' })
                else State.chartInstance.hideLoading()
            }
        },

        showEmpty(text = '暂无数据') {
            // 单实例下通过 setOption 显示空状态
            if (State.chartInstance) {
                State.chartInstance.clear()
            }
        }
    }

    // ==================== 6. Interaction 交互层 ====================

    const Interaction = {
        /**
         * 周期切换
         * 【高保真迁移】原始 selectPeriod 函数
         */
        onPeriodChange(period) {
            State.ui.period = period
            DataService.loadInitial()
        },

        /**
         * 指标切换
         * 【高保真迁移】原始 selectIndicator 函数
         */
        onIndicatorChange(indicator) {
            State.ui.indicator = indicator
            Lifecycle.render()
            Layout.updateSelectors()
        },

        /**
         * 筹码面板切换
         */
        toggleChip() {
            State.ui.chipVisible = !State.ui.chipVisible
            Layout.updateChipButton(State.ui.chipVisible)

            if (State.ui.chipVisible && State.data.kline.length > 0) {
                State.ui.chipDate = State.data.kline[State.data.kline.length - 1].date
            }

            // 通过 setOption 重新构建整个配置
            // 注意：ECharts setOption(notMerge: false) 不会删除已存在的 grid，
            // 所以切换时需要先 clear() 再重新构建
            if (State.chartInstance) {
                const option = ChartBuilder.buildOption()
                State.chartInstance.clear()
                State.chartInstance.setOption(option, {
                    notMerge: true,
                    lazyUpdate: false
                })
                // 恢复 DOM 按钮状态（clear 不影响 DOM，但为保险起见）
                Layout.updateSelectors()
            }
            Layout.updateResizeHandle()
        },

        /**
         * axisPointer 事件处理（筹码联动）
         * 【高保真迁移】原始 onKlineAxisPointer 函数
         */
        onAxisPointer(params) {
            if (!State.ui.chipVisible || !State.data.chipDistribution) return
            const xAxisInfo = params?.axesInfo?.[0]
            if (!xAxisInfo) return
            const idx = xAxisInfo.value
            if (typeof idx !== 'number' || idx < 0 || idx >= State.data.kline.length) return
            const date = State.data.kline[idx]?.date
            if (date && date !== State.ui.chipDate) {
                State.ui.chipDate = date
                // 更新筹码数据
                if (State.chartInstance) {
                    State.chartInstance.setOption({
                        series: ChartBuilder.buildChipSeries(),
                        graphic: ChartBuilder.buildChipGraphic()
                    }, { notMerge: false, lazyUpdate: true })
                }
            }
        },

        /**
         * 无限滚动检测
         * 【高保真迁移】原始 startInfiniteScrollDetection 函数
         */
        startInfiniteScroll() {
            const rt = State.runtime
            console.log('启动无限滚动检测')

            setInterval(() => {
                try {
                    if (!rt.initialLoadComplete) return
                    if (!State.chartInstance) return

                    let currentStart = 0
                    let hasValidZoom = false

                    const option = State.chartInstance.getOption()
                    if (option.dataZoom && option.dataZoom[0]) {
                        currentStart = option.dataZoom[0].start || 0
                        hasValidZoom = true
                    }

                    if (!hasValidZoom) return

                    // 检测用户拖动
                    if (rt.lastStartValue === -1) {
                        rt.lastStartValue = currentStart
                        console.log('首次记录 dataZoom 位置:', currentStart.toFixed(2) + '%')
                    } else if (Math.abs(currentStart - rt.lastStartValue) > 0.5 && !rt.isAdjustingBySystem) {
                        rt.userIsMoving = true
                        if (!rt.infiniteScrollEnabled && rt.initialLoadComplete) {
                            rt.infiniteScrollEnabled = true
                            console.log('检测到用户拖动，启用无限滚动')
                        }
                        if (rt.movingResetTimer) clearTimeout(rt.movingResetTimer)
                        rt.movingResetTimer = setTimeout(() => {
                            rt.userIsMoving = false
                        }, 500)
                    }

                    rt.lastStartValue = currentStart

                    // 触发加载
                    if (rt.infiniteScrollEnabled && rt.hasMoreData && !rt.isLoadingMore) {
                        let shouldLoad = false
                        let triggerReason = ''
                        let needsUserMoving = true

                        if (currentStart < 20 && rt.lastLoadPosition !== 20) {
                            shouldLoad = true
                            triggerReason = '紧急加载(start < 20%)'
                            rt.lastLoadPosition = 20
                            needsUserMoving = false
                        } else if (currentStart < 40 && rt.lastLoadPosition !== 40 && rt.userIsMoving) {
                            shouldLoad = true
                            triggerReason = '预加载1(start < 40%)'
                            rt.lastLoadPosition = 40
                        } else if (currentStart < 60 && currentStart >= 40 && rt.lastLoadPosition !== 60 && rt.userIsMoving) {
                            shouldLoad = true
                            triggerReason = '预加载2(start < 60%)'
                            rt.lastLoadPosition = 60
                        }

                        if (shouldLoad) {
                            console.log('触发加载更多：' + triggerReason)
                            rt.isLoadingMore = true
                            DataService.loadHistory((success) => {
                                rt.isLoadingMore = false
                                if (!success) {
                                    rt.hasMoreData = false
                                    console.log('已到达最早数据')
                                }
                            })
                        }
                    }
                } catch (e) {
                    // 忽略
                }
            }, 100)
        }
    }

    // ==================== 7. Lifecycle 生命周期层 ====================

    const Lifecycle = {
        /**
         * 初始化
         */
        init(symbol, marketCode, useMockMode, mockTradingPhase = 'trading') {
            const rt = State.runtime
            rt.symbol = symbol
            rt.marketCode = marketCode
            rt.useMockMode = useMockMode
            rt.mockTradingPhase = mockTradingPhase

            this.clear()
            Layout.build()
            Layout.initResizeHandle()
            DataService.loadInitial()
        },

        /**
         * 渲染
         */
        render() {
            if (!State.chartInstance) return

            const option = ChartBuilder.buildOption()
            State.chartInstance.setOption(option, true)

            // 绑定 axisPointer 事件
            State.chartInstance.off('updateAxisPointer')
            State.chartInstance.on('updateAxisPointer', Interaction.onAxisPointer)

            // 绑定 dataZoom 事件
            State.chartInstance.off('dataZoom')
            State.chartInstance.on('dataZoom', () => {
                if (State.ui.chipVisible && State.ui.chipDate) {
                    State.chartInstance.setOption({
                        series: ChartBuilder.buildChipSeries(),
                        graphic: ChartBuilder.buildChipGraphic()
                    }, { notMerge: false, lazyUpdate: true })
                }
            })

            Layout.updateResizeHandle()
        },

        /**
         * 清理
         * 【高保真迁移】原始 clearChart 函数
         */
        clear() {
            const rt = State.runtime

            DataService.stopRealtimePoll()

            if (rt.loadAbort) {
                rt.loadAbort.abort()
                rt.loadAbort = null
            }

            if (State.chartInstance) {
                State.chartInstance.dispose()
                State.chartInstance = null
            }

            // 重置数据
            State.data.kline = []
            State.data.events = []
            State.data.indicators = {}
            State.data.chipDistribution = {}

            // 重置 UI 状态
            State.ui.chipVisible = false
            State.ui.chipDate = ''

            // 重置运行时状态
            rt.isLoadingNewStock = false
            rt.realtimeTimer = null
            rt.currentRealtimeKline = null
            rt.zoom = null
            rt.isLoadingMore = false
            rt.hasMoreData = true
            rt.lastLoadPosition = -1
            rt.lastStartValue = -1
            rt.userIsMoving = false
            rt.movingResetTimer = null
            rt.isAdjustingBySystem = false
            rt.infiniteScrollEnabled = false
            rt.initialLoadComplete = false
        }
    }

    // ==================== 8. 公共接口 ====================

    window.KlineChart = {
        setCurrent(symbol, marketCode, useMockMode, mockTradingPhase = 'trading') {
            Lifecycle.init(symbol, marketCode, useMockMode, mockTradingPhase)
        },

        selectPeriod(period, element) {
            const container = document.getElementById('periodSelector')
            if (container) {
                container.querySelectorAll('.btn-segment').forEach(b => b.classList.remove('active'))
                if (element) element.classList.add('active')
            }
            Interaction.onPeriodChange(period)
        },

        selectIndicator(indicator, element) {
            const container = document.getElementById('indicatorSelector')
            if (container) {
                container.querySelectorAll('.btn-segment').forEach(b => b.classList.remove('active'))
                if (element) element.classList.add('active')
            }
            Interaction.onIndicatorChange(indicator)
        },

        toggleChipPanel() {
            Interaction.toggleChip()
        },

        setRealtimeUpdateEnabled(enabled) {
            State.runtime.realtimeEnabled = !!enabled
            if (!enabled) {
                DataService.stopRealtimePoll()
            }
            console.log('实时K线更新开关:', enabled ? '启用' : '禁用')
        },

        stopRealtimeKlineUpdateTimer() {
            DataService.stopRealtimePoll()
        }
    }
}
