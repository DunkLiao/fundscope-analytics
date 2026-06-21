const viewButtons = document.querySelectorAll("[data-view]");
const viewPanels = document.querySelectorAll("[data-view-panel]");
const navButtons = document.querySelectorAll(".nav-button, .menu-list button");
const actionCards = document.querySelectorAll(".action-card");
const navMenus = document.querySelectorAll(".nav-menu");

const form = document.querySelector("#query-form");
const input = document.querySelector("#fund-code");
const message = document.querySelector("#message");
const summary = document.querySelector("#fund-summary");
const navBody = document.querySelector("#nav-body");

const performanceForm = document.querySelector("#performance-form");
const performanceInput = document.querySelector("#performance-fund-code");
const performanceMessage = document.querySelector("#performance-message");
const performanceSummary = document.querySelector("#performance-fund-summary");
const performanceSummaryBody = document.querySelector("#performance-summary-body");
const performanceReturnsHead = document.querySelector("#performance-returns-head");
const performanceReturnsBody = document.querySelector("#performance-returns-body");
const performanceSource = document.querySelector("#performance-source");

const startUpdateButton = document.querySelector("#start-update");
const updateState = document.querySelector("#update-state");
const updateStarted = document.querySelector("#update-started");
const updateFinished = document.querySelector("#update-finished");
const updateMessage = document.querySelector("#update-message");
const investmentViews = document.querySelectorAll(".investment-view");

let updatePollTimer = null;

const summaryFields = {
  code: document.querySelector("#summary-code"),
  name: document.querySelector("#summary-name"),
  market: document.querySelector("#summary-market"),
  trans: document.querySelector("#summary-trans"),
};

const performanceSummaryFields = {
  code: document.querySelector("#performance-summary-code"),
  name: document.querySelector("#performance-summary-name"),
  market: document.querySelector("#performance-summary-market"),
  trans: document.querySelector("#performance-summary-trans"),
};

const updateStateLabels = {
  idle: "待命",
  running: "讀取中",
  succeeded: "已完成",
  failed: "失敗",
};

const investmentLabels = {
  holdings: {
    empty: "尚未建立庫存基金設定",
    saved: "庫存基金設定已儲存",
    deleted: "庫存基金設定已刪除",
  },
  recurring: {
    empty: "尚未建立定期定額申購基金設定",
    saved: "定期定額申購基金設定已儲存",
    deleted: "定期定額申購基金設定已刪除",
  },
  "lump-sum": {
    empty: "尚未建立單筆申購設定",
    saved: "單筆申購設定已儲存",
    deleted: "單筆申購設定已刪除",
  },
};

const investmentStates = {};

investmentViews.forEach((view) => {
  const type = view.dataset.settingType;
  investmentStates[type] = {
    type,
    view,
    form: view.querySelector(".investment-form"),
    idInput: view.querySelector('input[name="record-id"]'),
    codeInput: view.querySelector(".investment-code"),
    amountInput: view.querySelector(".investment-amount"),
    dateInput: view.querySelector(".investment-date"),
    unitsInput: view.querySelector(".investment-units"),
    startDateInput: view.querySelector(".investment-start-date"),
    endDateInput: view.querySelector(".investment-end-date"),
    daysInput: view.querySelector(".investment-days"),
    fundName: view.querySelector(".investment-fund-name"),
    message: view.querySelector(".investment-message"),
    cancelButton: view.querySelector('[data-action="cancel-edit"]'),
    body: view.querySelector(".investment-body"),
    items: [],
    lookupSeq: 0,
  };
});

function switchView(viewName) {
  viewPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.viewPanel === viewName);
  });

  navButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });

  if (viewName === "fund-list") {
    refreshUpdateStatus();
  }

  const investmentPanel = document.querySelector(`[data-view-panel="${viewName}"].investment-view`);
  if (investmentPanel) {
    refreshInvestmentSettings(investmentPanel.dataset.settingType);
  }
}

function setMessage(text, type = "") {
  message.textContent = text;
  message.dataset.type = type;
}

function setPerformanceMessage(text, type = "") {
  performanceMessage.textContent = text;
  performanceMessage.dataset.type = type;
}

function setUpdateMessage(text, type = "") {
  updateMessage.textContent = text;
  updateMessage.dataset.type = type;
}

function formatNumber(value, digits = 4) {
  if (value === null || value === undefined) return "-";
  return Number(value).toFixed(digits);
}

function formatTime(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("zh-TW", { hour12: false });
}

function formatCurrency(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "-";
  return amount.toLocaleString("zh-TW");
}

