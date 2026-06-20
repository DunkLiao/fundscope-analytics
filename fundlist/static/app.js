const viewButtons = document.querySelectorAll("[data-view]");
const viewPanels = document.querySelectorAll("[data-view-panel]");
const navButtons = document.querySelectorAll(".nav-button, .menu-list button");
const actionCards = document.querySelectorAll(".action-card");
const navMenu = document.querySelector(".nav-menu");

const form = document.querySelector("#query-form");
const input = document.querySelector("#fund-code");
const message = document.querySelector("#message");
const summary = document.querySelector("#fund-summary");
const navBody = document.querySelector("#nav-body");

const startUpdateButton = document.querySelector("#start-update");
const updateState = document.querySelector("#update-state");
const updateStarted = document.querySelector("#update-started");
const updateFinished = document.querySelector("#update-finished");
const updateMessage = document.querySelector("#update-message");

let updatePollTimer = null;

const summaryFields = {
  code: document.querySelector("#summary-code"),
  name: document.querySelector("#summary-name"),
  market: document.querySelector("#summary-market"),
  trans: document.querySelector("#summary-trans"),
};

const updateStateLabels = {
  idle: "待命",
  running: "讀取中",
  succeeded: "已完成",
  failed: "失敗",
};

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
}

function setMessage(text, type = "") {
  message.textContent = text;
  message.dataset.type = type;
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

function renderSummary(fund) {
  summaryFields.code.textContent = fund.fund_code || "-";
  summaryFields.name.textContent = fund.fund_name_main || fund.fund_name || "-";
  summaryFields.market.textContent = fund.market || "-";
  summaryFields.trans.textContent = fund.fund_id || "-";
  summary.hidden = false;
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

async function queryFund(code) {
  const response = await fetch(`/api/funds/${encodeURIComponent(code)}/nav`);
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
    if (button.closest(".menu-list") && navMenu) {
      navMenu.open = false;
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
