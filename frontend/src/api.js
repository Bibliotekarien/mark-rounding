// Thin fetch wrapper. All URLs are relative — same origin in dev (Vite
// proxy) and prod (FastAPI serves the SPA). The admin token lives in
// localStorage; committee reporting needs no auth beyond its secret URL.

let adminToken = localStorage.getItem("markrounding_admin_token") || null;

export function setAdminToken(token) {
  adminToken = token;
  if (token) localStorage.setItem("markrounding_admin_token", token);
  else localStorage.removeItem("markrounding_admin_token");
}

export function hasAdminToken() {
  return !!adminToken;
}

async function request(method, path, body) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (adminToken && path.startsWith("/api/admin")) {
    headers["Authorization"] = `Bearer ${adminToken}`;
  }
  const resp = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (resp.status === 401 && path.startsWith("/api/admin")) {
    setAdminToken(null);
    window.dispatchEvent(new CustomEvent("markrounding:unauthorized"));
  }
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const data = await resp.json();
      if (data.detail) detail = data.detail;
    } catch {
      /* keep generic detail */
    }
    const err = new Error(detail);
    err.status = resp.status;
    throw err;
  }
  if (resp.status === 204) return null;
  return resp.json();
}

const get = (path) => request("GET", path);
const post = (path, body) => request("POST", path, body);
const patch = (path, body) => request("PATCH", path, body);
const put = (path, body) => request("PUT", path, body);
const del = (path) => request("DELETE", path);

export const api = {
  // public
  regattas: () => get("/api/regattas"),
  regatta: (slug) => get(`/api/regattas/${slug}`),
  race: (slug, number) => get(`/api/regattas/${slug}/races/${number}`),
  weather: (slug) => get(`/api/regattas/${slug}/weather`),

  // committee reporting (secret token)
  report: (token) => get(`/api/report/${token}`),
  reportRace: (token, number) => get(`/api/report/${token}/races/${number}`),
  addRounding: (token, number, markId, boatId) =>
    post(`/api/report/${token}/races/${number}/roundings`, {
      mark_id: markId,
      boat_id: boatId,
    }),
  undoRounding: (token, roundingId) =>
    del(`/api/report/${token}/roundings/${roundingId}`),
  setRaceStatus: (token, number, status) =>
    post(`/api/report/${token}/races/${number}/status`, { status }),
  startSequence: (token, number, minutes, prepFlag) =>
    post(`/api/report/${token}/races/${number}/start-sequence`, {
      minutes,
      prep_flag: prepFlag,
    }),
  postpone: (token, number) =>
    del(`/api/report/${token}/races/${number}/start-sequence`),
  generalRecall: (token, number) =>
    post(`/api/report/${token}/races/${number}/general-recall`),
  setBoatCode: (token, number, boatId, code) =>
    put(`/api/report/${token}/races/${number}/boats/${boatId}/status`, { code }),
  clearBoatCode: (token, number, boatId) =>
    del(`/api/report/${token}/races/${number}/boats/${boatId}/status`),
  raceLog: (token, number) => get(`/api/report/${token}/races/${number}/log`),
  addLogNote: (token, number, note) =>
    post(`/api/report/${token}/races/${number}/log`, { note }),
  reportAddBoat: (token, boat) => post(`/api/report/${token}/boats`, boat),
  reportPatchBoat: (token, boatId, fields) =>
    patch(`/api/report/${token}/boats/${boatId}`, fields),
  reportSetMarks: (token, marks) => put(`/api/report/${token}/marks`, { marks }),

  // admin
  login: (password) => post("/api/auth/login", { password }),
  adminRegattas: () => get("/api/admin/regattas"),
  adminRegatta: (id) => get(`/api/admin/regattas/${id}`),
  createRegatta: (body) => post("/api/admin/regattas", body),
  patchRegatta: (id, body) => patch(`/api/admin/regattas/${id}`, body),
  deleteRegatta: (id) => del(`/api/admin/regattas/${id}`),
  regenerateToken: (id) => post(`/api/admin/regattas/${id}/regenerate-token`),
  setMarks: (id, marks) => put(`/api/admin/regattas/${id}/marks`, { marks }),
  sailarenaPreview: (url) => post("/api/admin/sailarena/preview", { url }),
  importBoats: (id, boats, replace) =>
    post(`/api/admin/regattas/${id}/boats/import`, { boats, replace }),
  adminAddBoat: (id, boat) => post(`/api/admin/regattas/${id}/boats`, boat),
  adminPatchBoat: (id, boatId, fields) =>
    patch(`/api/admin/regattas/${id}/boats/${boatId}`, fields),
  adminDeleteBoat: (id, boatId) => del(`/api/admin/regattas/${id}/boats/${boatId}`),
};
