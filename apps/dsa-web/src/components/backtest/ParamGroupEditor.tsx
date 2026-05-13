import { useEffect, useMemo } from 'react';
import { Copy, Trash2, Plus, Eye, EyeOff, AlertCircle, ChevronDown } from 'lucide-react';
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
        <span className="text-[11px] text-secondary-text">{param.name}</span>
        <span className="text-[11px] font-mono text-cyan-400">{numValue}</span>
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

  useEffect(() => {
    onValidationChange?.(invalidIds);
  }, [invalidIds, onValidationChange]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <span className="text-[11px] font-medium text-muted-text uppercase">参数组</span>
        <span className="text-[10px] text-muted-text">{paramGroups.length}/6</span>
      </div>

      {paramGroups.map((group) => {
        const errors = validateGroup(group, strategy);
        const hasError = errors.length > 0 && group.enabled;
        const isExpanded = activeGroupId === group.id;

        return (
          <div
            key={group.id}
            className={`rounded-xl border transition-all ${
              hasError
                ? 'border-danger/40 bg-danger/5'
                : isExpanded
                  ? 'border-cyan-400/60 bg-card/50 ring-1 ring-cyan-400/20'
                  : group.enabled
                    ? 'border-cyan-500/20 bg-card/40 hover:border-cyan-500/40'
                    : 'border-white/5 bg-card/20 opacity-60'
            }`}
          >
            {/* Header */}
            <div
              onClick={() => {
                if (!group.enabled) return;
                onSelectGroup(isExpanded ? null : group.id);
              }}
              className="flex items-center gap-1.5 px-2.5 py-2 cursor-pointer select-none"
            >
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleEnabled(group.id);
                }}
                className="text-muted-text hover:text-foreground transition-colors flex-shrink-0"
                title={group.enabled ? '禁用' : '启用'}
              >
                {group.enabled ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
              </button>

              <input
                type="text"
                value={group.name}
                onChange={(e) => onUpdateName(group.id, e.target.value)}
                onClick={(e) => e.stopPropagation()}
                className="flex-1 min-w-0 bg-transparent text-xs font-medium text-foreground outline-none border-b border-transparent focus:border-cyan-500/50 px-0.5"
              />

              {hasError && (
                <AlertCircle className="h-3 w-3 text-danger flex-shrink-0" />
              )}

              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onDuplicate(group.id);
                }}
                disabled={paramGroups.length >= 6}
                className="text-muted-text hover:text-cyan-400 transition-colors disabled:opacity-30 flex-shrink-0"
                title="复制"
              >
                <Copy className="h-3 w-3" />
              </button>

              {paramGroups.length > 1 && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemove(group.id);
                  }}
                  className="text-muted-text hover:text-danger transition-colors flex-shrink-0"
                  title="删除"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}

              <ChevronDown
                className={`h-3.5 w-3.5 text-muted-text flex-shrink-0 transition-transform duration-200 ${
                  isExpanded ? 'rotate-180' : ''
                }`}
              />
            </div>

            {/* Body — 仅展开时渲染 */}
            {isExpanded && (
              <div className="px-3 pb-3 space-y-2.5">
                {strategy.parameters.map((param) => (
                  <ParamInput
                    key={param.key}
                    param={param}
                    value={group.params[param.key] ?? param.defaultValue}
                    onChange={(v) => onUpdateParam(group.id, param.key, v)}
                  />
                ))}

                {hasError && (
                  <div className="flex items-start gap-1.5 text-[10px] text-danger">
                    <AlertCircle className="h-3 w-3 mt-0.5 flex-shrink-0" />
                    <span>{errors.join('；')}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      {paramGroups.length < 6 && (
        <button
          type="button"
          onClick={onAdd}
          className="w-full rounded-xl border border-dashed border-white/10 bg-card/20 py-2 text-xs text-muted-text hover:text-foreground hover:border-cyan-500/30 hover:bg-card/30 transition-all flex items-center justify-center gap-1.5"
        >
          <Plus className="h-3.5 w-3.5" />
          添加参数组
        </button>
      )}
    </div>
  );
};
