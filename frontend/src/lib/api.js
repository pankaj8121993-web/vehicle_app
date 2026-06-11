import axios from "axios";

const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`,
  withCredentials: true,
});

// Attach the selected role so the backend can enforce per-role rights
api.interceptors.request.use((config) => {
  const role = localStorage.getItem("fleet_role");
  if (role) config.headers["X-Role"] = role;
  return config;
});

export default api;
