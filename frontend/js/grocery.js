// ── Grocery list API ─────────────────────────────────────────────

async function fetchGroceryItems() {
    const data = await apiFetch("/grocery-list");
    return data.items;
}

async function addGroceryItem(name, quantity) {
    const body = { name };
    if (quantity) body.quantity = quantity;
    const data = await apiFetch("/grocery-list", {
        method: "POST",
        body: JSON.stringify(body),
    });
    return data.item;
}

async function updateGroceryItem(id, name, quantity) {
    const body = { name };
    if (quantity) body.quantity = quantity;
    const data = await apiFetch(`/grocery-list/${id}`, {
        method: "PUT",
        body: JSON.stringify(body),
    });
    return data.item;
}

async function deleteGroceryItem(id) {
    await apiFetch(`/grocery-list/${id}`, { method: "DELETE" });
}

// ── Render helpers ───────────────────────────────────────────────

function renderGroceryItem(item, editingId) {
    if (editingId === item.id) {
        return `
            <li class="grocery-item editing" data-id="${item.id}">
                <form class="grocery-edit-form">
                    <input type="text" class="grocery-edit-name" value="${item.name}" required>
                    <input type="text" class="grocery-edit-qty" value="${item.quantity || ""}" placeholder="Qty">
                    <button type="submit" class="grocery-btn save" title="Save">Save</button>
                    <button type="button" class="grocery-btn cancel" title="Cancel">Cancel</button>
                </form>
            </li>
        `;
    }
    const qty = item.quantity ? `<span class="grocery-qty">${item.quantity}</span>` : "";
    return `
        <li class="grocery-item" data-id="${item.id}">
            <span class="grocery-name">${item.name}</span>
            ${qty}
            <div class="grocery-actions">
                <button class="grocery-btn edit" title="Edit">Edit</button>
                <button class="grocery-btn delete" title="Delete">Delete</button>
            </div>
        </li>
    `;
}

function renderOptimizeResult(result) {
    const savingsHtml = result.total_savings > 0
        ? `<span class="savings-badge">Save up to ${result.total_savings.toFixed(2)} zł</span>`
        : "";

    const itemsHtml = result.items.map(({ grocery_item, best_deal, alternatives }) => {
        const qty = grocery_item.quantity
            ? `<span class="optimize-item-qty">${grocery_item.quantity}</span>` : "";

        let dealHtml;
        if (best_deal) {
            const altCount = alternatives.length;
            const altHtml = altCount > 0
                ? `<button class="alt-toggle-btn" data-count="${altCount}">Show ${altCount} more deal${altCount > 1 ? "s" : ""}</button>
                   <div class="alt-deals hidden">
                       <div class="deals-grid">${alternatives.map(renderCard).join("")}</div>
                   </div>`
                : "";
            dealHtml = `<div class="deals-grid">${renderCard(best_deal)}</div>${altHtml}`;
        } else {
            dealHtml = `<p class="no-deals-inline">No deals found</p>`;
        }

        return `
            <div class="optimize-item">
                <div class="optimize-item-header">
                    <span class="optimize-item-name">${grocery_item.name}</span>
                    ${qty}
                </div>
                ${dealHtml}
            </div>`;
    }).join("");

    return `
        <div class="optimize-result">
            <div class="optimize-summary">
                <h3 class="mylist-deals-heading">Optimized Shopping</h3>
                ${savingsHtml}
            </div>
            ${itemsHtml}
        </div>`;
}

function renderGroceryView(items, editingId, myListDeals, optimizeResult) {
    const listHtml = items.length
        ? `<ul class="grocery-list">${items.map(i => renderGroceryItem(i, editingId)).join("")}</ul>`
        : `<p class="empty">Your grocery list is empty. Add items above.</p>`;

    const showingDeals = myListDeals !== null;
    const showingOptimize = optimizeResult !== null;
    const dealsBtnLabel = showingDeals ? "Hide matching deals" : "Show matching deals";
    const optimizeBtnLabel = showingOptimize ? "Hide optimized list" : "Optimize Shopping";

    const buttonsHtml = items.length ? `
        <div class="grocery-action-bar">
            <button id="mylist-deals-btn" class="toolbar-btn${showingDeals ? " active" : ""}">${dealsBtnLabel}</button>
            <button id="optimize-btn" class="toolbar-btn optimize-btn${showingOptimize ? " active" : ""}">${optimizeBtnLabel}</button>
        </div>` : "";

    let dealsHtml = "";
    if (showingDeals) {
        dealsHtml = myListDeals.length
            ? `<div class="mylist-deals">
                   <h3 class="mylist-deals-heading">Deals matching your list (${myListDeals.length})</h3>
                   <div class="deals-grid">${myListDeals.map(renderCard).join("")}</div>
               </div>`
            : `<div class="mylist-deals"><p class="empty">No current deals match your grocery list.</p></div>`;
    }

    const optimizeHtml = showingOptimize ? renderOptimizeResult(optimizeResult) : "";

    return `
        <div class="grocery-container">
            <form class="grocery-add-form" id="grocery-add-form">
                <input type="text" id="grocery-name" placeholder="Item name" required>
                <input type="text" id="grocery-qty" placeholder="Qty (optional)">
                <button type="submit">Add</button>
            </form>
            ${listHtml}
            ${buttonsHtml}
            ${dealsHtml}
            ${optimizeHtml}
        </div>
    `;
}

// ── Wiring ───────────────────────────────────────────────────────

function wireGroceryView(items, editingId, onRefresh) {
    // Add form
    const addForm = document.getElementById("grocery-add-form");
    if (addForm) {
        addForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const nameInput = document.getElementById("grocery-name");
            const qtyInput = document.getElementById("grocery-qty");
            const name = nameInput.value.trim();
            if (!name) return;
            try {
                await addGroceryItem(name, qtyInput.value.trim());
                onRefresh();
            } catch (err) {
                alert(`Failed to add item: ${err.message}`);
            }
        });
    }

    // Edit / Delete / Save / Cancel buttons
    document.querySelectorAll(".grocery-item").forEach(li => {
        const id = parseInt(li.dataset.id, 10);

        li.querySelector(".grocery-btn.edit")?.addEventListener("click", () => {
            onRefresh(id);
        });

        li.querySelector(".grocery-btn.delete")?.addEventListener("click", async () => {
            try {
                await deleteGroceryItem(id);
                onRefresh();
            } catch (err) {
                alert(`Failed to delete: ${err.message}`);
            }
        });

        li.querySelector(".grocery-btn.cancel")?.addEventListener("click", () => {
            onRefresh();
        });

        li.querySelector(".grocery-edit-form")?.addEventListener("submit", async (e) => {
            e.preventDefault();
            const name = li.querySelector(".grocery-edit-name").value.trim();
            const qty = li.querySelector(".grocery-edit-qty").value.trim();
            if (!name) return;
            try {
                await updateGroceryItem(id, name, qty);
                onRefresh();
            } catch (err) {
                alert(`Failed to update: ${err.message}`);
            }
        });
    });
}
