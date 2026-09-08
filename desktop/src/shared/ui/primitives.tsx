import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "ghost" | "danger" | "record" | "quiet";
type ButtonSize = "sm" | "md";

interface ButtonProps extends Pick<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "aria-label" | "title"
> {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: ButtonVariant;
  size?: ButtonSize;
  recording?: boolean;
  type?: "button" | "submit";
  className?: string;
}

export function Button({
  children,
  onClick,
  disabled = false,
  variant = "ghost",
  size = "md",
  recording = false,
  type = "button",
  className,
  ...accessibility
}: ButtonProps) {
  const classes = [
    "button",
    `button-${variant}`,
    `button-${size}`,
    variant === "record" && recording ? "is-recording" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      type={type}
      className={classes}
      onClick={onClick}
      disabled={disabled}
      {...accessibility}
    >
      {variant === "record" ? <span className="dot" /> : null}
      {children}
    </button>
  );
}

interface CardProps extends Pick<HTMLAttributes<HTMLElement>, "aria-label"> {
  children: ReactNode;
  className?: string;
  tone?: "default" | "elevated" | "quiet";
}

export function Card({ children, className, tone = "default", ...accessibility }: CardProps) {
  const classes = ["card", `card-${tone}`, className ?? ""].filter(Boolean).join(" ");
  return (
    <section className={classes} {...accessibility}>
      {children}
    </section>
  );
}

interface PageHeaderProps {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="page-header-copy">
        <p className="pretitle">{eyebrow}</p>
        <div className="page-title">{title}</div>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

interface BadgeProps {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger";
}

export function Badge({ children, tone = "neutral" }: BadgeProps) {
  return <span className={`status-badge status-badge-${tone}`}>{children}</span>;
}

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <span className="empty-state-mark" aria-hidden />
      <div>
        <strong>{title}</strong>
        {description ? <p>{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

interface ProgressBarProps {
  value: number;
}

export function ProgressBar({ value }: ProgressBarProps) {
  const normalized = Math.max(0, Math.min(100, value));
  return (
    <div
      className="progress"
      role="progressbar"
      aria-valuenow={normalized}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span style={{ width: `${normalized}%` }} />
    </div>
  );
}
