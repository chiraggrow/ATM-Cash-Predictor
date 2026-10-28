import React, { useCallback, useEffect, useState } from "react";
import Login from "./pages/Login.jsx";
import Workspace from "./Workspace.jsx";
import { apiRequest, clearAccessToken, getAccessToken } from "./data.js";
import { BrandMark } from "./icons.jsx";

const PREFERENCE_KEY = "cashcast.preferences.v1";

function readStoredTheme() {
  try {
    const stored = JSON.parse(window.localStorage.getItem(PREFERENCE_KEY) || "{}");
    return stored.theme === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function SessionSplash({ message }) {
  return (
    <main className="session-splash" aria-busy="true">
      <BrandMark size={46} />
      <div>
        <strong>CashCast</strong>
        <span>{message}</span>
      </div>
      <span className="spinner" aria-hidden="true" />
    </main>
  );
}

export default function App() {
  const [token, setToken] = useState(() => getAccessToken());
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(() => Boolean(getAccessToken()));
  const [sessionError, setSessionError] = useState("");

  const logout = useCallback(() => {
    clearAccessToken();
    setToken(null);
    setUser(null);
    setChecking(false);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = readStoredTheme();
  }, []);

  useEffect(() => {
    if (!token || user) {
      setChecking(false);
      return undefined;
    }
    const controller = new AbortController();
    let active = true;
    setChecking(true);
    apiRequest("/auth/me", { token, signal: controller.signal })
      .then((profile) => {
        if (!active) return;
        setUser(profile);
        setSessionError("");
      })
      .catch((error) => {
        if (!active || error?.name === "AbortError") return;
        clearAccessToken();
        setToken(null);
        setSessionError(
          error?.status === 401
            ? "Your session expired. Sign in again."
            : error?.message || "The session could not be verified.",
        );
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [token, user]);

  useEffect(() => {
    function handleUnauthorized() {
      logout();
      setSessionError("Your session expired. Sign in again.");
    }
    window.addEventListener("cashcast:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("cashcast:unauthorized", handleUnauthorized);
  }, [logout]);

  useEffect(() => {
    if (!token) return undefined;
    function onStorage(event) {
      if (event.key === "atm-cash-access-token" && event.newValue === null) {
        setToken(null);
        setUser(null);
      }
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [token]);

  if (checking && token && !user) {
    return (
      <div className="app-root">
        <SessionSplash message="Verifying your secure session" />
      </div>
    );
  }

  if (!token || !user) {
    return (
      <div className="app-root">
        <Login
          sessionError={sessionError}
          onLogin={(nextToken, profile) => {
            setToken(nextToken);
            setUser(profile);
            setSessionError("");
          }}
        />
      </div>
    );
  }

  return (
    <div className="app-root">
      <Workspace token={token} user={user} onLogout={logout} />
    </div>
  );
}
