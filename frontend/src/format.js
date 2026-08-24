// Shared display helpers. Backend timestamps are ISO UTC; render in the
// viewer's local timezone.

export function fmtTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("sv-SE", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function fmtDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("sv-SE");
}

export function fmtDateRange(start, end) {
  if (!start) return "";
  if (!end || end === start) return fmtDate(start);
  return `${fmtDate(start)} – ${fmtDate(end)}`;
}

export function fmtGap(seconds) {
  if (seconds == null) return "";
  if (seconds === 0) return "0:00";
  const m = Math.floor(seconds / 60);
  return `+${m}:${String(seconds % 60).padStart(2, "0")}`;
}

export const raceStatusLabel = {
  upcoming: "Kommande",
  ongoing: "Pågår",
  finished: "Avslutat",
};

export const prepFlagLabel = {
  P: "P — vanlig",
  I: "I — runda ändar (30.1)",
  Z: "Z — 20 %-straff (30.2)",
  U: "U — DSQ, ej vid omstart (30.3)",
  BLACK: "Svart — DSQ även vid omstart (30.4)",
};

export const boatCodeLabel = {
  OCS: "Tjuvstart (OCS)",
  UFD: "U-flagg (UFD)",
  BFD: "Svart flagg (BFD)",
  ZFP: "Z-flagg 20 % (ZFP)",
  DNS: "Startade ej (DNS)",
  DNF: "Fullföljde ej (DNF)",
  RET: "Utgått (RET)",
  DSQ: "Diskvalificerad (DSQ)",
};

export const logEventLabel = {
  course_set: "Bana vald",
  shortened: "Avkortad bana (S)",
  sequence: "Startsekvens",
  postpone: "AP — uppskjutet",
  start: "Startsignal",
  general_recall: "Allmän återkallelse",
  finish: "Race avslutat",
  reset: "Race återställt",
  race_reset: "Racet nollställt av admin",
  boat_status: "Markering",
  boat_status_cleared: "Markering borttagen",
  rounding_undone: "Rundning ångrad",
  weather: "Väder vid start",
  note: "Anteckning",
};

// WMO weather codes -> short Swedish description + emoji.
const WEATHER_CODES = [
  [[0], "☀️ Klart"],
  [[1, 2], "🌤 Mest klart"],
  [[3], "☁️ Mulet"],
  [[45, 48], "🌫 Dimma"],
  [[51, 53, 55, 56, 57], "🌦 Duggregn"],
  [[61, 63, 65, 66, 67], "🌧 Regn"],
  [[71, 73, 75, 77], "🌨 Snö"],
  [[80, 81, 82], "🌦 Regnskurar"],
  [[85, 86], "🌨 Snöbyar"],
  [[95, 96, 99], "⛈ Åska"],
];

export function weatherLabel(code) {
  for (const [codes, label] of WEATHER_CODES) {
    if (codes.includes(code)) return label;
  }
  return "";
}

export function windArrow(directionFrom) {
  if (directionFrom == null) return "";
  // Arrow points where the wind blows *to*.
  const arrows = ["↓", "↙", "←", "↖", "↑", "↗", "→", "↘"];
  return arrows[Math.round((directionFrom % 360) / 45) % 8];
}

export function compass(directionFrom) {
  if (directionFrom == null) return "";
  const dirs = ["N", "NO", "O", "SO", "S", "SV", "V", "NV"];
  return dirs[Math.round((directionFrom % 360) / 45) % 8];
}
