/**
 * Dashboard frontend logic.
 *
 * Consumes only the public JSON REST API. All values rendered into the
 * DOM go through textContent or an explicit escape helper, so API data
 * can never be interpreted as markup (XSS-safe by construction).
 */

const API_BASE = "/api/v1";

const SEGMENT_COLORS = {
  new_user: "#118dff",
  repeat_buyer: "#007c7c",
  vip: "#6b007b",
  dormant: "#e66c37",
  price_sensitive: "#12239e",
};

const OFFER_LABELS = {
  discount_percent: "Процентная скидка",
  discount_fixed: "Фиксированная скидка",
  free_shipping: "Бесплатная доставка",
  bonus_points: "Бонусные баллы",
  gift: "Подарок",
  early_access: "Ранний доступ",
  personal_manager: "Персональный менеджер",
  concierge: "Консьерж-сервис",
  bundle: "Комплект",
};

const CHANNEL_LABELS = { push: "Push", email: "Email", sms: "SMS", telegram: "Telegram" };

const TIMING_LABELS = {
  immediate: "Немедленно",
  same_day_evening: "Вечером того же дня",
  next_morning: "Утром следующего дня",
  weekend: "В выходные",
};

const VALUE_SUFFIX = { discount_percent: "%", discount_fixed: " ₽", bonus_points: " баллов" };

