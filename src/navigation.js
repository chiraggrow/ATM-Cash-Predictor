export const NAV_ITEMS = [
  { id: "overview", label: "Overview", icon: "home", title: "Cash demand overview" },
  { id: "atms", label: "ATMs", icon: "bank", title: "ATM network" },
  { id: "whatif", label: "What-if forecast", icon: "activity", title: "What-if forecast" },
  { id: "replenishment", label: "Replenishment", icon: "truck", title: "Replenishment plan" },
  { id: "alerts", label: "Alerts", icon: "bell", title: "Alerts" },
];

export const TOP_TABS = [
  ...NAV_ITEMS,
  { id: "settings", label: "Settings", icon: "settings", title: "Settings" },
];

export const PAGE_NAMES = TOP_TABS.map((item) => item.id);

export function pageTitle(page) {
  return TOP_TABS.find((item) => item.id === page)?.title || "Cash demand overview";
}
