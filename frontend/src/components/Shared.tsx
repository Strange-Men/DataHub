export function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function StatusBadge({
  status,
  label,
}: {
  status: "connected" | "disconnected" | "roadmap" | "active";
  label: string;
}) {
  return <span className={`status-badge status-${status}`}>{label}</span>;
}

export function EmptyState({
  icon,
  title,
  description,
}: {
  icon?: string;
  title: string;
  description?: string;
}) {
  return (
    <div className="empty-state">
      {icon ? <span className="empty-icon">{icon}</span> : null}
      <p className="empty-title">{title}</p>
      {description ? <p className="empty-desc">{description}</p> : null}
    </div>
  );
}

export function RuleBox({
  title,
  rules,
}: {
  title: string;
  rules: string[];
}) {
  return (
    <div className="rule-box">
      <strong>{title}</strong>
      <ul>
        {rules.map((rule, i) => (
          <li key={i}>{rule}</li>
        ))}
      </ul>
    </div>
  );
}

export function SectionHeader({
  eyebrow,
  title,
  actions,
}: {
  eyebrow?: string;
  title: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="section-header">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h2>{title}</h2>
      </div>
      {actions ? <div className="section-actions">{actions}</div> : null}
    </div>
  );
}

export function StepIndicator({
  steps,
  currentStep,
}: {
  steps: { number: number; label: string }[];
  currentStep: number;
}) {
  return (
    <div className="step-indicator">
      {steps.map((step) => (
        <div
          key={step.number}
          className={`step-item ${step.number === currentStep ? "active" : ""} ${step.number < currentStep ? "done" : ""}`}
        >
          <div className="step-number">
            {step.number < currentStep ? "✓" : step.number}
          </div>
          <span className="step-label">{step.label}</span>
        </div>
      ))}
    </div>
  );
}
