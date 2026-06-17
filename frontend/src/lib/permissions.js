// Role-based access rights — uses real user role from AuthContext
const DRIVER_CREATE = ["trips", "fuel", "repairs"];

export const canCreate = (role, endpoint) => {
  if (role === "driver") return DRIVER_CREATE.includes(endpoint);
  return ["data_entry", "management", "admin", "test"].includes(role);
};
export const canEdit = (role) => ["data_entry", "management", "admin", "test"].includes(role);
export const canDelete = (role) => ["admin", "test"].includes(role);
export const canApprove = (role) => ["management", "admin"].includes(role);
