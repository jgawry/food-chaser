const API_BASE = "/api";

async function apiFetch(path, options = {}) {
    const headers = { "Content-Type": "application/json" };
    const token = localStorage.getItem("fc_token");
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const response = await fetch(`${API_BASE}${path}`, { headers, ...options });

    if (response.status === 401 && !path.startsWith("/auth/")) {
        localStorage.removeItem("fc_token");
        window.location.reload();
        return;
    }

    if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
    }
    return response.json();
}
