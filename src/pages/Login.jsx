import React, { useState } from "react";
import { apiRequest, clearAccessToken, createSession } from "../data.js";
import { BrandMark, Icon } from "../icons.jsx";

export default function Login({ onLogin, sessionError = "" }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const token = await createSession(username, password);
      const user = await apiRequest("/auth/me", { token });
      onLogin(token, user);
    } catch (requestError) {
      clearAccessToken();
      setError(requestError.message || "Sign in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-screen">
      <section className="login-shell">
        <div className="login-visual" aria-hidden="true">
          <div className="login-visual-brand">
            <BrandMark size={44} />
            <span>
              <strong>CashCast</strong>
              <small>Smarter ATM cash planning</small>
            </span>
          </div>
          <div className="login-visual-copy">
            <span className="eyebrow is-on-dark"><span className="eyebrow-line" />CASH INTELLIGENCE</span>
            <h1>Plan every note.<br />Serve every neighbourhood.</h1>
            <p>
              Demand forecasting, scenario planning and replenishment estimates in one
              calm operational view.
            </p>
          </div>
          <div className="login-preview">
            <div className="login-preview-head">
              <span>Network cash cover</span>
              <span className="badge badge-neutral">Simulation</span>
            </div>
            <div className="login-preview-chart">
              <svg viewBox="0 0 320 96" role="presentation">
                <defs>
                  <linearGradient id="login-area" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#f3e84a" stopOpacity="0.34" />
                    <stop offset="100%" stopColor="#f3e84a" stopOpacity="0" />
                  </linearGradient>
                </defs>
                <path d="M0 78 L40 68 L80 72 L120 52 L160 58 L200 38 L240 44 L280 24 L320 30 L320 96 L0 96 Z" fill="url(#login-area)" />
                <polyline points="0,78 40,68 80,72 120,52 160,58 200,38 240,44 280,24 320,30" fill="none" stroke="#f3e84a" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <div className="login-preview-foot">
              <span><i />Synthetic demonstration data</span>
              <strong>Model evaluation · holdout</strong>
            </div>
          </div>
          <div className="login-visual-foot">
            <Icon name="shield" size={15} />
            <span>Authenticated operations workspace · no live ATM connectivity</span>
          </div>
        </div>

        <div className="login-panel">
          <div className="login-mobile-brand">
            <BrandMark size={38} />
            <span>
              <strong>CashCast</strong>
              <small>ATM intelligence</small>
            </span>
          </div>

          <div className="login-intro">
            <span className="eyebrow"><span className="eyebrow-line" />SECURE ACCESS</span>
            <h2>Welcome back</h2>
            <p>Sign in to review ATM demand, scenario estimates and replenishment planning.</p>
          </div>

          <form className="login-form" onSubmit={submit}>
            <label htmlFor="username">Username</label>
            <div className="input-shell">
              <Icon name="user" size={16} />
              <input
                id="username"
                name="username"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="Operations username"
                required
              />
            </div>

            <label htmlFor="password">Password</label>
            <div className="input-shell">
              <Icon name="lock" size={16} />
              <input
                id="password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Password"
                required
              />
              <button
                type="button"
                className="password-toggle"
                aria-label={showPassword ? "Hide password" : "Show password"}
                onClick={() => setShowPassword((current) => !current)}
              >
                <Icon name={showPassword ? "x" : "info"} size={15} />
              </button>
            </div>

            {error && <div className="form-error" role="alert">{error}</div>}
            {!error && sessionError && <div className="form-error" role="status">{sessionError}</div>}

            <button className="button button-primary login-submit" type="submit" disabled={submitting}>
              {submitting ? <span className="spinner spinner-on-dark" aria-hidden="true" /> : <Icon name="arrowRight" size={16} />}
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div className="login-note">
            <Icon name="info" size={15} />
            <span>
              This workspace runs on synthetic demonstration data. Amounts are generic cash
              units, not live Bank Muscat balances.
            </span>
          </div>
          <div className="login-footnote">Authorized banking operations staff only.</div>
        </div>
      </section>
    </main>
  );
}
