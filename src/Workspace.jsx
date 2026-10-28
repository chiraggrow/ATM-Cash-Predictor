import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AppContext, PREFERENCE_DEFAULTS } from "./AppContext.jsx";
import Shell from "./components/Shell.jsx";
import { ErrorState } from "./components/ui.jsx";
import { apiRequest } from "./data.js";
import { useHashRoute, useLocalStorage } from "./hooks.js";
import { PAGE_NAMES } from "./navigation.js";
import Alerts from "./pages/Alerts.jsx";
import ATMs from "./pages/ATMs.jsx";
import Overview from "./pages/Overview.jsx";
import Replenishment from "./pages/Replenishment.jsx";
import Settings from "./pages/Settings.jsx";
import WhatIf from "./pages/WhatIf.jsx";

const EMPTY_CORE = {
  summary: null,
  status: null,
  atms: [],
  metadata: [],
  databaseSummary: null,
};

const PAGE_COMPONENTS = {
  overview: Overview,
  atms: ATMs,
  whatif: WhatIf,
  replenishment: Replenishment,
  alerts: Alerts,
  settings: Settings,
};

export default function Workspace({ token, user, onLogout }) {
  const { page, params, navigate } = useHashRoute(PAGE_NAMES, "overview");
  const [storedPreferences, setStoredPreferences] = useLocalStorage(
    "cashcast.preferences.v1",
    PREFERENCE_DEFAULTS,
  );
  const preferences = useMemo(
    () => ({ ...PREFERENCE_DEFAULTS, ...storedPreferences }),
    [storedPreferences],
  );
  const [core, setCore] = useState(EMPTY_CORE);
  const [coreLoading, setCoreLoading] = useState(true);
  const [coreError, setCoreError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const refreshCore = useCallback(() => {
    setRefreshKey((current) => current + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setCoreLoading(true);
    setCoreError("");

    Promise.all([
      apiRequest("/analytics/summary", { token, signal: controller.signal }),
      apiRequest("/model/status", { token, signal: controller.signal }),
      apiRequest("/atms?limit=100", { token, signal: controller.signal }),
      apiRequest("/data/atms?limit=500", { token, signal: controller.signal }),
      apiRequest("/data/summary", { token, signal: controller.signal }),
    ])
      .then(([summary, status, atmPage, metadataPage, databaseSummary]) => {
        if (!active) return;
        setCore({
          summary,
          status,
          atms: atmPage.items || [],
          metadata: metadataPage.items || [],
          databaseSummary,
        });
        setCoreLoading(false);
      })
      .catch((error) => {
        if (!active || error?.name === "AbortError") return;
        setCoreError(error?.message || "The dashboard data could not be loaded.");
        setCoreLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [token, refreshKey]);

  useEffect(() => {
    function handleUnauthorized() {
      onLogout();
    }
    window.addEventListener("cashcast:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("cashcast:unauthorized", handleUnauthorized);
  }, [onLogout]);

  useEffect(() => {
    document.documentElement.dataset.theme = preferences.theme;
    document.documentElement.dataset.density = preferences.density;
  }, [preferences.theme, preferences.density]);

  const Page = PAGE_COMPONENTS[page] || Overview;

  const contextValue = useMemo(
    () => ({
      token,
      user,
      onLogout,
      core,
      coreLoading,
      coreError,
      refreshCore,
      prefs: preferences,
      setPrefs: setStoredPreferences,
      page,
      params,
      navigate,
    }),
    [
      token,
      user,
      onLogout,
      core,
      coreLoading,
      coreError,
      refreshCore,
      preferences,
      setStoredPreferences,
      page,
      params,
      navigate,
    ],
  );

  return (
    <AppContext.Provider value={contextValue}>
      <Shell>
        {coreError && (
          <ErrorState message={coreError} onRetry={refreshCore} />
        )}
        <Page />
      </Shell>
    </AppContext.Provider>
  );
}
