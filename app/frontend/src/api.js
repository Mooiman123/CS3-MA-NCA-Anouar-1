import axios from "axios";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
});

export const setAuthEmail = (email) => {
  if (email) {
    api.defaults.headers.common["X-User-Email"] = email;
  } else {
    delete api.defaults.headers.common["X-User-Email"];
  }
};

export const login = (payload) => api.post("/auth/login", payload);
export const createEmployee = (payload) => api.post("/employees", payload);
export const listEmployees = () => api.get("/employees");
export const updateEmployee = (id, payload) => api.put(`/employees/${id}`, payload);
export const deleteEmployee = (id) => api.delete(`/employees/${id}`);

export default api;
