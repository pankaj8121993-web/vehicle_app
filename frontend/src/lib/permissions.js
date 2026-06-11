// Role-based access rights (no login — role chosen on entry screen)
const DRIVER_CREATE = ["trips", "fuel", "repairs"];

export const canCreate = (role, endpoint) => (role === "driver" ? DRIVER_CREATE.includes(endpoint) : true);
export const canEdit = (role) => role !== "driver";
export const canDelete = (role) => role === "admin";
export const canApprove = (role) => ["management", "admin"].includes(role);
