const app = document.getElementById("app");

// ── Tab navigation ───────────────────────────────────────────────

function renderTabs(activeTab) {
    return `
        <nav class="tab-bar">
            <button class="tab-btn${activeTab === "deals" ? " active" : ""}" data-tab="deals">Deals</button>
            <button class="tab-btn${activeTab === "grocery" ? " active" : ""}" data-tab="grocery">My List</button>
        </nav>
    `;
}

// ── Render helpers ────────────────────────────────────────────────

function renderToolbar(loading = false, currentCategory = null) {
    const exportUrl = currentCategory
        ? `/api/deals/export/pdf?category=${encodeURIComponent(currentCategory)}`
        : `/api/deals/export/pdf`;
    return `
        <div class="toolbar">
            <button id="scrape-btn" ${loading ? "disabled" : ""}>
                ${loading ? "Scraping…" : "Scrape all deals now"}
            </button>
            <a id="export-btn" class="toolbar-link" href="${exportUrl}" download>
                Download PDF
            </a>
            <button id="email-btn" ${loading ? "disabled" : ""}>
                Email PDF
            </button>
            <div id="category-filter" class="filter-bar"></div>
        </div>
    `;
}

function renderCard(deal) {
    const img = deal.image_url
        ? `<img src="${deal.image_url}" alt="" loading="lazy" referrerpolicy="no-referrer">`
        : `<div class="no-img"></div>`;
    const brand = deal.brand ? `<p class="deal-brand">${deal.brand}</p>` : "";
    const qty   = deal.qty   ? `<p class="deal-qty">${deal.qty}</p>`     : "";

    let priceLine;
    if (deal.promo_label) {
        priceLine = `<p class="deal-price">${deal.price.toFixed(2)} zł</p>
                     <p class="deal-promo">${deal.promo_label} <span class="badge">-${deal.discount_pct}%</span></p>`;
    } else {
        const badge = deal.discount_pct
            ? `<span class="badge">-${deal.discount_pct}%</span>` : "";
        const oldPrice = deal.old_price
            ? `<span class="old-price">${deal.old_price.toFixed(2)} zł</span>` : "";
        priceLine = `<p class="deal-price">${deal.price.toFixed(2)} zł ${oldPrice}${badge}</p>`;
    }

    const inner = `
        ${img}
        <div class="deal-info">
            ${brand}
            <p class="deal-name">${deal.name || "—"}</p>
            ${qty}
            ${priceLine}
            <p class="deal-category">${deal.category}</p>
            ${deal.matched_items ? `<p class="deal-matched">Matches: ${deal.matched_items.join(", ")}</p>` : ""}
        </div>
    `;

    return deal.product_url
        ? `<a class="deal-card" href="${deal.product_url}" target="_blank" rel="noopener noreferrer">${inner}</a>`
        : `<div class="deal-card no-link">${inner}</div>`;
}

function renderGrid(deals) {
    if (!deals.length) {
        return `<p class="empty">No deals yet — click "Scrape all deals now" to fetch.</p>`;
    }
    return `<div class="deals-grid">${deals.map(renderCard).join("")}</div>`;
}

// ── Data fetching ─────────────────────────────────────────────────

async function fetchDeals(category = null) {
    const path = category
        ? `/deals?category=${encodeURIComponent(category)}`
        : "/deals";
    const data = await apiFetch(path);
    return data.deals;
}

async function fetchMyListDeals(category = null) {
    const path = category
        ? `/deals/my-list?category=${encodeURIComponent(category)}`
        : "/deals/my-list";
    const data = await apiFetch(path);
    return data.deals;
}

async function fetchCategories() {
    const data = await apiFetch("/deals/categories");
    return data.categories;
}

async function triggerScrape() {
    return apiFetch("/scrape", { method: "POST" });
}


// ── App ───────────────────────────────────────────────────────────