function formatPercent(value) {
  if (value === null || value === undefined) return "N/A";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "N/A";
  return parsed.toFixed(2);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderSummary(fund) {
  summaryFields.code.textContent = fund.fund_code || "-";
  summaryFields.name.textContent = fund.fund_name_main || fund.fund_name || "-";
  summaryFields.market.textContent = fund.market || "-";
  summaryFields.trans.textContent = fund.fund_id || "-";
  summary.hidden = false;
}

function renderPerformanceFundSummary(fund) {
  performanceSummaryFields.code.textContent = fund.fund_code || "-";
  performanceSummaryFields.name.textContent = fund.fund_name_main || fund.fund_name || "-";
  performanceSummaryFields.market.textContent = fund.market || "-";
  performanceSummaryFields.trans.textContent = fund.fund_id || "-";
  performanceSummary.hidden = false;
}

function renderRows(rows) {
  if (!rows.length) {
    navBody.innerHTML = '<tr><td colspan="4" class="empty">查無逐日淨值資料</td></tr>';
    return;
  }

  navBody.innerHTML = rows
    .map((row) => {
      const changeClass = row.change > 0 ? "up" : row.change < 0 ? "down" : "";
      return `
        <tr>
          <td>${row.date}</td>
          <td>${formatNumber(row.nav)}</td>
          <td class="${changeClass}">${formatNumber(row.change)}</td>
          <td class="${changeClass}">${formatNumber(row.change_percent, 2)}</td>
        </tr>
      `;
    })
    .join("");
}

function renderPerformance(payload) {
  const performance = payload.performance;
  const summaryRow = performance.summary;
  const returns = performance.cumulative_returns || [];
  const sourceUrl = performance.source_url;

  performanceSummaryBody.innerHTML = `
    <tr>
      <td>${escapeHtml(summaryRow.fund_name || "-")}</td>
      <td>${formatNumber(summaryRow.nav)}</td>
      <td>${escapeHtml(summaryRow.nav_date || "-")}</td>
      <td class="up">${formatPercent(summaryRow.year_to_date_return_percent)}</td>
      <td>${formatPercent(summaryRow.annualized_standard_deviation_percent)}</td>
      <td>${formatNumber(summaryRow.sharpe, 2)}</td>
      <td>${formatNumber(summaryRow.beta, 2)}</td>
    </tr>
  `;

  if (!returns.length) {
    performanceReturnsHead.innerHTML = "<tr><th>基金名稱</th></tr>";
    performanceReturnsBody.innerHTML = '<tr><td class="empty">查無累積報酬率資料</td></tr>';
  } else {
    performanceReturnsHead.innerHTML = `
      <tr>
        <th>基金名稱</th>
        ${returns.map((item) => `<th>${escapeHtml(item.period)}</th>`).join("")}
      </tr>
    `;
    performanceReturnsBody.innerHTML = `
      <tr>
        <td>${escapeHtml(summaryRow.fund_name || "-")}</td>
        ${returns.map((item) => `<td>${formatPercent(item.return_percent)}</td>`).join("")}
      </tr>
    `;
  }

  if (sourceUrl) {
    performanceSource.innerHTML = `資料來源：<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">臺銀基金績效頁</a>`;
    performanceSource.hidden = false;
  } else {
    performanceSource.hidden = true;
  }
}

async function queryFund(code) {
  const response = await fetch(`/api/funds/${encodeURIComponent(code)}/nav`);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "查詢失敗");
  }
  return payload;
}

async function queryPerformance(code) {
  const response = await fetch(`/api/funds/${encodeURIComponent(code)}/performance`);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "查詢失敗");
  }
  return payload;
}

async function startFundListUpdate() {
  const response = await fetch("/api/fund-list/update", { method: "POST" });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "無法啟動基金清單更新");
  }
  return payload;
}

async function getFundListUpdateStatus() {
  const response = await fetch("/api/fund-list/update-status");
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "無法取得基金清單更新狀態");
  }
  return payload;
}

async function getFundProfile(code) {
  const response = await fetch(`/api/funds/${encodeURIComponent(code)}`);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "無法取得基金名稱");
  }
  return payload;
}

async function getInvestmentSettings(type) {
  const url = type === "recurring"
    ? "/api/investments/recurring/plans"
    : `/api/investments/${encodeURIComponent(type)}/transactions`;
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "無法取得投資資料");
  }
  return payload;
}

