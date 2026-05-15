import { useState } from 'react';
import { createPortal } from 'react-dom';

interface PromptDialogProps {
  isOpen: boolean;
  title: string;
  placeholder?: string;
  confirmText?: string;
  cancelText?: string;
  onConfirm: (value: string) => void;
  onCancel: () => void;
}

/**
 * 通用输入对话框，替换 window.prompt。
 * 样式与 ConfirmDialog 保持一致。
 */
export const PromptDialog: React.FC<PromptDialogProps> = ({
  isOpen,
  title,
  placeholder = '',
  confirmText = '确定',
  cancelText = '取消',
  onConfirm,
  onCancel,
}) => {
  const [value, setValue] = useState('');

  if (!isOpen) return null;

  const handleConfirm = () => {
    if (value.trim()) {
      onConfirm(value.trim());
      setValue('');
    }
  };

  const handleCancel = () => {
    setValue('');
    onCancel();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleConfirm();
    if (e.key === 'Escape') handleCancel();
  };

  const dialog = (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm transition-all"
      onClick={handleCancel}
    >
      <div
        className="mx-4 w-full max-w-sm rounded-xl border border-border/70 bg-elevated p-6 shadow-2xl animate-in fade-in zoom-in duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-2 text-lg font-medium text-foreground">{title}</h3>
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          autoFocus
          className="mb-6 w-full rounded-lg border border-border/70 bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted-text outline-none transition-all focus:border-cyan-500/30"
        />
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={handleCancel}
            className="rounded-lg border border-border/70 px-4 py-2 text-sm font-medium text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
          >
            {cancelText}
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!value.trim()}
            className="rounded-lg bg-cyan/80 px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-cyan shadow-lg shadow-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(dialog, document.body);
};
