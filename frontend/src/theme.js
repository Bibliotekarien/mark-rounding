// Theme handling: light (default), dark, and a super-high-contrast mode
// for working in direct sunlight on the water. The choice is stamped as
// data-theme on <html> and persisted per device.

const STORAGE_KEY = "markrounding_theme";

export const themes = [
  { id: "light", label: "Ljust", icon: "☀️" },
  { id: "dark", label: "Mörkt", icon: "🌙" },
  { id: "contrast", label: "Superkontrast", icon: "🔆" },
];

export function currentTheme() {
  return document.documentElement.dataset.theme || "light";
}

export function applyTheme(id) {
  document.documentElement.dataset.theme = id;
  localStorage.setItem(STORAGE_KEY, id);
  // Components with canvas rendering (charts) listen and repaint.
  window.dispatchEvent(new CustomEvent("markrounding:theme", { detail: id }));
}

export function initTheme() {
  const saved = localStorage.getItem(STORAGE_KEY);
  document.documentElement.dataset.theme = themes.some((t) => t.id === saved)
    ? saved
    : "light";
}