const state = {
  customers: [],
  selectedCustomerId: null,
  sortKey: "id",
  sortAsc: true,
  search: "",
  segment: "",
  lastCampaignId: null,
};

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function formatNumber(value, digits = 0) {
  return Number(value).toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function formatPercent(ratio) {
  return `${(Number(ratio) * 100).toFixed(1)}%`;
}

function formatOfferValue(offerType, value) {
  if (!value) return "—";
  return `${formatNumber(value)}${VALUE_SUFFIX[offerType] || ""}`;
}

function formatDateTime(isoString) {
  const date = new Date(isoString);
  return Number.isNaN(date.getTime()) ? String(isoString) : date.toLocaleString("ru-RU");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Ошибка запроса (${response.status})`);
  }
  return response.json();
}

function renderKpis(summary) {
  const cards = [
    { label: "Всего клиентов", value: formatNumber(summary.total_customers), cls: "" },
    { label: "Сгенерировано офферов", value: formatNumber(summary.total_offers_generated), cls: "accent" },
    { label: "Применено офферов", value: formatNumber(summary.total_offers_applied), cls: "teal" },
    { label: "Общая конверсия", value: formatPercent(summary.overall_conversion_rate), cls: "orange" },
  ];
  document.getElementById("kpi-grid").innerHTML = cards
    .map((c) => `<div class="kpi-card ${c.cls}"><div class="label">${escapeHtml(c.label)}</div><div class="value">${escapeHtml(c.value)}</div></div>`)
    .join("");
}

function renderSegmentBars(distribution) {
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  const maxCount = entries.length ? Math.max(...entries.map((e) => e[1])) : 0;
  const container = document.getElementById("segment-bars");

  if (!entries.length) {
    container.innerHTML = '<p class="empty">Нет данных по сегментам.</p>';
    return;
  }

  container.innerHTML = entries
    .map(([segment, count]) => {
      const width = maxCount ? (count / maxCount) * 100 : 0;
      const color = SEGMENT_COLORS[segment] || "#118dff";
      return `<div class="segment-row">
        <span>${escapeHtml(segment)}</span>
        <span class="bar-track"><span class="bar-fill" style="width:${width.toFixed(1)}%;background:${color}"></span></span>
        <span class="bar-count">${escapeHtml(formatNumber(count))}</span>
      </div>`;
    })
    .join("");
}

function visibleCustomers() {
  const search = state.search.trim().toLowerCase();
  const filtered = state.customers.filter((c) => {
    const matchesSegment = !state.segment || c.segment === state.segment;
    const matchesSearch = !search || String(c.id).includes(search) || c.external_ref.toLowerCase().includes(search);
    return matchesSegment && matchesSearch;
  });

  const key = state.sortKey;
  const direction = state.sortAsc ? 1 : -1;
  return filtered.sort((a, b) => (a[key] > b[key] ? direction : a[key] < b[key] ? -direction : 0));
}

function renderCustomers() {
  const rows = visibleCustomers();
  const tbody = document.querySelector("#customers-table tbody");

  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty">Клиенты не найдены. Измените фильтры.</td></tr>';
  } else {
    tbody.innerHTML = rows
      .map((c) => `<tr data-customer-id="${c.id}" class="${c.id === state.selectedCustomerId ? "selected" : ""}">
        <td class="num">${c.id}</td>
        <td>${escapeHtml(c.external_ref)}</td>
        <td class="num">${formatNumber(c.total_orders)}</td>
        <td class="num">${formatNumber(c.lifetime_value)}</td>
        <td class="num">${formatNumber(c.avg_order_value)}</td>
        <td class="num">${c.price_sensitivity.toFixed(2)}</td>
        <td><span class="tag">${escapeHtml(CHANNEL_LABELS[c.preferred_channel] || c.preferred_channel)}</span></td>
        <td><span class="pill ${escapeHtml(c.segment)}">${escapeHtml(c.segment)}</span></td>
        <td><button type="button" class="secondary offers-btn" data-customer-id="${c.id}">Офферы</button></td>
      </tr>`)
      .join("");
  }

  document.getElementById("customers-status").textContent =
    `Показано ${rows.length} из ${state.customers.length} клиентов.`;

  tbody.querySelectorAll(".offers-btn").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.stopPropagation();
      selectCustomer(Number(btn.dataset.customerId));
    });
  });

  tbody.querySelectorAll("tr[data-customer-id]").forEach((row) => {
    row.addEventListener("click", () => selectCustomer(Number(row.dataset.customerId)));
  });
}

function renderOffers(data) {
  const grid = document.getElementById("offers-grid");
  const empty = document.getElementById("offers-empty");

  document.getElementById("selected-customer-label").textContent =
    `— клиент #${data.customer_id}, сегмент ${data.segment}, эластичность ${data.price_sensitivity.toFixed(2)}`;

  if (!data.offers.length) {
    grid.innerHTML = "";
    empty.textContent = "Для этого сегмента офферы не настроены.";
    empty.style.display = "";
    return;
  }

  empty.style.display = "none";
  grid.innerHTML = data.offers
    .map((offer, index) => `<div class="offer-card">
      <div class="rank">Приоритет ${index + 1} · ${escapeHtml(offer.offer_type)}</div>
      <div class="title">${escapeHtml(offer.title)}</div>
      <div class="meter-track"><div class="meter-fill" style="width:${(offer.expected_conversion * 100).toFixed(0)}%"></div></div>
      <div class="score">Ожидаемая конверсия: ${(offer.expected_conversion * 100).toFixed(0)}%</div>
      <div class="reason">${escapeHtml(offer.reason)}</div>
      <div class="uid">${escapeHtml(offer.offer_uid)}</div>
    </div>`)
    .join("");
}

function renderOptimization(data) {
  const tbody = document.querySelector("#agent-table tbody");
  const empty = document.getElementById("agent-empty");

  document.getElementById("agent-engine-label").textContent =
    `— клиент #${data.customer_id}, движок ${data.engine}`;
  document.getElementById("agent-strategy").textContent = data.overall_strategy;

  if (!data.recommendations.length) {
    tbody.innerHTML = "";
    empty.textContent = "Агент не нашёл применимых рекомендаций.";
    empty.style.display = "";
    return;
  }

  empty.style.display = "none";
  tbody.innerHTML = data.recommendations
    .map((r) => `<tr>
      <td>${escapeHtml(OFFER_LABELS[r.offer_type] || r.offer_type)}</td>
      <td class="num">${escapeHtml(formatOfferValue(r.offer_type, r.value))}</td>
      <td><span class="tag">${escapeHtml(CHANNEL_LABELS[r.channel] || r.channel)}</span></td>
      <td>${escapeHtml(TIMING_LABELS[r.timing] || r.timing)}</td>
      <td class="num">${(r.expected_conversion * 100).toFixed(0)}%</td>
      <td class="reason-cell">${escapeHtml(r.reasoning)}</td>
    </tr>`)
    .join("");
}

function renderCampaign(schedule, performance) {
  const container = document.getElementById("campaign-result");
  document.getElementById("campaign-empty").style.display = "none";

  const breakdown = Object.entries(performance.segment_breakdown || {});
  const breakdownHtml = breakdown.length
    ? breakdown.map(([segment, count]) =>
        `<span class="tag">${escapeHtml(segment)}: ${escapeHtml(formatNumber(count))}</span>`).join(" ")
    : '<span class="tag">нет данных за период</span>';

  container.innerHTML = `
    <div class="campaign-summary">
      <div class="item"><div class="label">ID кампании</div><div class="value mono">${escapeHtml(schedule.campaign_id)}</div></div>
      <div class="item"><div class="label">Аудитория</div><div class="value">${escapeHtml(formatNumber(schedule.target_audience_size))}</div></div>
      <div class="item"><div class="label">Канал</div><div class="value">${escapeHtml(CHANNEL_LABELS[schedule.channel] || schedule.channel)}</div></div>
      <div class="item"><div class="label">Запуск</div><div class="value mono">${escapeHtml(formatDateTime(schedule.scheduled_for))}</div></div>
      <div class="item"><div class="label">Офферов за период</div><div class="value">${escapeHtml(formatNumber(performance.offers_generated))}</div></div>
      <div class="item"><div class="label">Конверсия</div><div class="value">${escapeHtml(formatPercent(performance.conversion_rate))}</div></div>
    </div>
    <p class="note">Распределение офферов по сегментам за период: ${breakdownHtml}</p>`;
}

function renderAbTest(result) {
  const groupLabels = { personalized: "Персональные офферы", mass_promotion: "Массовое промо" };
  const tbody = document.querySelector("#ab-test-table tbody");

  tbody.innerHTML = [result.personalized, result.mass_promotion]
    .map((g) => `<tr>
      <td>${escapeHtml(groupLabels[g.group] || g.group)}</td>
      <td class="num">${formatNumber(g.customers)}</td>
      <td class="num">${formatNumber(g.offers_generated)}</td>
      <td class="num">${formatNumber(g.offers_converted)}</td>
      <td class="num">${formatPercent(g.conversion_rate)}</td>
      <td class="num">${formatNumber(g.average_order_value)}</td>
      <td class="num">${g.estimated_margin_pct}%</td>
    </tr>`)
    .join("");

  const uplift = result.conversion_uplift_pct;
  const sign = uplift > 0 ? "+" : "";
  document.getElementById("ab-uplift").innerHTML =
    `Прирост конверсии: <span class="uplift ${uplift >= 0 ? "positive" : "negative"}">${sign}${uplift.toFixed(1)}%</span> · ` +
    `выигрыш по марже: <span class="uplift positive">+${result.margin_uplift_pct.toFixed(1)} п.п.</span>`;

  document.getElementById("ab-test-note").textContent = result.note;
}

async function selectCustomer(customerId) {
  state.selectedCustomerId = customerId;
  renderCustomers();

  // Cart total always follows the selected customer's average order value,
  // so switching customers never leaves a stale figure from the previous one.
  const customer = state.customers.find((c) => c.id === customerId);
  if (customer) {
    document.getElementById("cart-total-input").value = Math.round(customer.avg_order_value);
  }

  document.getElementById("regenerate-btn").disabled = false;
  document.getElementById("optimize-btn").disabled = false;
  await Promise.all([loadOffers(), loadOptimization()]);
}

function currentCartTotal() {
  return Math.max(0, Number(document.getElementById("cart-total-input").value) || 0);
}

async function loadOffers() {
  if (state.selectedCustomerId === null) return;

  const isAbandoned = document.getElementById("abandoned-cart-input").checked;
  const url = `${API_BASE}/offers/generate/${state.selectedCustomerId}`
    + `?cart_total=${currentCartTotal()}&is_abandoned_cart=${isAbandoned}`;

  try {
    renderOffers(await fetchJson(url));
  } catch (error) {
    const empty = document.getElementById("offers-empty");
    document.getElementById("offers-grid").innerHTML = "";
    empty.textContent = `Не удалось загрузить офферы: ${error.message}`;
    empty.style.display = "";
  }
}

async function loadOptimization() {
  if (state.selectedCustomerId === null) return;

  const url = `${API_BASE}/offers/optimization/recommendations`
    + `?customer_id=${state.selectedCustomerId}&cart_total=${currentCartTotal()}`;

  try {
    renderOptimization(await fetchJson(url));
  } catch (error) {
    const empty = document.getElementById("agent-empty");
    document.querySelector("#agent-table tbody").innerHTML = "";
    document.getElementById("agent-strategy").textContent = "";
    empty.textContent = `Не удалось получить рекомендации: ${error.message}`;
    empty.style.display = "";
  }
}

async function scheduleCampaign() {
  const button = document.getElementById("schedule-btn");
  button.disabled = true;

  try {
    const schedule = await fetchJson(`${API_BASE}/offers/campaign/schedule`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        segment: document.getElementById("campaign-segment").value,
        offer_type: document.getElementById("campaign-offer-type").value,
        channel: document.getElementById("campaign-channel").value,
      }),
    });

    const performance = await fetchJson(
      `${API_BASE}/offers/campaign/performance?campaign_id=${encodeURIComponent(schedule.campaign_id)}`
    );

    state.lastCampaignId = schedule.campaign_id;
    renderCampaign(schedule, performance);
  } catch (error) {
    document.getElementById("campaign-result").innerHTML = "";
    const empty = document.getElementById("campaign-empty");
    empty.textContent = `Не удалось запланировать кампанию: ${error.message}`;
    empty.style.display = "";
  } finally {
    button.disabled = false;
  }
}

