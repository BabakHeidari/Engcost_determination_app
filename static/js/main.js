(function () {
    const appLocale = document.documentElement.lang === 'fa' ? 'fa-IR' : (document.documentElement.lang || 'fa-IR');

    window.AppLocale = Object.freeze({
        locale: appLocale,
        direction: document.documentElement.dir || 'rtl',
        formatTime(date) {
            return new Intl.DateTimeFormat(this.locale, {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                numberingSystem: 'latn'
            }).format(date);
        },
        formatNumber(value, options = {}) {
            return new Intl.NumberFormat(this.locale, {
                numberingSystem: 'latn',
                ...options
            }).format(value);
        }
    });

    function updateTime() {
        const now = new Date();
        const el = document.getElementById('currentTime');
        if (el) {
            el.innerText = window.AppLocale.formatTime(now);
        }
    }

    setInterval(updateTime, 1000);
    updateTime();
})();

document.addEventListener("DOMContentLoaded", () => {
    const table = document.getElementById("component_table");
    const addRowBtn = document.getElementById("add_row");
    const grandTotalEl = document.getElementById("grand_total");

    if (!table || !addRowBtn || !grandTotalEl) {
        return;
    }

    function recalcTotals() {
        let grandTotal = 0;
        table.querySelectorAll("tbody tr").forEach(row => {
            const qty = parseFloat(row.querySelector(".quantity").value) || 0;
            const cost = parseFloat(row.querySelector(".unit_cost").value) || 0;
            const total = qty * cost;
            row.querySelector(".total_cost").textContent = total.toFixed(2);
            grandTotal += total;
        });
        grandTotalEl.textContent = grandTotal.toFixed(2);
    }

    table.addEventListener("input", e => {
        if (e.target.classList.contains("quantity") || e.target.classList.contains("unit_cost")) {
            recalcTotals();
        }
    });

    addRowBtn.addEventListener("click", () => {
        const newRow = document.createElement("tr");
        newRow.innerHTML = `
            <td><input type="text" class="form-control" placeholder="نام جزء"></td>
            <td><input type="number" class="form-control quantity" min="0" dir="ltr"></td>
            <td><input type="number" class="form-control unit_cost" step="0.01" min="0" dir="ltr"></td>
            <td class="total_cost text-end numeric" dir="ltr">0.00</td>
            <td><button class="btn btn-sm btn-outline-danger remove-row">×</button></td>
        `;
        table.querySelector("tbody").appendChild(newRow);
    });

    table.addEventListener("click", e => {
        if (e.target.classList.contains("remove-row")) {
            e.target.closest("tr").remove();
            recalcTotals();
        }
    });
});