async function saveInvestmentSetting(type, id, data) {
  const url = type === "recurring"
    ? id
      ? `/api/investments/recurring/plans/${encodeURIComponent(id)}`
      : "/api/investments/recurring/plans"
    : id
      ? `/api/investments/${encodeURIComponent(type)}/transactions/${encodeURIComponent(id)}`
      : `/api/investments/${encodeURIComponent(type)}/transactions`;
  const response = await fetch(url, {
    method: id ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "無法儲存投資資料");
  }
  return payload;
}

async function deleteInvestmentSetting(type, id) {
  const url = type === "recurring"
    ? `/api/investments/recurring/plans/${encodeURIComponent(id)}`
    : `/api/investments/${encodeURIComponent(type)}/transactions/${encodeURIComponent(id)}`;
  const response = await fetch(url, {
    method: "DELETE",
  });
  if (!response.ok) {
    let message = "無法刪除投資設定";
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {
      // Keep the generic message when the server returns no JSON body.
    }
    throw new Error(message);
  }
}

async function generateRecurringTransactions(planId) {
  const response = await fetch(`/api/investments/recurring/plans/${encodeURIComponent(planId)}/generate-transactions`, {
    method: "POST",
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "無法產生定期定額交易");
  }
  return payload;
}

function renderUpdateStatus(payload) {
  const status = payload.status || "idle";
  updateState.textContent = updateStateLabels[status] || status;
  updateStarted.textContent = formatTime(payload.started_at);
  updateFinished.textContent = formatTime(payload.finished_at);

  const type = status === "failed" ? "error" : status === "succeeded" ? "success" : "";
  setUpdateMessage(payload.message || "尚未執行基金清單更新", type);
  startUpdateButton.disabled = status === "running";

  if (status === "running" && updatePollTimer === null) {
    updatePollTimer = window.setInterval(refreshUpdateStatus, 2000);
  }

  if (status !== "running" && updatePollTimer !== null) {
    window.clearInterval(updatePollTimer);
    updatePollTimer = null;
  }
}

function setInvestmentMessage(state, text, type = "") {
  state.message.textContent = text;
  state.message.dataset.type = type;
}

function resetInvestmentForm(state) {
  state.form.reset();
  state.idInput.value = "";
  state.fundName.textContent = "輸入基金代號後自動帶出";
  state.cancelButton.hidden = true;
}

