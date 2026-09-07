const API_BASE = "/api/v1";

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed with status ${response.status}`);
  }
  return response.json();
}

function renderKpis(summary) {
  const grid = document.getElementById("kpi-grid");
  const cards = [
    { label: "Всего клиентов", value: summary.total_customers },
    { label: "Сгенерировано офферов", value: summary.total_offers_generated },
    { label: "Применено офферов", value: summary.total_offers_applied },
    { label: "Общая конверсия", value: `${(summary.overall_conversion_rate * 100).toFixed(1)}%` },
  ];
  grid.innerHTML = cards.map((c) => `<div class="kpi-card"><div class="value">${c.value}</div><div class="label">${c.label}</div></div>`).join("");
}

function renderCustomers(customers) {
  const tbody = document.querySelector("#customers-table tbody");
  tbody.innerHTML = customers.map((c) => `
    <tr>
      <td>${c.id}</td><td>${c.external_ref}</td><td>${c.total_orders}</td><td>${c.lifetime_value.toFixed(0)}</td>
      <td>${c.price_sensitivity.toFixed(2)}</td><td>${c.segment}</td>
      <td><button data-customer-id="${c.id}" class="generate-btn">Офферы</button></td>
    </tr>`).join("");
  document.querySelectorAll(".generate-btn").forEach((btn) => btn.addEventListener("click", () => loadOffers(btn.dataset.customerId)));
}

function renderOffers(customerId, data) {
  const panel = document.getElementById("offers-panel");
  const grid = document.getElementById("offers-grid");
  document.getElementById("selected-customer-label").textContent = `#${customerId} (${data.segment})`;
  grid.innerHTML = data.offers.map((o) => `
    <div class="offer-card">
      <div class="title">${o.title}</div>
      <div class="score">Оценка конверсии: ${(o.expected_conversion * 100).toFixed(0)}%</div>
      <div class="reason">${o.reason}</div>
    </div>`).join("");
  panel.hidden = false;
}

function renderAbTest(result) {
  const tbody = document.querySelector("#ab-test-table tbody");
  const groups = [result.personalized, result.mass_promotion];
  tbody.innerHTML = groups.map((g) => `
    <tr>
      <td>${g.group}</td><td>${g.customers}</td><td>${g.offers_generated}</td><td>${g.offers_converted}</td>
      <td>${(g.conversion_rate * 100).toFixed(1)}%</td><td>${g.average_order_value.toFixed(0)}</td><td>${g.estimated_margin_pct}%</td>
    </tr>`).join("");
  document.getElementById("ab-test-note").textContent = result.note;
}

async function loadOffers(customerId) {
  try {
    const data = await fetchJson(`${API_BASE}/offers/generate/${customerId}`);
    renderOffers(customerId, data);
  } catch (error) {
    alert(`Не удалось загрузить офферы: ${error.message}`);
  }
}

async function bootstrap() {
  try {
    const [summary, customers, abTest] = await Promise.all([
      fetchJson(`${API_BASE}/analytics/dashboard`),
      fetchJson(`${API_BASE}/customers?limit=50`),
      fetchJson(`${API_BASE}/analytics/ab-test`),
    ]);
    renderKpis(summary);
    renderCustomers(customers);
    renderAbTest(abTest);
  } catch (error) {
    console.error(error);
    document.getElementById("kpi-grid").innerHTML = `<p>Ошибка загрузки данных: ${error.message}</p>`;
  }
}

document.addEventListener("DOMContentLoaded", bootstrap);
