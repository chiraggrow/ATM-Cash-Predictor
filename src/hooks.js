import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest } from "./data.js";

export function useLocalStorage(key, initialValue) {
  const [value, setValue] = useState(() => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored === null ? initialValue : JSON.parse(stored);
    } catch {
      return initialValue;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Storage can be unavailable in private browsing; the UI remains functional.
    }
  }, [key, value]);

  useEffect(() => {
    function sync(event) {
      if (event.key !== key || event.newValue === null) return;
      try {
        setValue(JSON.parse(event.newValue));
      } catch {
        // Ignore values written by another tab that are not valid JSON.
      }
    }
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, [key]);

  return [value, setValue];
}

export function useApi(path, {
  token,
  method = "GET",
  body = null,
  enabled = true,
  refreshKey = 0,
} = {}) {
  const bodyKey = body === null ? "" : JSON.stringify(body);
  const [state, setState] = useState({
    data: null,
    loading: Boolean(enabled),
    error: "",
  });
  const [reloadKey, setReloadKey] = useState(0);
  const reload = useCallback(() => setReloadKey((current) => current + 1), []);

  useEffect(() => {
    if (!enabled || !path) {
      setState((current) => ({ ...current, loading: false }));
      return undefined;
    }
    const controller = new AbortController();
    let active = true;
    setState((current) => ({ ...current, loading: true, error: "" }));
    apiRequest(path, {
      token,
      signal: controller.signal,
      method,
      headers: body === null ? undefined : { "Content-Type": "application/json" },
      body: body === null ? undefined : bodyKey,
    })
      .then((data) => {
        if (active) setState({ data, loading: false, error: "" });
      })
      .catch((error) => {
        if (!active || error?.name === "AbortError") return;
        setState((current) => ({
          data: current.data,
          loading: false,
          error: error?.message || "The request failed.",
        }));
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [path, token, method, bodyKey, enabled, refreshKey, reloadKey]);

  return { ...state, reload };
}

export function useDebouncedValue(value, delay = 250) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function parseHash(defaultPage) {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [candidate, queryString = ""] = raw.split("?");
  const params = Object.fromEntries(new URLSearchParams(queryString));
  return {
    page: candidate || defaultPage,
    params,
  };
}

export function useHashRoute(knownPages, defaultPage = "overview") {
  const [route, setRoute] = useState(() => {
    const initial = parseHash(defaultPage);
    return knownPages.includes(initial.page)
      ? initial
      : { page: defaultPage, params: {} };
  });

  useEffect(() => {
    function onHashChange() {
      const next = parseHash(defaultPage);
      setRoute(
        knownPages.includes(next.page)
          ? next
          : { page: defaultPage, params: {} },
      );
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, [knownPages, defaultPage]);

  const navigate = useCallback((page, params = {}) => {
    const target = knownPages.includes(page) ? page : defaultPage;
    const query = new URLSearchParams(
      Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== ""),
    ).toString();
    const hash = `#/${target}${query ? `?${query}` : ""}`;
    if (window.location.hash === hash) {
      setRoute({ page: target, params });
    } else {
      window.location.hash = hash;
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [knownPages, defaultPage]);

  return { ...route, navigate };
}

export function useEscapeKey(active, handler) {
  useEffect(() => {
    if (!active) return undefined;
    function onKeyDown(event) {
      if (event.key === "Escape") handler(event);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [active, handler]);
}

export function useOutsideClick(ref, handler, active = true) {
  useEffect(() => {
    if (!active) return undefined;
    function onPointerDown(event) {
      if (!ref.current || ref.current.contains(event.target)) return;
      handler(event);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [ref, handler, active]);
}

export function useStoredSet(key) {
  const [values, setValues] = useLocalStorage(key, []);
  const has = useCallback((value) => values.includes(value), [values]);
  const add = useCallback((value) => {
    setValues((current) => (current.includes(value) ? current : [...current, value]));
  }, [setValues]);
  const remove = useCallback((value) => {
    setValues((current) => current.filter((item) => item !== value));
  }, [setValues]);
  const toggle = useCallback((value) => {
    setValues((current) => (current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value]));
  }, [setValues]);
  return { values, setValues, has, add, remove, toggle };
}
