/**
 * 格式化日期时间
 */
export function formatDate(
  dateString: string | Date,
  format = 'YYYY-MM-DD HH:mm:ss'
): string {
  const date = typeof dateString === 'string' ? new Date(dateString) : dateString;
  if (isNaN(date.getTime())) return '-';

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');

  return format
    .replace('YYYY', String(year))
    .replace('MM', month)
    .replace('DD', day)
    .replace('HH', hours)
    .replace('mm', minutes)
    .replace('ss', seconds);
}

/**
 * 格式化数字，保留指定小数位
 */
export function formatNumber(num: number | null | undefined, decimals = 2): string {
  if (num === null || num === undefined || isNaN(num)) return '-';
  return Number(num).toFixed(decimals);
}

/**
 * 格式化为百分比
 */
export function formatPercent(num: number | null | undefined, decimals = 2): string {
  if (num === null || num === undefined || isNaN(num)) return '-';
  return (Number(num) * 100).toFixed(decimals) + '%';
}

/**
 * 安全获取嵌套对象属性
 */
export function getNestedValue<T>(obj: unknown, path: string, defaultValue: T | null = null): T | null {
  const value = path.split('.').reduce<unknown>((acc, part) => {
    if (acc && typeof acc === 'object' && part in acc) {
      return (acc as Record<string, unknown>)[part];
    }
    return undefined;
  }, obj);
  return value !== undefined ? (value as T) : defaultValue;
}

/**
 * 获取指定时区的分钟偏移量（相对于UTC）
 */
export function getTimezoneOffset(timezone: string): number {
  const date = new Date();
  const utcDate = new Date(date.toLocaleString('en-US', { timeZone: 'UTC' }));
  const tzDate = new Date(date.toLocaleString('en-US', { timeZone: timezone }));
  return (utcDate.getTime() - tzDate.getTime()) / 60000;
}

/**
 * 将时间字符串解析为指定市场时区的Date对象
 */
export function extractFromMarketDateTimeStr(
  timeString: string,
  marketTimezone: string
): Date | null {
  if (!timeString || !marketTimezone) return null;

  let date: Date;

  if (timeString.includes('T')) {
    date = new Date(timeString);
  } else if (timeString.includes('-') && timeString.includes(':')) {
    date = new Date(timeString.replace(' ', 'T'));
  } else if (/^\d+$/.test(timeString)) {
    date = new Date(parseInt(timeString));
  } else {
    date = new Date(timeString);
  }

  if (isNaN(date.getTime())) return null;

  const timezoneOffset = getTimezoneOffset(marketTimezone);
  const localOffset = date.getTimezoneOffset();
  return new Date(date.getTime() + (timezoneOffset - localOffset) * 60000);
}

/**
 * 从日期时间字符串中提取日期部分（YYYY-MM-DD）
 */
export function extractFromDateStr(dateTimeStr: string, marketTimezone: string): string {
  if (!dateTimeStr) return '';

  const match = dateTimeStr.match(/(\d{4}-\d{2}-\d{2})/);
  if (match) return match[1];

  const date = extractFromMarketDateTimeStr(dateTimeStr, marketTimezone);
  if (date) return date.toISOString().split('T')[0];

  return '';
}

/**
 * 从日期时间字符串中提取时间部分（HH:MM:SS）
 */
export function extractFromTimeStr(dateTimeStr: string, marketTimezone: string): string {
  if (!dateTimeStr) return '';

  const match = dateTimeStr.match(/(\d{2}:\d{2}:\d{2})/);
  if (match) return match[1];

  const date = extractFromMarketDateTimeStr(dateTimeStr, marketTimezone);
  if (!date) return '';

  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `${hours}:${minutes}:${seconds}`;
}

/**
 * 获取指定时间在指定市场时区的格式化时间字符串
 */
export function formatToMarketDateTimeStr(date: Date, marketTimezone: string): string {
  if (!date || !(date instanceof Date) || !marketTimezone) return '';

  try {
    return date.toLocaleString('zh-CN', {
      timeZone: marketTimezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  } catch {
    return '';
  }
}

/**
 * 解析交易时间字符串
 * 格式如 "09:30-11:30,13:00-15:00" 或 "09:30-15:00"
 */
export function parseTradingHoursString(tradingHoursStr: string): {
  open: string | null;
  close: string | null;
  lunch_start: string | null;
  lunch_end: string | null;
} {
  if (!tradingHoursStr) {
    return { open: null, close: null, lunch_start: null, lunch_end: null };
  }

  if (tradingHoursStr.includes(',')) {
    const segments = tradingHoursStr.split(',');
    const morning = segments[0].trim();
    const afternoon = segments[1].trim();
    const morningParts = morning.split('-');
    const afternoonParts = afternoon.split('-');

    return {
      open: morningParts[0]?.trim() ?? null,
      close: afternoonParts[1]?.trim() ?? null,
      lunch_start: morningParts[1]?.trim() ?? null,
      lunch_end: afternoonParts[0]?.trim() ?? null,
    };
  }

  const parts = tradingHoursStr.split('-');
  return {
    open: parts[0]?.trim() ?? null,
    close: parts[1]?.trim() ?? null,
    lunch_start: null,
    lunch_end: null,
  };
}

/**
 * 时间轴标签格式化（显示 HH:MM）
 */
export function formatTimeAxisLabel(value: string | number): string {
  if (typeof value === 'string') {
    if (value.length >= 5) return value.substring(0, 5);
  }
  return String(value);
}