function renderInvestmentRows(state) {
  if (!state.items.length) {
    const colspan = state.type === "recurring" ? 7 : 8;
    state.body.innerHTML = `<tr><td colspan="${colspan}" class="empty">${investmentLabels[state.type].empty}</td></tr>`;
    return;
  }

  if (state.type === "recurring") {
    state.body.innerHTML = state.items
      .map(
        (item) => `
          <tr>
            <td>${escapeHtml(item.fund_code)}</td>
            <td>${escapeHtml(item.fund_name || "-")}</td>
            <td>${formatCurrency(item.amount)}</td>
            <td>${escapeHtml(item.start_date || "-")}</td>
            <td>${escapeHtml(item.end_date || "-")}</td>
            <td>${escapeHtml((item.days || []).join(", "))}</td>
            <td>
              <div class="table-actions">
                <button class="table-action" type="button" data-action="edit" data-id="${item.id}">編輯</button>
                <button class="table-action danger" type="button" data-action="delete" data-id="${item.id}">刪除</button>
                <button class="table-action" type="button" data-action="generate" data-id="${item.id}">產生已到期交易</button>
              </div>
            </td>
          </tr>
        `
      )
      .join("");
    return;
  }

  state.body.innerHTML = state.items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.fund_code)}</td>
          <td>${escapeHtml(item.fund_name || "-")}</td>
          <td>${escapeHtml(item.trade_date || "-")}</td>
          <td>${escapeHtml(item.nav_date || "-")}</td>
          <td>${formatNumber(item.nav, 4)}</td>
          <td>${formatCurrency(item.amount)}</td>
          <td>${formatNumber(item.units, 4)}</td>
          <td>
            <div class="table-actions">
              <button class="table-action" type="button" data-action="edit" data-id="${item.id}">編輯</button>
              <button class="table-action danger" type="button" data-action="delete" data-id="${item.id}">刪除</button>
            </div>
          </td>
        </tr>
      `
    )
    .join("");
}

async function refreshInvestmentSettings(type) {
  const state = investmentStates[type];
  if (!state) return;
  setInvestmentMessage(state, "讀取中...", "loading");

  try {
    state.items = await getInvestmentSettings(type);
    renderInvestmentRows(state);
    setInvestmentMessage(state, `已載入 ${state.items.length} 筆設定`, "success");
  } catch (error) {
    state.body.innerHTML = '<tr><td colspan="4" class="empty">無法顯示投資設定</td></tr>';
    setInvestmentMessage(state, error.message, "error");
  }
}

async function lookupInvestmentFundName(state) {
  const code = state.codeInput.value.trim().toUpperCase();
  state.codeInput.value = code;
  state.lookupSeq += 1;
  const seq = state.lookupSeq;

  if (!code) {
    state.fundName.textContent = "輸入基金代號後自動帶出";
    return;
  }

  if (!/^[A-Z0-9]{4}$/.test(code)) {
    state.fundName.textContent = "基金代號必須是四碼英數字";
    return;
  }

  state.fundName.textContent = "查找中...";

  try {
    const fund = await getFundProfile(code);
    if (seq !== state.lookupSeq) return;
    state.fundName.textContent = fund.fund_name_main || fund.fund_name || "-";
  } catch (error) {
    if (seq !== state.lookupSeq) return;
    state.fundName.textContent = error.message;
  }
}

async function handleInvestmentSubmit(state, event) {
  event.preventDefault();
  const code = state.codeInput.value.trim().toUpperCase();
  const amountText = state.amountInput.value.trim();

  if (!/^[A-Z0-9]{4}$/.test(code)) {
    setInvestmentMessage(state, "基金代號必須是四碼英數字", "error");
    state.codeInput.focus();
    return;
  }

  if (!/^[1-9]\d*$/.test(amountText)) {
    setInvestmentMessage(state, "投資金額必須是大於 0 的整數", "error");
    state.amountInput.focus();
    return;
  }

  if (state.type === "recurring") {
    const startDate = state.startDateInput.value;
    const daysText = state.daysInput.value.trim();
    const days = daysText
      .split(",")
      .map((item) => Number(item.trim()))
      .filter((item) => Number.isInteger(item));
    if (!startDate) {
      setInvestmentMessage(state, "開始日必填", "error");
      state.startDateInput.focus();
      return;
    }
    if (!days.length || days.some((day) => day < 1 || day > 31)) {
      setInvestmentMessage(state, "每月扣款日必須介於 1 到 31，可用逗號分隔", "error");
      state.daysInput.focus();
      return;
    }

    setInvestmentMessage(state, "儲存中...", "loading");
    try {
      await saveInvestmentSetting(state.type, state.idInput.value, {
        fund_code: code,
        amount: Number(amountText),
        start_date: startDate,
        end_date: state.endDateInput.value || null,
        days,
      });
      resetInvestmentForm(state);
      await refreshInvestmentSettings(state.type);
      setInvestmentMessage(state, investmentLabels[state.type].saved, "success");
    } catch (error) {
      setInvestmentMessage(state, error.message, "error");
    }
    return;
  }

  if (!state.dateInput.value) {
    setInvestmentMessage(state, "交易/基準日期必填", "error");
    state.dateInput.focus();
    return;
  }

  let units = null;
  if (state.type === "holdings") {
    const unitsText = state.unitsInput.value.trim();
    if (!/^\d+(\.\d+)?$/.test(unitsText) || Number(unitsText) <= 0) {
      setInvestmentMessage(state, "現有單位數必須大於 0", "error");
      state.unitsInput.focus();
      return;
    }
    units = Number(unitsText);
  }

  setInvestmentMessage(state, "儲存中...", "loading");

  try {
    await saveInvestmentSetting(state.type, state.idInput.value, {
      fund_code: code,
      trade_date: state.dateInput.value,
      amount: Number(amountText),
      units,
    });
    resetInvestmentForm(state);
    await refreshInvestmentSettings(state.type);
    setInvestmentMessage(state, investmentLabels[state.type].saved, "success");
  } catch (error) {
    setInvestmentMessage(state, error.message, "error");
  }
}

function startInvestmentEdit(state, id) {
  const item = state.items.find((row) => String(row.id) === String(id));
  if (!item) return;
  state.idInput.value = item.id;
  state.codeInput.value = item.fund_code;
  if (state.dateInput) state.dateInput.value = item.trade_date || "";
  if (state.startDateInput) state.startDateInput.value = item.start_date || "";
  if (state.endDateInput) state.endDateInput.value = item.end_date || "";
  if (state.daysInput) state.daysInput.value = (item.days || []).join(",");
  state.amountInput.value = item.amount;
  if (state.unitsInput) state.unitsInput.value = item.units || "";
  state.fundName.textContent = item.fund_name || "-";
  state.cancelButton.hidden = false;
  setInvestmentMessage(state, "編輯中", "");
  state.codeInput.focus();
}

async function handleInvestmentTableAction(state, event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;

  const id = button.dataset.id;
  if (button.dataset.action === "edit") {
    startInvestmentEdit(state, id);
    return;
  }

  if (button.dataset.action === "generate") {
    setInvestmentMessage(state, "產生交易中...", "loading");
    try {
      const rows = await generateRecurringTransactions(id);
      setInvestmentMessage(state, `已產生 ${rows.length} 筆已到期交易`, "success");
    } catch (error) {
      setInvestmentMessage(state, error.message, "error");
    }
    return;
  }

  if (button.dataset.action !== "delete") return;
  if (!window.confirm("確定要刪除此筆投資設定？")) return;

  setInvestmentMessage(state, "刪除中...", "loading");
  try {
    await deleteInvestmentSetting(state.type, id);
    await refreshInvestmentSettings(state.type);
    setInvestmentMessage(state, investmentLabels[state.type].deleted, "success");
  } catch (error) {
    setInvestmentMessage(state, error.message, "error");
  }
}

async function refreshUpdateStatus() {
  try {
    const payload = await getFundListUpdateStatus();
    renderUpdateStatus(payload);
  } catch (error) {
    setUpdateMessage(error.message, "error");
  }
}

viewButtons.forEach((button) => {
  button.addEventListener("click", () => {
    switchView(button.dataset.view);
    if (button.closest(".menu-list")) {
      navMenus.forEach((menu) => {
        menu.open = false;
      });
    }
  });
});

actionCards.forEach((card) => {
  card.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      switchView(card.dataset.view);
    }
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const code = input.value.trim().toUpperCase();
  if (!/^[A-Z0-9]{4}$/.test(code)) {
    setMessage("基金代號必須是四碼英數字", "error");
    input.focus();
    return;
  }

  input.value = code;
  summary.hidden = true;
  navBody.innerHTML = '<tr><td colspan="4" class="empty">查詢中...</td></tr>';
  setMessage("查詢中...", "loading");

  try {
    const payload = await queryFund(code);
    renderSummary(payload.fund);
    renderRows(payload.nav);
    setMessage(`已載入 ${payload.nav.length} 筆逐日淨值`, "success");
  } catch (error) {
    navBody.innerHTML = '<tr><td colspan="4" class="empty">無法顯示資料</td></tr>';
    setMessage(error.message, "error");
  }
});

performanceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const code = performanceInput.value.trim().toUpperCase();
  if (!/^[A-Z0-9]{4}$/.test(code)) {
    setPerformanceMessage("基金代號必須是四碼英數字", "error");
    performanceInput.focus();
    return;
  }

  performanceInput.value = code;
  performanceSummary.hidden = true;
  performanceSource.hidden = true;
  performanceSummaryBody.innerHTML = '<tr><td colspan="7" class="empty">查詢中...</td></tr>';
  performanceReturnsHead.innerHTML = "<tr><th>基金名稱</th></tr>";
  performanceReturnsBody.innerHTML = '<tr><td class="empty">查詢中...</td></tr>';
  setPerformanceMessage("查詢中...", "loading");

  try {
    const payload = await queryPerformance(code);
    renderPerformanceFundSummary(payload.fund);
    renderPerformance(payload);
    setPerformanceMessage("績效資料已載入", "success");
  } catch (error) {
    performanceSummaryBody.innerHTML = '<tr><td colspan="7" class="empty">無法顯示資料</td></tr>';
    performanceReturnsHead.innerHTML = "<tr><th>基金名稱</th></tr>";
    performanceReturnsBody.innerHTML = '<tr><td class="empty">無法顯示資料</td></tr>';
    setPerformanceMessage(error.message, "error");
  }
});

startUpdateButton.addEventListener("click", async () => {
  startUpdateButton.disabled = true;
  setUpdateMessage("基金清單更新中", "loading");

  try {
    const payload = await startFundListUpdate();
    renderUpdateStatus(payload);
  } catch (error) {
    startUpdateButton.disabled = false;
    setUpdateMessage(`${error.message}；也可改用根目錄的 update_fundlist.bat`, "error");
  }
});

Object.values(investmentStates).forEach((state) => {
  state.form.addEventListener("submit", (event) => handleInvestmentSubmit(state, event));
  state.codeInput.addEventListener("input", () => {
    lookupInvestmentFundName(state);
  });
  state.cancelButton.addEventListener("click", () => {
    resetInvestmentForm(state);
    setInvestmentMessage(state, "", "");
  });
  state.body.addEventListener("click", (event) => {
    handleInvestmentTableAction(state, event);
  });
});
