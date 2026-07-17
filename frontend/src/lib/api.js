import axios from "axios";

// AUTH-01: the session is an HttpOnly cookie set by the backend, so it is not
// readable by script and is never held in localStorage. `withCredentials` is
// what makes the browser attach it.
const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`,
  withCredentials: true,
});

const CSRF_COOKIE = "fleet_csrf";
const CSRF_HEADER = "X-CSRF-Token";
const SAFE_METHODS = ["get", "head", "options"];

function readCookie(name) {
  const match = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)")
  );
  return match ? decodeURIComponent(match[1]) : null;
}

// Double-submit CSRF: the backend sets a readable fleet_csrf cookie alongside
// the HttpOnly session cookie, and we echo it back in a header. A cross-site
// page can make the browser send the session cookie but cannot read this one,
// so it cannot forge the header.
api.interceptors.request.use((config) => {
  const method = (config.method || "get").toLowerCase();
  if (!SAFE_METHODS.includes(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) config.headers[CSRF_HEADER] = csrf;
  }
  return config;
});

// Auto-redirect on 401. The session cookie is cleared server-side on logout and
// on expiry; only the cached display profile is dropped here.
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401) {
      localStorage.removeItem("fleet_user");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export default api;
