import { useEffect, useRef } from "react";

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  busy = false,
  danger = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  busy?: boolean;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, onCancel, open]);

  if (!open) return null;

  return (
    <div className="p3-dialog-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !busy) onCancel();
    }}>
      <div
        className="p3-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="p3-confirm-title"
        aria-describedby="p3-confirm-description"
      >
        <h2 id="p3-confirm-title">{title}</h2>
        <p id="p3-confirm-description">{description}</p>
        <div className="p3-dialog-actions">
          <button
            ref={cancelRef}
            type="button"
            className="btn-secondary"
            disabled={busy}
            onClick={onCancel}
          >
            取消
          </button>
          <button
            type="button"
            className={danger ? "btn-danger" : "btn-primary"}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "正在处理…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