function attachControls() {
  document.getElementById("search-input").addEventListener("input", (event) => {
    state.search = event.target.value;
    renderCustomers();
  });

  document.getElementById("segment-filter").addEventListener("change", (event) => {
    state.segment = event.target.value;
    renderCustomers();
  });

  document.querySelectorAll("th.sortable").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.sortKey;
      state.sortAsc = state.sortKey === key ? !state.sortAsc : true;
      state.sortKey = key;
      renderCustomers();
    });
  });

  // Changing the cart amount or the abandoned-cart flag immediately
  // re-scores the offers, so the panel always matches the inputs.
  document.getElementById("cart-total-input").addEventListener("change", () => {
    loadOffers();
    loadOptimization();
  });
  document.getElementById("abandoned-cart-input").addEventListener("change", loadOffers);

  document.getElementById("regenerate-btn").addEventListener("click", loadOffers);
  document.getElementById("optimize-btn").addEventListener("click", loadOptimization);
  document.getElementById("schedule-btn").addEventListener("click", scheduleCampaign);
  document.getElementById("refresh-btn").addEventListener("click", bootstrap);
}

async function bootstrap() {
  try {
    const [summary, customers, abTest] = await Promise.all([
      fetchJson(`${API_BASE}/analytics/dashboard`),
      fetchJson(`${API_BASE}/customers?limit=500`),
      fetchJson(`${API_BASE}/analytics/ab-test`),
    ]);

    state.customers = customers;
    renderKpis(summary);
    renderSegmentBars(summary.segment_distribution);
    renderCustomers();
    renderAbTest(abTest);
  } catch (error) {
    document.getElementById("kpi-grid").innerHTML =
      `<div class="kpi-card"><div class="label">Ошибка</div><div class="value" style="font-size:15px">${escapeHtml(error.message)}</div></div>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  attachControls();
  bootstrap();
});
