/* ══════════════════════════════════════════
   NOCTURNE — Dashboard JavaScript
   Connects to the FastAPI backend for
   weather, signal evaluation, history,
   and account data.
══════════════════════════════════════════ */

const API_BASE = 'https://nocturne-1m7s.onrender.com';
let currentSymbol = 'AAPLUSDT';
let liveInterval = null;
let timelineChart = null;
let timelineData = { labels: [], scores: [] };

// ── State → colour mapping ──
const STATE_COLOURS = {
  CLEAR:    '#22d3ee',
  CLOUDY:   '#facc15',
  STORM:    '#f97316',
  BLACKOUT: '#ef4444',
};
const CIRCUMFERENCE = 2 * Math.PI * 50; // r=50

// ─────────────────────────────────────────
// Tab navigation
// ─────────────────────────────────────────
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(`tab-${name}`).classList.add('active');
  document.getElementById(`nav-${name}`).classList.add('active');
}

// ─────────────────────────────────────────
// Symbol selection
// ─────────────────────────────────────────
function setSymbol(sym) {
  currentSymbol = sym;
  document.querySelectorAll('.pill').forEach(p => {
    const label = (p.dataset.symbol || p.textContent || '').trim().toUpperCase();
    p.classList.toggle('active', label === sym.toUpperCase());
  });
  fetchWeather();
}
function setCustomSymbol() {
  const v = document.getElementById('custom-symbol').value.trim().toUpperCase();
  if (v) { currentSymbol = v; fetchWeather(); }
}

// ─────────────────────────────────────────
// Live toggle
// ─────────────────────────────────────────
function toggleLive() {
  const on = document.getElementById('live-toggle').checked;
  if (liveInterval) {
    clearInterval(liveInterval);
    liveInterval = null;
  }
  if (on) {
    fetchWeather();
    liveInterval = setInterval(fetchWeather, 30000);
  }
}

