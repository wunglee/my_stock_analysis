import { useState, useEffect, useCallback } from 'react';

function isNonEmptyArray(v: unknown): v is unknown[] {
  return Array.isArray(v) && v.length > 0;
}

interface UseSessionStateOptions<T> {
  defaultValue: T;
  validate?: (value: unknown) => boolean;
}

/**
 * 通用 sessionStorage 状态管理 Hook。
 * 用法类似 useState，但自动持久化到 sessionStorage 并在挂载时恢复。
 */
export function useSessionState<T>(key: string, options: UseSessionStateOptions<T>) {
  const { defaultValue, validate } = options;

  const [value, setValue] = useState<T>(() => {
    try {
      const raw = sessionStorage.getItem(key);
      if (!raw) return defaultValue;
      const parsed: unknown = JSON.parse(raw);
      if (validate && !validate(parsed)) return defaultValue;
      return parsed as T;
    } catch {
      return defaultValue;
    }
  });

  useEffect(() => {
    try {
      sessionStorage.setItem(key, JSON.stringify(value));
    } catch {
      // quota 满或隐私模式下降级
    }
  }, [key, value]);

  const clearValue = useCallback(() => {
    try {
      sessionStorage.removeItem(key);
    } catch {
      // 静默降级
    }
    setValue(defaultValue);
  }, [key, defaultValue]);

  return [value, setValue, clearValue] as const;
}

export { isNonEmptyArray };
