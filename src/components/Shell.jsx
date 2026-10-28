import React, { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "../AppContext.jsx";
import { Icon, BrandMark } from "../icons.jsx";
import { NAV_ITEMS, TOP_TABS, pageTitle } from "../navigation.js";
import { mergeAtmRecords, riskCounts, scenarioIndex } from "../derive.js";
import {
  classNames,
  coverageLabel,
  formatDate,
  formatPercent,
  sourceLabel,
} from "../format.js";
import { Badge, EmptyState, SearchField, Skeleton, StatusBadge } from "./ui.jsx";
import { useEscapeKey, useOutsideClick, useApi } from "../hooks.js";

function Rail() {
  const { page, navigate, user, onLogout, prefs, setPrefs, core } = useApp();
  const isDark = prefs.theme === "dark";

  return (
    <aside className="rail" aria-label="Primary navigation">
      <button
        type="button"
        className="rail-brand"
        aria-label="CashCast home"
        title="CashCast — Smarter ATM Cash Planning"
        onClick={() => navigate("overview")}
      >
        <BrandMark size={40} />
      </button>

      <nav className="rail-nav">
        {NAV_ITEMS.map((item) => (
          <button
            type="button"
            key={item.id}
            className={classNames("rail-link", page === item.id && "is-active")}
            aria-label={item.label}
            aria-current={page === item.id ? "page" : undefined}
            onClick={() => navigate(item.id)}
          >
            <Icon name={item.icon} size={19} />
            <span className="rail-tooltip">{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="rail-bottom">
        <span
          className="rail-status"
          title={`${sourceLabel(core.status?.data_source)} · ${user.role} access`}
          aria-hidden="true"
        >
          <i />
        </span>
        <button
          type="button"
          className={classNames("rail-link", page === "settings" && "is-active")}
          aria-label="Settings"
          aria-current={page === "settings" ? "page" : undefined}
          onClick={() => navigate("settings")}
        >
          <Icon name="settings" size={19} />
          <span className="rail-tooltip">Settings</span>
        </button>
        <button
          type="button"
          className="rail-link"
          aria-label={isDark ? "Switch to light theme" : "Switch to dim theme"}
          title={isDark ? "Switch to light theme" : "Switch to dim theme"}
          onClick={() => setPrefs((current) => ({
            ...current,
            theme: current.theme === "dark" ? "light" : "dark",
          }))}
        >
          <Icon name={isDark ? "sun" : "moon"} size={18} />
          <span className="rail-tooltip">{isDark ? "Light theme" : "Dim theme"}</span>
        </button>
        <button
          type="button"
          className="rail-link rail-signout"
          aria-label="Sign out"
          title="Sign out"
          onClick={onLogout}
        >
          <Icon name="logout" size={18} />
          <span className="rail-tooltip">Sign out</span>
        </button>
      </div>
    </aside>
  );
}

function GlobalSearch() {
  const { core, navigate } = useApp();
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const [openOnMobile, setOpenOnMobile] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const wrapperRef = useRef(null);
  const inputRef = useRef(null);

  const records = useMemo(
    () => mergeAtmRecords(core.atms, core.metadata),
    [core.atms, core.metadata],
  );
  const normalized = query.trim().toLowerCase();
  const results = useMemo(() => {
    const filtered = normalized
      ? records.filter((record) => (
        record.atm_id.toLowerCase().includes(normalized)
        || String(record.location_name || "").toLowerCase().includes(normalized)
        || String(record.location_type || "").toLowerCase().includes(normalized)
        || String(record.city || "").toLowerCase().includes(normalized)
      ))
      : records
        .filter((record) => record.risk_level !== "healthy")
        .sort((a, b) => (a.coverage_ratio ?? 99) - (b.coverage_ratio ?? 99));
    return filtered.slice(0, 7);
  }, [records, normalized]);

  const showing = focused || openOnMobile;

  useOutsideClick(wrapperRef, () => {
    setFocused(false);
    setOpenOnMobile(false);
  }, showing);

  useEffect(() => {
    function onShortcut(event) {
      const isShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
      if (!isShortcut) return;
      event.preventDefault();
      setOpenOnMobile(true);
      window.requestAnimationFrame(() => inputRef.current?.focus());
    }
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, []);

  useEffect(() => {
    setHighlighted(0);
  }, [query]);

  function select(record) {
    if (!record) return;
    navigate("atms", { q: record.atm_id });
    setQuery("");
    setFocused(false);
    setOpenOnMobile(false);
    inputRef.current?.blur();
  }

  function onKeyDown(event) {
    if (event.key === "Escape") {
      setFocused(false);
      setOpenOnMobile(false);
      inputRef.current?.blur();
      return;
    }
    if (!results.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((current) => (current + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((current) => (current - 1 + results.length) % results.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      select(results[highlighted]);
    }
  }

  return (
    <div className={classNames("global-search", openOnMobile && "is-open")} ref={wrapperRef}>
      <button
        type="button"
        className="search-mobile-toggle"
        aria-label="Search ATM ID or city"
        onClick={() => {
          setOpenOnMobile((current) => !current);
          window.requestAnimationFrame(() => inputRef.current?.focus());
        }}
      >
        <Icon name="search" size={17} />
      </button>
      <SearchField
        className="topbar-search"
        inputRef={inputRef}
        value={query}
        onChange={setQuery}
        onFocus={() => setFocused(true)}
        onKeyDown={onKeyDown}
        shortcut="⌘K"
        label="Search ATM ID or city"
      />
      {showing && (
        <div className="search-results" role="listbox" aria-label="ATM search results">
          <div className="search-results-head">
            <span>{normalized ? `${results.length} matching ATMs` : "Priority ATMs"}</span>
            <kbd>esc</kbd>
          </div>
          {results.length === 0 ? (
            <EmptyState
              icon="search"
              title="No ATMs match"
              message="Try an ATM identifier, city, or location type."
            />
          ) : results.map((record, index) => (
            <button
              type="button"
              key={record.atm_id}
              role="option"
              aria-selected={highlighted === index}
              className={classNames("search-result", highlighted === index && "is-highlighted")}
              onMouseEnter={() => setHighlighted(index)}
              onClick={() => select(record)}
            >
              <span className="search-result-icon"><Icon name="atm" size={16} /></span>
              <span className="search-result-copy">
                <strong>{record.atm_id}</strong>
                <span>{record.location_name} · {record.location_type}</span>
              </span>
              <StatusBadge risk={record.risk_level} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Briefing() {
  const { token, core, navigate } = useApp();
  const [open, setOpen] = useState(false);
  const close = React.useCallback(() => setOpen(false), []);
  useEscapeKey(open, close);

  const scenario = useApi("/forecasts/scenario", {
    token,
    method: "POST",
    body: {},
    enabled: open && Boolean(core.summary),
  });
  const estimates = useMemo(() => scenarioIndex(scenario.data), [scenario.data]);
  const rows = useMemo(
    () => mergeAtmRecords(core.atms, core.metadata).map((row) => {
      const estimate = estimates.get(row.atm_id);
      return {
        ...row,
        risk_level: estimate?.risk_level || row.risk_level,
        coverage_ratio: estimate?.cash_cover_days ?? row.coverage_ratio,
      };
    }),
    [core.atms, core.metadata, estimates],
  );
  const counts = useMemo(() => riskCounts(rows), [rows]);
  const critical = useMemo(
    () => rows
      .filter((row) => row.risk_level === "critical")
      .sort((a, b) => (a.coverage_ratio ?? 99) - (b.coverage_ratio ?? 99))
      .slice(0, 4),
    [rows],
  );

  return (
    <>
      <button type="button" className="briefing-button" onClick={() => setOpen(true)}>
        <Icon name="sparkles" size={15} />
        <span>Daily briefing</span>
      </button>
      {open && (
        <div className="drawer-layer" role="dialog" aria-modal="true" aria-label="Daily briefing">
          <button type="button" className="drawer-backdrop" aria-label="Close daily briefing" onClick={close} />
          <aside className="drawer">
            <header className="drawer-head">
              <div>
                <span className="eyebrow"><span className="eyebrow-line" />OPERATIONS SUMMARY</span>
                <h2>Daily briefing</h2>
                <p>Generated from the latest API response · {formatDate(core.summary?.latest_dataset_date)}</p>
              </div>
              <button type="button" className="icon-button" onClick={close} aria-label="Close daily briefing">
                <Icon name="x" size={17} />
              </button>
            </header>

            <div className="drawer-body">
              {!core.summary ? (
                <div className="drawer-skeletons">
                  <Skeleton style={{ height: 74 }} />
                  <Skeleton style={{ height: 74 }} />
                  <Skeleton style={{ height: 148 }} />
                </div>
              ) : (
                <>
                  <div className="briefing-grid">
                    <div>
                      <span>Holdout accuracy</span>
                      <strong>{formatPercent(core.summary.model.accuracy_pct)}</strong>
                      <small>Target {formatPercent(core.summary.model.target_accuracy_pct, 0)}</small>
                    </div>
                    <div>
                      <span>ATMs at risk</span>
                      <strong>{counts.critical + counts.watch}</strong>
                      <small>{counts.critical} critical · {counts.watch} warning</small>
                    </div>
                  </div>

                  <div className="briefing-source">
                    <Badge tone={core.status?.data_source === "synthetic_simulation" ? "warning" : "neutral"} dot>
                      {sourceLabel(core.status?.data_source)}
                    </Badge>
                    <span>Forecast mode: {core.status?.forecast_mode || "—"}</span>
                    {scenario.data && <Badge tone="warning" dot>Simulation</Badge>}
                  </div>

                  <section className="briefing-section">
                    <div className="briefing-section-head">
                      <h3>Most urgent cash cover</h3>
                      <span>{critical.length} shown</span>
                    </div>
                    {critical.length ? (
                      <div className="briefing-list">
                        {critical.map((row) => (
                          <div className="briefing-row" key={row.atm_id}>
                            <span className="briefing-row-icon"><Icon name="alert" size={15} /></span>
                            <div>
                              <strong>{row.atm_id}</strong>
                              <span>{row.location_name}</span>
                            </div>
                            <div className="briefing-row-metric">
                              <strong>{coverageLabel(row.coverage_ratio)}</strong>
                              <span>cover</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <EmptyState icon="shield" title="No critical ATMs" message="All monitored ATMs are above the critical cash-cover threshold." />
                    )}
                  </section>

                  <div className="drawer-note">
                    <Icon name="info" size={15} />
                    <span>
                      Cash cover and risk use the labelled simulation scenario estimate for the
                      next day. They are not live bank balances or approved replenishment orders.
                    </span>
                  </div>
                </>
              )}
            </div>

            <footer className="drawer-foot">
              <button
                type="button"
                className="button button-primary"
                onClick={() => { close(); navigate("alerts"); }}
              >
                Open alerts
              </button>
              <button
                type="button"
                className="button button-quiet"
                onClick={() => { close(); navigate("atms"); }}
              >
                ATM network
              </button>
            </footer>
          </aside>
        </div>
      )}
    </>
  );
}

function Topbar() {
  const { page, navigate, user } = useApp();
  const title = pageTitle(page);
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <div className="topbar-mobile-brand">
          <BrandMark size={30} />
          <strong>{title}</strong>
        </div>
        <nav className="top-tabs" aria-label="Page navigation">
          {TOP_TABS.map((item) => (
            <button
              type="button"
              key={item.id}
              className={classNames("top-tab", page === item.id && "is-active")}
              aria-current={page === item.id ? "page" : undefined}
              onClick={() => navigate(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="topbar-actions">
          <GlobalSearch />
          <Briefing />
          <button
            type="button"
            className="profile-button"
            aria-label={`Open settings for ${user.username}`}
            title={`${user.username} · ${user.role} access`}
            onClick={() => navigate("settings")}
          >
            {user.username.slice(0, 2).toUpperCase()}
          </button>
        </div>
      </div>
    </header>
  );
}

function MobileNav() {
  const { page, navigate, prefs, setPrefs } = useApp();
  return (
    <nav className="mobile-nav" aria-label="Mobile navigation">
      {NAV_ITEMS.map((item) => (
        <button
          type="button"
          key={item.id}
          className={classNames("mobile-nav-link", page === item.id && "is-active")}
          onClick={() => navigate(item.id)}
          aria-current={page === item.id ? "page" : undefined}
        >
          <Icon name={item.icon} size={19} />
          <span>{item.label === "What-if forecast" ? "What-if" : item.label}</span>
        </button>
      ))}
      <button
        type="button"
        className={classNames("mobile-nav-link", page === "settings" && "is-active")}
        onClick={() => navigate("settings")}
        aria-current={page === "settings" ? "page" : undefined}
      >
        <Icon name="settings" size={19} />
        <span>Settings</span>
      </button>
      <button
        type="button"
        className="mobile-nav-link"
        onClick={() => setPrefs((current) => ({
          ...current,
          theme: current.theme === "dark" ? "light" : "dark",
        }))}
        aria-label={prefs.theme === "dark" ? "Switch to light theme" : "Switch to dim theme"}
      >
        <Icon name={prefs.theme === "dark" ? "sun" : "moon"} size={19} />
        <span>Theme</span>
      </button>
    </nav>
  );
}

export default function Shell({ children }) {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <Rail />
      <div className="app-main">
        <Topbar />
        <main className="page-content" id="main-content" tabIndex={-1}>
          {children}
        </main>
      </div>
      <MobileNav />
    </div>
  );
}
