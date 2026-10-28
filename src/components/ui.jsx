import React from "react";
import { Icon } from "../icons.jsx";
import { classNames, riskLabel, riskTone } from "../format.js";

export function Card({ as: Tag = "article", className, children, ...rest }) {
  return (
    <Tag className={classNames("card", className)} {...rest}>
      {children}
    </Tag>
  );
}

export function CardHeader({ title, subtitle, action, eyebrow, className }) {
  return (
    <div className={classNames("card-header", className)}>
      <div className="card-header-copy">
        {eyebrow && <span className="card-eyebrow">{eyebrow}</span>}
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {action && <div className="card-header-action">{action}</div>}
    </div>
  );
}

export function Badge({ tone = "neutral", children, dot = false, icon, className }) {
  return (
    <span className={classNames("badge", `badge-${tone}`, className)}>
      {dot && <i aria-hidden="true" />}
      {icon && <Icon name={icon} size={12} strokeWidth={2} />}
      {children}
    </span>
  );
}

export function StatusBadge({ risk, label }) {
  return (
    <Badge tone={riskTone(risk)} dot>
      {label || riskLabel(risk)}
    </Badge>
  );
}

export function Segmented({ options, value, onChange, label, className }) {
  return (
    <div className={classNames("segmented", className)} role="group" aria-label={label}>
      {options.map((option) => (
        <button
          type="button"
          key={option.value}
          className={option.value === value ? "is-selected" : ""}
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function SearchField({
  value,
  onChange,
  placeholder = "Search ATM ID or city",
  label = "Search",
  className,
  inputRef,
  onFocus,
  onKeyDown,
  shortcut,
}) {
  return (
    <label className={classNames("search-field", className)}>
      <Icon name="search" size={16} />
      <input
        ref={inputRef}
        type="search"
        value={value}
        placeholder={placeholder}
        aria-label={label}
        onChange={(event) => onChange(event.target.value)}
        onFocus={onFocus}
        onKeyDown={onKeyDown}
        autoComplete="off"
      />
      {shortcut && <kbd>{shortcut}</kbd>}
    </label>
  );
}

export function EmptyState({ icon = "info", title, message, action }) {
  return (
    <div className="empty-state">
      <span className="empty-icon"><Icon name={icon} size={20} /></span>
      <strong>{title}</strong>
      {message && <p>{message}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry, compact = false }) {
  return (
    <div className={classNames("error-state", compact && "is-compact")} role="alert">
      <span className="error-icon"><Icon name="alert" size={18} /></span>
      <div>
        <strong>{compact ? "Could not refresh" : "Something went wrong"}</strong>
        <p>{message}</p>
      </div>
      {onRetry && (
        <button type="button" className="button button-quiet" onClick={onRetry}>
          <Icon name="refresh" size={14} />Retry
        </button>
      )}
    </div>
  );
}

export function LoadingState({ label = "Loading", compact = false }) {
  return (
    <div className={classNames("loading-state", compact && "is-compact")} role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function Skeleton({ className, style }) {
  return <span className={classNames("skeleton", className)} style={style} aria-hidden="true" />;
}

export function Progress({ value = 0, tone = "neutral", label }) {
  const safeValue = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div
      className={classNames("progress", `progress-${tone}`)}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(safeValue)}
    >
      <span style={{ width: `${safeValue}%` }} />
    </div>
  );
}

export function InfoHint({ text }) {
  return (
    <span className="info-hint" title={text} tabIndex={0} role="note" aria-label={text}>
      <Icon name="info" size={13} />
    </span>
  );
}

export function PageHeader({ eyebrow, title, subtitle, meta, actions }) {
  return (
    <header className="page-heading">
      <div className="page-heading-main">
        {eyebrow && <div className="eyebrow"><span className="eyebrow-line" />{eyebrow}</div>}
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
        {meta && <div className="page-meta">{meta}</div>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function DataNotice({ tone = "warning", icon = "alert", title, children, action }) {
  return (
    <div className={classNames("data-notice", `data-notice-${tone}`)} role="note">
      <span className="data-notice-icon"><Icon name={icon} size={16} /></span>
      <div className="data-notice-copy">
        {title && <strong>{title}</strong>}
        <span>{children}</span>
      </div>
      {action}
    </div>
  );
}

export function IconButton({ icon, label, onClick, className, disabled, children, ...rest }) {
  return (
    <button
      type="button"
      className={classNames("icon-button", className)}
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      {...rest}
    >
      <Icon name={icon} size={16} />
      {children}
    </button>
  );
}
