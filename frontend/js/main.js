const app = document.getElementById("app");

// ── Render helpers ────────────────────────────────────────────────

function renderToolbar(loading = false, currentCategory = null) {
    const exportUrl = currentCategory
        ? `/api/deals/export/pdf?category=${encodeURIComponent(currentCategory)}`
        : `/api/deals/export/pdf`;
    return `
        <div class="toolbar">
            <button id="scrape-btn" ${loading ? "disabled" : ""}>
                ${loading ? "Scraping…" : "Scrape Lidl deals now"}
            </button>
            <button id="leaflet-btn" ${loading ? "disabled" : ""}>
                Import leaflet PDF
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
        </div>
    `;

    return deal.product_url
        ? `<a class="deal-card" href="${deal.product_url}" target="_blank" rel="noopener noreferrer">${inner}</a>`
        : `<div class="deal-card no-link">${inner}</div>`;
}

function renderGrid(deals) {
    if (!deals.length) {
        return `<p class="empty">No deals yet — click "Scrape Lidl deals now" to fetch.</p>`;
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

async function fetchCategories() {
    const data = await apiFetch("/deals/categories");
    return data.categories;
}

async function triggerScrape() {
    return apiFetch("/scrape", { method: "POST" });
}

async function triggerLeafletScrape(pdfPath) {
    return apiFetch("/scrape/leaflet", {
        method: "POST",
        body: JSON.stringify({ pdf_path: pdfPath }),
    });
}

// ── App ───────────────────────────────────────────────────────────

async function init() {
    let currentCategory = null;
    let deals = [];

    try { deals = await fetchDeals(); } catch (_) { /* empty on first run */ }

    function render(loading = false) {
        app.innerHTML = renderToolbar(loading, currentCategory) + renderGrid(deals);
        if (!loading) {
            wireScrapeButton();
            wireLeafletButton();
            wireEmailButton();
            renderCategoryFilter();
        }
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
            try {
                await triggerScrape();
                deals = await fetchDeals(currentCategory);
            } catch (err) {
                alert(`Scrape failed: ${err.message}`);
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

    function wireLeafletButton() {
        const btn = document.getElementById("leaflet-btn");
        if (!btn) return;
        btn.addEventListener("click", async () => {
            const pdfPath = prompt("Enter the full path to the leaflet PDF:");
            if (!pdfPath) return;
            render(true);
            try {
                const result = await triggerLeafletScrape(pdfPath.trim());
                deals = await fetchDeals(currentCategory);
                alert(`Imported ${result.parsed} deals from the leaflet.`);
            } catch (err) {
                alert(`Import failed: ${err.message}`);
            }
            render();
        });
    }

    render();
}

init();
