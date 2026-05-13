import { useState } from 'react';
import { Save, FolderOpen, Trash2 } from 'lucide-react';
import type { BacktestTemplateItem } from '../../types/technicalBacktest';
import { PromptDialog, ConfirmDialog } from '../common';

interface Props {
  templates: BacktestTemplateItem[];
  isLoading: boolean;
  onLoad: (template: BacktestTemplateItem) => void;
  onDelete: (id: number) => Promise<void>;
  onSave: (name: string) => Promise<void>;
  disabled?: boolean;
}

export const TemplateManager: React.FC<Props> = ({
  templates,
  isLoading,
  onLoad,
  onDelete,
  onSave,
  disabled,
}) => {
  const [selectedId, setSelectedId] = useState<number | ''>('');
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // 对话框状态
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const selected = templates.find((t) => t.id === selectedId);

  const handleSave = async (name: string) => {
    setIsSaving(true);
    try {
      await onSave(name);
    } finally {
      setIsSaving(false);
      setShowSaveDialog(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!selectedId) return;
    setIsDeleting(true);
    try {
      await onDelete(selectedId);
      setSelectedId('');
    } finally {
      setIsDeleting(false);
      setShowDeleteDialog(false);
    }
  };

  return (
    <>
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-text whitespace-nowrap">模板</span>
        <select
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value ? Number(e.target.value) : '')}
          disabled={disabled || isLoading}
          className="h-9 rounded-xl border border-white/10 bg-card/30 px-2.5 py-1.5 text-xs text-foreground outline-none transition-all focus:border-cyan-500/30 cursor-pointer disabled:opacity-50 min-w-[120px]"
        >
          <option value="">
            {isLoading ? '加载中...' : templates.length === 0 ? '无模板' : '选择模板...'}
          </option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>

        <button
          type="button"
          onClick={() => selected && onLoad(selected)}
          disabled={disabled || !selected}
          className="flex items-center gap-1 h-9 px-2.5 rounded-xl border border-white/10 bg-card/30 text-xs text-muted-text hover:text-cyan-400 hover:border-cyan-500/30 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          title="加载选中模板"
        >
          <FolderOpen className="h-3.5 w-3.5" />
          加载
        </button>

        <button
          type="button"
          onClick={() => setShowSaveDialog(true)}
          disabled={disabled || isSaving}
          className="flex items-center gap-1 h-9 px-2.5 rounded-xl border border-white/10 bg-card/30 text-xs text-muted-text hover:text-cyan-400 hover:border-cyan-500/30 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          title="保存当前参数为模板"
        >
          <Save className="h-3.5 w-3.5" />
          {isSaving ? '保存中...' : '保存当前'}
        </button>

        <button
          type="button"
          onClick={() => setShowDeleteDialog(true)}
          disabled={disabled || isDeleting || !selectedId}
          className="flex items-center gap-1 h-9 px-2.5 rounded-xl border border-white/10 bg-card/30 text-xs text-muted-text hover:text-danger hover:border-danger/40 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          title="删除选中模板"
        >
          <Trash2 className="h-3.5 w-3.5" />
          {isDeleting ? '删除中...' : '删除'}
        </button>
      </div>

      <PromptDialog
        isOpen={showSaveDialog}
        title="保存模板"
        placeholder="请输入模板名称"
        onConfirm={handleSave}
        onCancel={() => setShowSaveDialog(false)}
      />

      <ConfirmDialog
        isOpen={showDeleteDialog}
        title="删除模板"
        message={`确定删除模板「${selected?.name ?? selectedId}」？此操作不可撤销。`}
        confirmText="删除"
        cancelText="取消"
        isDanger
        onConfirm={handleDeleteConfirm}
        onCancel={() => setShowDeleteDialog(false)}
      />
    </>
  );
};
