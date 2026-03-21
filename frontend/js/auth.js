// ── Token storage ─────────────────────────────────────────────────

function getToken() {
    return localStorage.getItem("fc_token");
}

function setToken(token) {
    localStorage.setItem("fc_token", token);
}

function clearToken() {
    localStorage.removeItem("fc_token");
}

// ── Current user ──────────────────────────────────────────────────

async function getCurrentUser() {
    if (!getToken()) return null;
    try {
        return await apiFetch("/auth/me");
    } catch (_) {
        return null;
    }
}

// ── Auth bar (shown when logged in) ───────────────────────────────

function renderAuthBar(email) {
    return `
        <div class="auth-bar">
            Logged in as <strong>${email}</strong>
            <button class="auth-bar-logout" id="logout-btn">Logout</button>
        </div>
    `;
}

function wireAuthBar() {
    const btn = document.getElementById("logout-btn");
    if (!btn) return;
    btn.addEventListener("click", () => {
        clearToken();
        window.location.reload();
    });
}

// ── Login form ────────────────────────────────────────────────────

function renderLoginView(message = "") {
    const banner = message
        ? `<p class="auth-banner">${message}</p>`
        : "";
    return `
        <div class="auth-container">
            ${banner}
            <h2>Sign in</h2>
            <form class="auth-form" id="login-form">
                <input type="email" id="login-email" placeholder="Email" required autocomplete="email">
                <input type="password" id="login-password" placeholder="Password" required autocomplete="current-password">
                <p class="auth-error" id="login-error"></p>
                <button type="submit">Sign in</button>
            </form>
            <p class="auth-switch">No account? <a href="#" id="go-register">Register</a></p>
        </div>
    `;
}

// ── Register form ─────────────────────────────────────────────────

function renderRegisterView() {
    return `
        <div class="auth-container">
            <h2>Create account</h2>
            <form class="auth-form" id="register-form">
                <input type="email" id="reg-email" placeholder="Email" required autocomplete="email">
                <input type="password" id="reg-password" placeholder="Password (min 8 chars)" required autocomplete="new-password">
                <p class="auth-error" id="reg-error"></p>
                <button type="submit">Register</button>
            </form>
            <p class="auth-switch">Already have an account? <a href="#" id="go-login">Sign in</a></p>
        </div>
    `;
}

// ── Wire auth forms ───────────────────────────────────────────────

function wireAuthForms() {
    const loginForm = document.getElementById("login-form");
    if (loginForm) {
        loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const email = document.getElementById("login-email").value;
            const password = document.getElementById("login-password").value;
            const errorEl = document.getElementById("login-error");
            errorEl.textContent = "";
            try {
                const data = await apiFetch("/auth/login", {
                    method: "POST",
                    body: JSON.stringify({ email, password }),
                });
                setToken(data.token);
                init();
            } catch (err) {
                const status = err.message.match(/\d+/)?.[0];
                if (status === "403") {
                    errorEl.innerHTML = 'Please confirm your email before logging in. <a href="#" id="resend-link">Resend confirmation</a>';
                    document.getElementById("resend-link")?.addEventListener("click", async (ev) => {
                        ev.preventDefault();
                        try {
                            await apiFetch("/auth/resend-confirmation", {
                                method: "POST",
                                body: JSON.stringify({ email }),
                            });
                            errorEl.innerHTML = "";
                            errorEl.textContent = "Confirmation email sent! Check your inbox.";
                            errorEl.style.color = "#2a9d4e";
                        } catch (_) {
                            errorEl.textContent = "Failed to resend. Try again later.";
                        }
                    });
                } else {
                    errorEl.textContent = "Invalid email or password.";
                }
            }
        });
    }

    const registerForm = document.getElementById("register-form");
    if (registerForm) {
        registerForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const email = document.getElementById("reg-email").value;
            const password = document.getElementById("reg-password").value;
            const errorEl = document.getElementById("reg-error");
            errorEl.textContent = "";
            try {
                await apiFetch("/auth/register", {
                    method: "POST",
                    body: JSON.stringify({ email, password }),
                });
                // Show login form with success message
                const app = document.getElementById("app");
                app.innerHTML = renderLoginView("Registration successful! Check your email to confirm your account.");
                wireAuthForms();
            } catch (err) {
                const status = err.message.match(/\d+/)?.[0];
                if (status === "409") {
                    errorEl.textContent = "This email is already registered.";
                } else {
                    errorEl.textContent = "Registration failed. Please try again.";
                }
            }
        });
    }

    document.getElementById("go-register")?.addEventListener("click", (e) => {
        e.preventDefault();
        document.getElementById("app").innerHTML = renderRegisterView();
        wireAuthForms();
    });

    document.getElementById("go-login")?.addEventListener("click", (e) => {
        e.preventDefault();
        document.getElementById("app").innerHTML = renderLoginView();
        wireAuthForms();
    });
}
