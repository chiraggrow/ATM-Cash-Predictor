import React, { useState } from "react";
import { useApp } from "../AppContext.jsx";
import {
  Badge,
  Card,
  CardHeader,
  DataNotice,
  ErrorState,
  PageHeader,
  Progress,
  Segmented,
  StatusBadge,
} from "../components/ui.jsx";
import { apiRequest } from "../data.js";
import {
  classNames,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPercent,
  sourceLabel,
} from "../format.js";
import { Icon } from "../icons.jsx";

function PreferenceToggle({ id, checked, onChange, label, description }) {
  return (
    <label className="toggle-row is-compact" htmlFor={id}>
      <span className="toggle-copy">
        <strong>{label}</strong>
        <span>{description}</span>
      </span>
      <input
        id={id}
        type="checkbox"
        className="toggle-input"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="toggle-track" aria-hidden="true"><i /></span>
    </label>
  );
}

export default function Settings() {
  const {
    token,
    user,
    onLogout,
    core,
    coreLoading,
    refreshCore,
    prefs,
    setPrefs,
  } = useApp();
  const [retraining, setRetraining] = useState(false);
  const [retrainError, setRetrainError] = useState("");
  const [retrainResult, setRetrainResult] = useState(null);

  const status = core.status;
  const model = core.summary?.model;
  const database = core.databaseSummary;
  const isAdmin = String(user.role).toLowerCase() === "admin";
  const update = (patch) => setPrefs((current) => ({ ...current, ...patch }));

  async function retrain() {
    setRetrainError("");
    setRetrainResult(null);
    setRetraining(true);
    try {
      const result = await apiRequest("/admin/model/retrain", {
        token,
        method: "POST",
      });
      setRetrainResult(result);
      refreshCore();
    } catch (error) {
      setRetrainError(error?.message || "The model could not be retrained.");
    } finally {
      setRetraining(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="WORKSPACE"
        title="Settings"
        subtitle="Profile, local display preferences and the current model and data context."
        meta={(
          <>
            <span className="meta-chip"><Icon name="user" size={13} />{user.username} · {user.role}</span>
            <Badge tone="neutral">Local preferences</Badge>
          </>
        )}
        actions={(
          <button type="button" className="button button-quiet" onClick={onLogout}>
            <Icon name="logout" size={15} />Sign out
          </button>
        )}
      />

      <section className="settings-grid">
        <Card className="settings-card">
          <CardHeader eyebrow="ACCOUNT" title="User profile" subtitle="Provided by the authenticated API session" />
          <div className="profile-block">
            <span className="profile-avatar">{user.username.slice(0, 2).toUpperCase()}</span>
            <div>
              <strong>{user.username}</strong>
              <span>{isAdmin ? "Administrator access" : "Analyst access"}</span>
              <small>Session token held in this browser tab for the current session</small>
            </div>
          </div>
          <dl className="detail-list">
            <div><dt>Role</dt><dd><Badge tone={isAdmin ? "positive" : "neutral"}>{user.role}</Badge></dd></div>
            <div><dt>Authentication</dt><dd>OAuth2 password bearer · FastAPI</dd></div>
            <div><dt>Account persistence</dt><dd>Managed by the backend user table</dd></div>
          </dl>
          <div className="settings-actions">
            <button type="button" className="button button-quiet" onClick={onLogout}>
              <Icon name="logout" size={15} />Sign out of CashCast
            </button>
          </div>
        </Card>

        <Card className="settings-card">
          <CardHeader
            eyebrow="DISPLAY"
            title="Dashboard preferences"
            subtitle="Stored in this browser only · not synced to an account"
          />

          <div className="setting-field">
            <span className="field-label">Appearance</span>
            <Segmented
              label="Theme"
              value={prefs.theme}
              onChange={(value) => update({ theme: value })}
              options={[{ value: "light", label: "Light" }, { value: "dark", label: "Dim" }]}
            />
          </div>

          <div className="setting-field">
            <span className="field-label">Table density</span>
            <Segmented
              label="Table density"
              value={prefs.density}
              onChange={(value) => update({ density: value })}
              options={[{ value: "comfortable", label: "Comfortable" }, { value: "compact", label: "Compact" }]}
            />
          </div>

          <div className="setting-field">
            <label className="field-label" htmlFor="default-months">Default chart window</label>
            <div className="select-shell">
              <Icon name="calendar" size={15} />
              <select
                id="default-months"
                value={prefs.defaultMonths}
                onChange={(event) => update({ defaultMonths: Number(event.target.value) })}
              >
                <option value={3}>3 months</option>
                <option value={6}>6 months</option>
                <option value={12}>12 months</option>
                <option value={24}>24 months</option>
              </select>
            </div>
            <p className="field-help">Applied whenever the Overview page is opened.</p>
          </div>

          <div className="setting-toggles">
            <PreferenceToggle
              id="compact-numbers"
              checked={prefs.compactNumbers}
              onChange={(checked) => update({ compactNumbers: checked })}
              label="Compact large numbers"
              description="Show values above ten thousand with a K/M suffix."
            />
          </div>

          <div className="setting-field">
            <span className="field-label">Currency and number formatting</span>
            <p className="field-help is-strong">
              The dataset does not declare a currency, so CashCast renders generic
              <strong> cash units</strong> rather than INR, OMR or USD. Values use thousands
              separators and up to one decimal for compact notation.
            </p>
          </div>
        </Card>

        <Card className="settings-card">
          <CardHeader
            eyebrow="DATA"
            title="Data source and coverage"
            subtitle="Reported by /analytics/summary, /model/status and /data/summary"
            action={<Badge tone={status?.data_source === "synthetic_simulation" ? "warning" : "neutral"} dot>{sourceLabel(status?.data_source)}</Badge>}
          />

          {coreLoading && !status ? (
            <p className="field-help">Loading data context…</p>
          ) : (
            <dl className="detail-list">
              <div><dt>Operational source</dt><dd>PostgreSQL · ATM observation table</dd></div>
              <div><dt>Observation source</dt><dd>{sourceLabel(status?.data_source)}</dd></div>
              <div><dt>Coverage</dt><dd>{formatDate(status?.dataset_start_date)} – {formatDate(status?.dataset_end_date)}</dd></div>
              <div><dt>Dataset rows</dt><dd>{formatNumber(status?.dataset_rows)}</dd></div>
              <div><dt>ATMs</dt><dd>{formatNumber(status?.atm_count)}</dd></div>
              <div><dt>Stored observations</dt><dd>{formatNumber(database?.observation_count)}</dd></div>
              <div><dt>Stored forecasts</dt><dd>{formatNumber(database?.forecast_count)}</dd></div>
              <div><dt>Forecast mode</dt><dd>{status?.forecast_mode || "—"}</dd></div>
              <div>
                <dt>Operational forecasting</dt>
                <dd>
                  {status?.forecast_available
                    ? <Badge tone="positive" dot>Available</Badge>
                    : <Badge tone="warning" dot>Blocked</Badge>}
                </dd>
              </div>
              {!status?.forecast_available && status?.forecast_blocked_reason && (
                <div className="detail-wide">
                  <dt>Blocked reason</dt>
                  <dd>{status.forecast_blocked_reason}</dd>
                </div>
              )}
            </dl>
          )}
        </Card>

        <Card className="settings-card">
          <CardHeader
            eyebrow="MODEL"
            title="Forecast model"
            subtitle="Chronological holdout evaluation from the backend"
            action={model ? (
              <Badge tone={model.target_met ? "positive" : "warning"}>
                {model.target_met ? "Target met" : "Below target"}
              </Badge>
            ) : null}
          />

          {model ? (
            <>
              <dl className="detail-list">
                <div><dt>Model</dt><dd>{String(model.model_name).replaceAll("-", " ")}</dd></div>
                <div><dt>Target</dt><dd>{formatPercent(model.target_accuracy_pct, 0)} accuracy</dd></div>
                <div><dt>Accuracy</dt><dd>{formatPercent(model.accuracy_pct)}</dd></div>
                <div><dt>WAPE</dt><dd>{formatPercent(model.wape_pct)}</dd></div>
                <div><dt>Baseline WAPE</dt><dd>{formatPercent(model.baseline_wape_pct)}</dd></div>
                <div><dt>MAE</dt><dd>{formatNumber(model.mae)} units</dd></div>
                <div><dt>RMSE</dt><dd>{formatNumber(model.rmse)} units</dd></div>
                <div><dt>P90 error interval</dt><dd>± {formatNumber(model.interval_abs_error_p90)} units</dd></div>
                <div><dt>Holdout window</dt><dd>{formatDate(model.test_start_date)} – {formatDate(model.test_end_date)}</dd></div>
                <div><dt>Trained</dt><dd>{formatDateTime(model.trained_at)}</dd></div>
              </dl>
              <div className="target-progress">
                <div className="cash-progress-labels">
                  <span>Holdout accuracy vs 100%</span>
                  <strong>{formatPercent(model.accuracy_pct)}</strong>
                </div>
                <Progress value={model.accuracy_pct ?? 0} tone={model.target_met ? "positive" : "warning"} label="Model accuracy" />
                <p className="field-help">Accuracy = 100 − WAPE on the holdout window. It is not cash-out performance.</p>
              </div>
            </>
          ) : (
            <p className="field-help">Model evaluation is not available.</p>
          )}
        </Card>

        <Card className="settings-card is-full">
          <CardHeader
            eyebrow="ADMINISTRATION"
            title="Model operations"
            subtitle="Retraining runs on the backend with the configured dataset and rewrites evaluation artifacts"
            action={<StatusBadge risk={status?.model_data_current ? "healthy" : "watch"} label={status?.model_data_current ? "Model current" : "Retrain required"} />}
          />

          <div className="admin-row">
            <div>
              <strong>Retrain the forecast model</strong>
              <p className="field-help">
                {isAdmin
                  ? "This calls POST /api/v1/admin/model/retrain. It can take longer than a normal request and is recorded against your session."
                  : "Only an administrator account can trigger retraining. Your role currently has read access."}
              </p>
            </div>
            <button
              type="button"
              className="button button-primary"
              onClick={retrain}
              disabled={!isAdmin || retraining}
            >
              {retraining
                ? <span className="spinner spinner-on-dark" aria-hidden="true" />
                : <Icon name="cpu" size={15} />}
              {retraining ? "Retraining…" : "Retrain model"}
            </button>
          </div>

          {retrainError && <ErrorState message={retrainError} compact />}

          {retrainResult && (
            <DataNotice tone="info" icon="checkCircle" title="Retraining completed">
              {retrainResult.model_name} evaluated at {formatPercent(retrainResult.accuracy_pct)} accuracy
              on {formatNumber(retrainResult.test_rows)} holdout rows. Metrics refreshed at{" "}
              {formatDateTime(retrainResult.trained_at)}.
            </DataNotice>
          )}

          <div className="admin-foot">
            <span><Icon name="shield" size={14} />Environment variables, database credentials and API keys are never exposed in this interface.</span>
            <button type="button" className="text-link" onClick={refreshCore} disabled={coreLoading}>
              Refresh metadata <Icon name="refresh" size={12} />
            </button>
          </div>
        </Card>
      </section>

      <DataNotice tone="warning" title="Demonstration workspace">
        CashCast is connected to a PostgreSQL-backed forecasting service using synthetic
        demonstration observations. No live Bank Muscat balances, cash-out outcomes or dispatch
        confirmations are displayed anywhere in this interface.
      </DataNotice>
    </>
  );
}