async function init() {
    // Handle email confirmation redirect
    const params = new URLSearchParams(location.search);
    let confirmedMessage = "";
    if (params.get("confirmed") === "1") {
        history.replaceState({}, "", "/");
        confirmedMessage = "Email confirmed! You can now sign in.";
    }

    // Auth gate
    const user = await getCurrentUser();
    if (!user) {
        app.innerHTML = renderLoginView(confirmedMessage);
        wireAuthForms();
        return;
    }

    let activeTab = "deals";
    let currentCategory = null;
    let deals = [];
    let groceryItems = [];
    let editingGroceryId = null;
    let myListDeals = null; // null = not loaded, [] = loaded but empty

    try { deals = await fetchDeals(); } catch (_) { /* empty on first run */ }

    function render(loading = false) {
        let content;
        if (activeTab === "grocery") {
            content = renderGroceryView(groceryItems, editingGroceryId, myListDeals);
        } else {
            content = renderToolbar(loading, currentCategory) + renderGrid(deals);
        }
        app.innerHTML = renderAuthBar(user.email) + renderTabs(activeTab) + content;
        wireAuthBar();
        wireTabs();

        if (activeTab === "grocery") {
            wireGroceryView(groceryItems, editingGroceryId, async (editId) => {
                editingGroceryId = editId || null;
                try { groceryItems = await fetchGroceryItems(); } catch (_) {}
                if (myListDeals !== null) {
                    try { myListDeals = await fetchMyListDeals(); } catch (_) {}
                }
                render();
            });
            wireMyListDealsButton();
        } else if (!loading) {
            wireScrapeButton();
            wireEmailButton();
            renderCategoryFilter();
        }
    }

    function wireTabs() {
        document.querySelectorAll(".tab-btn").forEach(btn => {
            btn.addEventListener("click", async () => {
                const tab = btn.dataset.tab;
                if (tab === activeTab) return;
                activeTab = tab;
                if (tab === "grocery") {
                    try { groceryItems = await fetchGroceryItems(); } catch (_) {}
                    myListDeals = null;
                }
                editingGroceryId = null;
                render();
            });
        });
    }

    async function renderCategoryFilter() {
        let cats;
        try { cats = await fetchCategories(); } catch (_) { return; }
        if (!cats.length) return;

        const bar = document.getElementById("category-filter");
        if (!bar) return;

        const buttons = [{ label: "Wszystkie", value: "" }, ...cats.map(c => ({ label: c, value: c }))]
            .map(({ label, value }) => {
                const active = value === (currentCategory || "");
                return `<button class="cat-btn${active ? " active" : ""}" data-cat="${value}">${label}</button>`;
            })
            .join("");
        bar.innerHTML = buttons;

        bar.querySelectorAll(".cat-btn").forEach(btn => {
            btn.addEventListener("click", async () => {
                currentCategory = btn.dataset.cat || null;
                deals = await fetchDeals(currentCategory);
                render();
            });
        });
    }

    function wireScrapeButton() {
        const btn = document.getElementById("scrape-btn");
        if (!btn) return;
        btn.addEventListener("click", async () => {
            render(true);
            let scrapeOk = false;
            try {
                await triggerScrape();
                deals = await fetchDeals(currentCategory);
                scrapeOk = true;
            } catch (err) {
                alert(`Scrape failed: ${err.message}`);
            }
            render();
            if (scrapeOk) {
                // Re-fetch after a delay to pick up images populated by the async lookup
                setTimeout(async () => {
                    if (activeTab !== "deals") return;
                    try {
                        deals = await fetchDeals(currentCategory);
                        render();
                    } catch (_) {}
                }, 8000);
            }
        });
    }

    function wireMyListDealsButton() {
        const btn = document.getElementById("mylist-deals-btn");
        if (!btn) return;
        btn.addEventListener("click", async () => {
            if (myListDeals !== null) {
                myListDeals = null;
            } else {
                try {
                    myListDeals = await fetchMyListDeals();
                } catch (err) {
                    alert(`Failed to load deals: ${err.message}`);
                    return;
                }
            }
            render();
        });
    }

    function wireEmailButton() {
        const btn = document.getElementById("email-btn");
        if (!btn) return;
        btn.addEventListener("click", async () => {
            btn.disabled = true;
            btn.textContent = "Sending…";
            const path = currentCategory
                ? `/deals/export/email?category=${encodeURIComponent(currentCategory)}`
                : "/deals/export/email";
            try {
                await apiFetch(path, { method: "POST" });
                alert("Report sent to jgawry@gmail.com");
            } catch (err) {
                alert(`Email failed: ${err.message}`);
            }
            btn.disabled = false;
            btn.textContent = "Email PDF";
        });
    }

    render();
}

init();
