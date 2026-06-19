const form = document.querySelector("#query-form");
const input = document.querySelector("#fund-code");
const message = document.querySelector("#message");
const summary = document.querySelector("#fund-summary");
const navBody = document.querySelector("#nav-body");

const summaryFields = {
  code: document.querySelector("#summary-code"),
  name: document.querySelector("#summary-name"),
  market: document.querySelector("#summary-market"),
  trans: document.querySelector("#summary-trans"),
};

function setMessage(text, type = "") {
  message.textContent = text;
  message.dataset.type = type;
}

function formatNumber(value, digits = 4) {
  if (value === null || value === undefined) return "-";
  return Number(value).toFixed(digits);
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
