import { useEffect, useMemo } from 'react';
import { Copy, Trash2, Plus, Eye, EyeOff, AlertCircle } from 'lucide-react';
import type { StrategyConfig, ParamGroup, StrategyParameter } from '../../types/technicalBacktest';

interface Props {
  strategy: StrategyConfig | undefined;
  paramGroups: ParamGroup[];
  activeGroupId: string | null;
  onSelectGroup: (id: string | null) => void;
  onAdd: () => void;
  onRemove: (id: string) => void;
  onDuplicate: (id: string) => void;
  onUpdateParam: (groupId: string, key: string, value: number | boolean) => void;
  onUpdateName: (groupId: string, name: string) => void;
  onToggleEnabled: (groupId: string) => void;
  onValidationChange?: (invalidIds: Set<string>) => void;
}

const ParamInput: React.FC<{
  param: StrategyParameter;
  value: number | boolean;
  onChange: (v: number | boolean) => void;
}> = ({ param, value, onChange }) => {
  if (param.type === 'boolean') {
    return (
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(e.target.checked)}
          className="h-4 w-4 rounded border-white/20 bg-transparent accent-cyan-500"
        />
        <span className="text-xs text-secondary-text">{param.name}</span>
      </label>
    );
  }

  const numValue = typeof value === 'number' ? value : Number(value) || 0;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-secondary-text">{param.name}</span>
        <span className="text-xs font-mono text-cyan-400">{numValue}</span>
      </div>
      <input
        type="range"
        min={param.min ?? 0}
        max={param.max ?? 100}
        step={param.step ?? 1}
        value={numValue}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-cyan-500 h-1.5 cursor-pointer"
      />
    </div>
  );
};

function validateGroup(
  group: ParamGroup,
  strategy: StrategyConfig,
): string[] {
  const errors: string[] = [];
  for (const rule of strategy.validationRules) {
    const a = group.params[rule.paramA];
    const b = group.params[rule.paramB];
    if (typeof a === 'number' && typeof b === 'number') {
      if (rule.type === 'lessThan' && a >= b) {
        errors.push(rule.message);
      }
      if (rule.type === 'greaterThan' && a <= b) {
        errors.push(rule.message);
      }
    }
  }
  return errors;
}

export const ParamGroupEditor: React.FC<Props> = ({
  strategy,
  paramGroups,
  activeGroupId,
  onSelectGroup,
  onAdd,
  onRemove,
  onDuplicate,
  onUpdateParam,
  onUpdateName,
  onToggleEnabled,
  onValidationChange,
}) => {
  if (!strategy) {
    return (
      <div className="rounded-xl border border-white/5 bg-card/30 p-4 text-xs text-muted-text">
        请先选择策略
      </div>
    );
  }

  const invalidIds = useMemo(() => {
    const ids = new Set<string>();
    for (const group of paramGroups) {
      if (validateGroup(group, strategy).length > 0) {
        ids.add(group.id);
      }
    }
    return ids;
  }, [paramGroups, strategy]);

  // 通知外部校验状态变化
  useEffect(() => {
    onValidationChange?.(invalidIds);
  }, [invalidIds, onValidationChange]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-text uppercase">参数组配置</span>
        <span className="text-xs text-muted-text">{paramGroups.length}/6</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {paramGroups.map((group) => {
          const errors = validateGroup(group, strategy);
          const hasError = errors.length > 0 && group.enabled;
          return (
          <div
            key={group.id}
            onClick={() => {
              if (!group.enabled) return;
              onSelectGroup(activeGroupId === group.id ? null : group.id);
            }}
            className={`rounded-xl border p-3 space-y-3 transition-all cursor-pointer ${
              hasError
                ? 'border-danger/40 bg-danger/5'
                : activeGroupId === group.id
                  ? 'border-cyan-400/60 bg-card/50 ring-1 ring-cyan-400/20'
                  : group.enabled
                    ? 'border-cyan-500/20 bg-card/40 hover:border-cyan-500/40'
                    : 'border-white/5 bg-card/20 opacity-60'
            }`}
          >
            {/* Group Header */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => onToggleEnabled(group.id)}
                className="text-muted-text hover:text-foreground transition-colors"
                title={group.enabled ? '禁用' : '启用'}
              >
                {group.enabled ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
              </button>
              <input
                type="text"
                value={group.name}
                onChange={(e) => onUpdateName(group.id, e.target.value)}
                className="flex-1 bg-transparent text-xs font-medium text-foreground outline-none border-b border-transparent focus:border-cyan-500/50 px-1"
              />
              <button
                type="button"
                onClick={() => onDuplicate(group.id)}
                disabled={paramGroups.length >= 6}
                className="text-muted-text hover:text-cyan-400 transition-colors disabled:opacity-30"
                title="复制"
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
              {paramGroups.length > 1 && (
                <button
                  type="button"
                  onClick={() => onRemove(group.id)}
                  className="text-muted-text hover:text-danger transition-colors"
                  title="删除"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            {/* Parameters */}
            <div className="space-y-2.5">
              {strategy.parameters.map((param) => (
                <ParamInput
                  key={param.key}
                  param={param}
                  value={group.params[param.key] ?? param.defaultValue}
                  onChange={(v) => onUpdateParam(group.id, param.key, v)}
                />
              ))}
            </div>

            {/* Validation Errors */}
            {hasError && errors.length > 0 && (
              <div className="flex items-start gap-1.5 text-[10px] text-danger">
                <AlertCircle className="h-3 w-3 mt-0.5 flex-shrink-0" />
                <span>{errors.join('；')}</span>
              </div>
            )}
          </div>
          );
        })}
      </div>

      {paramGroups.length < 6 && (
        <button
          type="button"
          onClick={onAdd}
          className="w-full rounded-xl border border-dashed border-white/10 bg-card/20 py-2.5 text-xs text-muted-text hover:text-foreground hover:border-cyan-500/30 hover:bg-card/30 transition-all flex items-center justify-center gap-1.5"
        >
          <Plus className="h-3.5 w-3.5" />
          添加参数组
        </button>
      )}
    </div>
  );
};
