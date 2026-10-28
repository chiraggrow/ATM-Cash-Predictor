import { createContext, useContext } from "react";

export const AppContext = createContext(null);

export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp must be used inside the CashCast workspace.");
  return value;
}

export const PREFERENCE_DEFAULTS = {
  theme: "light",
  defaultMonths: 12,
  compactNumbers: true,
  density: "comfortable",
};