// ─────────────────────────────────────────
// Weather fetch
// ─────────────────────────────────────────
async function fetchWeather({ explain = false, preserveDisplay = false } = {}) {
  setConnStatus('connecting');
  if (!preserveDisplay) showLoading(true);
  try {
    const res = await fetch(`${API_BASE}/weather/${currentSymbol}?explain=${explain}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderWeather(data);
    pushTimeline(data);
    setConnStatus('connected');
    return data;
  } catch (err) {
    setConnStatus('error');
    if (preserveDisplay) {
      document.getElementById('rationale-text').textContent = `Could not generate a rationale: ${err.message}`;
    } else {
      showError(err.message);
    }
    return null;
  }
}

async function generateRationale() {
  const btn = document.getElementById('generate-rationale-btn');
  const text = document.getElementById('rationale-text');
  btn.disabled = true;
  btn.textContent = 'Generating…';
  text.textContent = 'Checking current conditions and asking the AI for an explanation…';
  try {
    const data = await fetchWeather({ explain: true, preserveDisplay: true });
    if (data && !data.rationale) {
      text.textContent = 'The AI returned no explanation. Try again in a moment.';
    }
  } finally {
    btn.disabled = false;
    btn.textContent = '✦ Generate once';
  }
}

function showLoading(on) {
  document.getElementById('weather-loading').classList.toggle('hidden', !on);
  document.getElementById('weather-content').classList.toggle('hidden', on);
}

function showError(msg) {
  document.getElementById('weather-loading').innerHTML =
    `<p style="color:#ef4444;font-size:13px;">⚠ ${msg}</p>
     <button class="btn-secondary" style="margin-top:12px" onclick="fetchWeather()">Retry</button>`;
  document.getElementById('weather-loading').classList.remove('hidden');
  document.getElementById('weather-content').classList.add('hidden');
}

function renderWeather(d) {
  showLoading(false);

  const s = d.scores;
  const state = d.state;
  const colour = STATE_COLOURS[state] || '#6366f1';
  const score = Math.round(d.composite_score);

  // Badge
  const badge = document.getElementById('state-badge');
  badge.textContent = state;
  badge.className = `state-badge state-${state}`;

  // Score ring
  const fill = document.getElementById('ring-fill');
  const pct = score / 100;
  fill.style.strokeDasharray = `${CIRCUMFERENCE * pct} ${CIRCUMFERENCE}`;
  fill.style.stroke = colour;
  document.getElementById('score-value').textContent = score;
  document.getElementById('score-value').style.color = colour;

  // Action pill
  const actionMap = {
    TRADE:      { text: 'TRADE',      sub: 'Full strategy size permitted' },
    REDUCE:     { text: 'REDUCE',     sub: `Trade at ${Math.round(d.recommended_size_pct*100)}% of normal size` },
    WAIT:       { text: 'WAIT',       sub: 'No new entries — manage existing risk' },
    STAND_DOWN: { text: 'STAND DOWN', sub: 'Cancel pending orders and stand down' },
  };
  const act = actionMap[d.action] || { text: d.action, sub: '' };
  document.getElementById('action-pill').textContent = act.text;
  document.getElementById('action-pill').style.color = colour;
  document.getElementById('action-sub').textContent = act.sub;

  // Prices
  document.getElementById('bid-val').textContent   = d.bid    ? fmtPrice(d.bid)   : '—';
  document.getElementById('mid-val').textContent   = d.mid    ? fmtPrice(d.mid)   : '—';
  document.getElementById('ask-val').textContent   = d.ask    ? fmtPrice(d.ask)   : '—';
  document.getElementById('spread-val').textContent= d.spread_bps != null ? `${d.spread_bps.toFixed(1)} bps` : '—';

  // Bars
  setBar('spread', s.spread_score, colour);
  setBar('depth',  s.depth_score,  colour);
  setBar('vol',    s.volatility_score, colour);
  setBar('ll',     s.lead_lag_score, colour);
  setBar('ev',     s.event_score,  colour);

  // Stats
  document.getElementById('stat-vol').textContent   = d.realized_vol_1h != null ? `${d.realized_vol_1h.toFixed(1)}% ann.` : '—';
  document.getElementById('stat-depth').textContent = d.depth_within_25bps != null ? `$${fmtNum(d.depth_within_25bps)}` : '—';
  document.getElementById('stat-size').textContent  = `${Math.round(d.recommended_size_pct * 100)}%`;

  // AI only runs when the user presses Generate. Monitoring/refresh requests
  // carry no rationale and should clearly leave AI inactive.
  const rationaleText = document.getElementById('rationale-text');
  if (d.rationale) {
    renderRationale(d.rationale);
    document.getElementById('rationale-ts').textContent = `Generated: ${new Date(d.timestamp).toUTCString()}`;
  } else {
    rationaleText.textContent = 'AI is off. Live weather monitoring does not call the model. Generate one rationale only when needed.';
    document.getElementById('rationale-ts').textContent = '';
  }
}

function renderRationale(markdown) {
  const container = document.getElementById('rationale-text');
  container.replaceChildren();
  let list = null;

  const flushList = () => {
    if (list) container.appendChild(list);
    list = null;
  };

  for (const rawLine of markdown.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      continue;
    }

    const heading = line.match(/^#{1,3}\s+(.+)$/) || line.match(/^\*\*(.+)\*\*$/);
    if (heading) {
      flushList();
      const node = document.createElement('h4');
      node.className = 'rationale-heading';
      appendRationaleInline(node, heading[1]);
      container.appendChild(node);
      continue;
    }

    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      if (!list) {
        list = document.createElement('ul');
        list.className = 'rationale-list';
      }
      const item = document.createElement('li');
      appendRationaleInline(item, bullet[1]);
      list.appendChild(item);
      continue;
    }

    flushList();
    const paragraph = document.createElement('p');
    paragraph.className = 'rationale-paragraph';
    appendRationaleInline(paragraph, line);
    container.appendChild(paragraph);
  }
  flushList();
}

function appendRationaleInline(parent, text) {
  const tokens = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).filter(Boolean);
  for (const token of tokens) {
    if (token.startsWith('**') && token.endsWith('**')) {
      const strong = document.createElement('strong');
      strong.textContent = token.slice(2, -2);
      parent.appendChild(strong);
    } else if (token.startsWith('*') && token.endsWith('*')) {
      const emphasis = document.createElement('em');
      emphasis.textContent = token.slice(1, -1);
      parent.appendChild(emphasis);
    } else {
      parent.appendChild(document.createTextNode(token));
    }
  }
}

function setBar(id, val, colour) {
  const v = Math.round(val);
  const fill = document.getElementById(`bar-${id}`);
  fill.style.width = `${v}%`;
  fill.style.background = `linear-gradient(90deg, ${colour}88, ${colour})`;
  document.getElementById(`txt-${id}`).textContent = v;
}

// ─────────────────────────────────────────
// Timeline chart
// ─────────────────────────────────────────
function pushTimeline(data) {
  const ts = new Date(data.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  timelineData.labels.push(ts);
  timelineData.scores.push(Math.round(data.composite_score));
  if (timelineData.labels.length > 30) {
    timelineData.labels.shift();
    timelineData.scores.shift();
  }
  renderTimeline();
}

function renderTimeline() {
  const ctx = document.getElementById('timeline-chart').getContext('2d');
  if (timelineChart) {
    timelineChart.data.labels = timelineData.labels;
    timelineChart.data.datasets[0].data = timelineData.scores;
    timelineChart.update('none');
    return;
  }
  timelineChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: timelineData.labels,
      datasets: [{
        data: timelineData.scores,
        borderColor: '#6366f1',
        backgroundColor: 'rgba(99,102,241,0.08)',
        tension: 0.4,
        pointRadius: 3,
        pointBackgroundColor: '#6366f1',
        fill: true,
        borderWidth: 2,
      }],
    },
    options: {
      animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } },
        y: { min: 0, max: 100, ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } },
      },
    },
  });
}

// ─────────────────────────────────────────
// Signal Lab
// ─────────────────────────────────────────
async function submitSignal() {
  const btn = document.getElementById('submit-signal-btn');
  btn.disabled = true;
  btn.textContent = 'Evaluating…';

  const body = {
    symbol:      document.getElementById('sig-symbol').value.trim().toUpperCase(),
    signal_type: document.getElementById('sig-type').value,
    direction:   document.getElementById('sig-direction').value,
    strength:    parseFloat(document.getElementById('sig-strength').value),
    notional_usd:parseFloat(document.getElementById('sig-notional').value),
    notes:       document.getElementById('sig-notes').value,
  };
  const ep = document.getElementById('sig-entry').value;
  const sp = document.getElementById('sig-stop').value;
  const tp = document.getElementById('sig-target').value;
  if (ep) body.entry_price  = parseFloat(ep);
  if (sp) body.stop_price   = parseFloat(sp);
  if (tp) body.target_price = parseFloat(tp);

  try {
    const res = await fetch(`${API_BASE}/signal`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderDecision(data);
  } catch (err) {
    alert(`Error: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Evaluate Signal →';
  }
}

function renderDecision(data) {
  const panel = document.getElementById('signal-result');
  panel.classList.remove('hidden');

  const d = data.decision;
  const approved = d.approved;
  const badge = document.getElementById('decision-badge');
  badge.textContent = approved ? '✅ APPROVED' : '❌ REJECTED';
  badge.className = `decision-badge ${approved ? 'approved' : 'rejected'}`;

  if (approved) {
    document.getElementById('decision-detail').innerHTML =
      `<strong>Approved notional:</strong> $${d.approved_notional_usd?.toFixed(2)}<br>` +
      `<strong>Position size:</strong> ${Math.round((d.approved_size_pct || 0) * 100)}% of normal`;
  } else {
    document.getElementById('decision-detail').innerHTML =
      '<strong>Rejection reasons:</strong><ul style="margin-top:6px;padding-left:16px">' +
      d.rejection_reasons.map(r => `<li>${r}</li>`).join('') + '</ul>';
  }

  const w = data.weather;
  const col = STATE_COLOURS[w.state] || '#6366f1';
  document.getElementById('decision-weather').innerHTML =
    `<strong>Weather:</strong> <span style="color:${col}">${w.state}</span> ` +
    `(score ${Math.round(w.composite_score)}/100)`;

  document.getElementById('decision-rationale').textContent = data.rationale || '';
}

// ─────────────────────────────────────────
// History
// ─────────────────────────────────────────
async function fetchHistory() {
  const sym = document.getElementById('hist-symbol').value.trim().toUpperCase();
  try {
    const res = await fetch(`${API_BASE}/weather/${sym}/history?limit=50`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const rows = await res.json();
    renderHistory(rows);
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

function renderHistory(rows) {
  const tbody = document.getElementById('history-tbody');
  if (!rows.length) { tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No history yet.</td></tr>'; return; }
  tbody.innerHTML = rows.map(r => {
    const col = STATE_COLOURS[r.state] || '#6366f1';
    const sc = r.scores || {};
    return `<tr>
      <td>${new Date(r.timestamp).toUTCString()}</td>
      <td style="color:${col};font-weight:600">${r.state}</td>
      <td>${Math.round(r.composite_score)}</td>
      <td>${Math.round(sc.spread_score ?? 0)}</td>
      <td>${Math.round(sc.depth_score ?? 0)}</td>
      <td>${Math.round(sc.volatility_score ?? 0)}</td>
      <td>${r.action}</td>
    </tr>`;
  }).join('');
}

// ─────────────────────────────────────────
// Account
// ─────────────────────────────────────────
async function fetchAccount() {
  try {
    const res = await fetch(`${API_BASE}/account`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderAccount(data);
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

function renderAccount(data) {
  const balance = data.balance;
  const rows = Array.isArray(balance)
    ? balance
    : (Array.isArray(balance?.assets) ? balance.assets : []);
  const bal = rows.find(row => String(row.marginCoin || row.coin || '').toUpperCase() === 'USDT')
    || rows[0]
    || balance
    || {};
  const balDiv = document.getElementById('balance-content');
  balDiv.classList.remove('hidden');
  document.querySelector('.balance-loading')?.remove();

  const firstValue = (...values) => values.find(value => value !== undefined && value !== null && value !== '');
  const displayValue = value => {
    const numeric = Number(value);
    return value !== undefined && value !== null && value !== '' && Number.isFinite(numeric)
      ? numeric.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
      : '—';
  };
  const fields = [
    ['USDT Equity', firstValue(bal.usdtEquity, bal.accountEquity, bal.equity, bal.equityValue)],
    ['Available', firstValue(bal.available, bal.availableBalance, bal.availableEquity, bal.maxTransferOut)],
    ['Unrealized PnL', firstValue(bal.unrealizedPL, bal.unrealizedPnl, bal.uPnL, bal.unrealizedProfit)],
    ['Margin Ratio', firstValue(bal.marginRatio, bal.crossedRiskRate, bal.riskRate)],
  ];
  balDiv.innerHTML = fields.map(([k, v]) =>
    `<div class="account-stat"><span class="stat-label">${k}</span><span class="stat-value" style="font-family:var(--mono)">${displayValue(v)}</span></div>`
  ).join('');

  const posDiv = document.getElementById('positions-content');
  const positions = data.positions || [];
  if (!positions.length) {
    posDiv.innerHTML = '<p class="empty-state">No open positions.</p>';
  } else {
    posDiv.innerHTML = positions.map(p => {
      const side = p.holdSide || p.posSide || p.side || 'spot';
      const directionColour = side.toLowerCase() === 'long' || side.toLowerCase() === 'buy' ? '#4ade80' : '#ef4444';
      const amount = firstValue(p.total, p.size, p.available, p.usdValue, 0);
      const symbol = String(p.symbol || p.coin || 'Asset');
      return `<div class="account-stat">
        <span>${symbol} <span style="color:${directionColour}">${side}</span></span>
        <span style="font-family:var(--mono)">$${displayValue(amount)}</span>
      </div>`;
    }).join('');
  }
}

// ─────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────
function fmtPrice(n) { return Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 }); }
function fmtNum(n)   { return Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 }); }

function setConnStatus(state) {
  const el = document.getElementById('conn-status');
  const map = {
    connecting: ['● CONNECTING', ''],
    connected:  ['● LIVE',       'connected'],
    error:      ['● ERROR',      'error'],
  };
  const [text, cls] = map[state] || ['● UNKNOWN', ''];
  el.textContent = text;
  el.className = `status-pill ${cls}`;
}

// ─────────────────────────────────────────
// Init
// ─────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Initialize the score ring
  const fill = document.getElementById('ring-fill');
  fill.style.strokeDasharray = `0 ${CIRCUMFERENCE}`;

  // Check API health
  fetch(`${API_BASE}/health`)
    .then(r => r.json())
    .then(() => setConnStatus('connected'))
    .catch(() => setConnStatus('error'));
});
