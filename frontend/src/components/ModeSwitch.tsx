export function ModeSwitch({
  checked,
  onChange,
  title,
  offDescription,
  onDescription,
  offLabel = "Shadow",
  onLabel = "Active",
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  title: string;
  offDescription: string;
  onDescription: string;
  offLabel?: string;
  onLabel?: string;
}) {
  return (
    <div className="mode-switch-row">
      <div className="mode-switch-copy">
        <strong>{title}</strong>
        <span>{checked ? onDescription : offDescription}</span>
      </div>
      <div className="mode-switch-control">
        <span className={`mode-state ${checked ? "active" : "shadow"}`}>
          {checked ? onLabel : offLabel}
        </span>
        <button
          type="button"
          className="compact-switch"
          role="switch"
          aria-checked={checked}
          aria-label={title}
          onClick={() => onChange(!checked)}
        >
          <span aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
