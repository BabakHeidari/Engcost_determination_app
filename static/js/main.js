function updateTime(){const now=new Date();const el=document.getElementById('currentTime');if(el){el.innerText=now.toLocaleTimeString();}}setInterval(updateTime,1000);updateTime();

document.addEventListener("DOMContentLoaded", () => {

    const table = document.getElementById("component_table");
    const addRowBtn = document.getElementById("add_row");
    const grandTotalEl = document.getElementById("grand_total");

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
            <td><input type="text" class="form-control" placeholder="Component name"></td>
            <td><input type="number" class="form-control quantity" min="0"></td>
            <td><input type="number" class="form-control unit_cost" step="0.01" min="0"></td>
            <td class="total_cost text-end">0.00</td>
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
