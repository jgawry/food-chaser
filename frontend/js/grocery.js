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

function renderGroceryView(items, editingId, myListDeals) {
    const listHtml = items.length
        ? `<ul class="grocery-list">${items.map(i => renderGroceryItem(i, editingId)).join("")}</ul>`
        : `<p class="empty">Your grocery list is empty. Add items above.</p>`;

    const showingDeals = myListDeals !== null;
    const btnLabel = showingDeals ? "Hide matching deals" : "Show matching deals";
    const dealsBtn = items.length
        ? `<button id="mylist-deals-btn" class="toolbar-btn${showingDeals ? " active" : ""}">${btnLabel}</button>`
        : "";

    let dealsHtml = "";
    if (showingDeals) {
        if (myListDeals.length) {
            dealsHtml = `
                <div class="mylist-deals">
                    <h3 class="mylist-deals-heading">Deals matching your list (${myListDeals.length})</h3>
                    <div class="deals-grid">${myListDeals.map(renderCard).join("")}</div>
                </div>`;
        } else {
            dealsHtml = `
                <div class="mylist-deals">
                    <p class="empty">No current deals match your grocery list.</p>
                </div>`;
        }
    }

    return `
        <div class="grocery-container">
            <form class="grocery-add-form" id="grocery-add-form">
                <input type="text" id="grocery-name" placeholder="Item name" required>
                <input type="text" id="grocery-qty" placeholder="Qty (optional)">
                <button type="submit">Add</button>
            </form>
            ${listHtml}
            ${dealsBtn}
            ${dealsHtml}
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
