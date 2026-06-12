// "Kjør analyse på nytt" — henter JSON fra POST /call/<name>/analyze og
// rebygger analyse-panelet klient-side. Holder samme visning som server-render.

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function band(pct) {
  return pct >= 80 ? "good" : pct >= 50 ? "mid" : "bad";
}

function renderAnalysis(a) {
  const sc = a.scorecard || { items: [] };
  const items = sc.items || [];
  const total = items.reduce((n, i) => n + (i.score || 0), 0);
  const max = items.length;
  const pct = max ? Math.round((100 * total) / max) : 0;

  const scItems = items.map((i) => {
    const pass = i.score === 1;
    return `<li class="sc-item sc-${pass ? "pass" : "fail"}">
      <span class="sc-mark">${pass ? "✓" : "✗"}</span>
      <span class="sc-label">${esc(i.label)}</span>
      <span class="sc-ev">${esc(i.evidence)}</span>
    </li>`;
  }).join("");

  const flags = (a.compliance_flags || []).length
    ? `<ul class="flags">${a.compliance_flags.map((f) => `<li class="flag">⚠ ${esc(f)}</li>`).join("")}</ul>`
    : `<p class="ok">✓ Ingen flagg.</p>`;

  const follow = (a.follow_up || []).length
    ? `<ul class="follow-up">${a.follow_up.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
    : `<p>—</p>`;

  const ki = a.key_info || {};

  // --- Utvidede felter (kan mangle — render defensivt) --- //
  const churn = a.churn_risk
    ? `<div class="mini"><span class="mini-label">Churn-risiko</span>
         <span class="churn churn-${esc(a.churn_risk)}">${esc(a.churn_risk)}</span></div>`
    : "";
  const reason = a.call_reason
    ? `<div class="mini"><span class="mini-label">Henvendelsesårsak</span>
         <span class="reason-chip">${esc(a.call_reason)}</span></div>`
    : "";

  const adherence = a.script_adherence
    ? `<div class="a-block"><h3>Manus-etterlevelse</h3>
         <div class="score-bar"><div class="score-bar-fill fill-${band(a.script_adherence)}"
           style="width: ${a.script_adherence}%"></div></div>
         <span class="adherence-val">${a.script_adherence}%</span></div>`
    : "";

  const coaching = (a.coaching_tips || []).length
    ? `<div class="a-block"><h3>Coaching til agenten</h3>
         <ul class="coaching">${a.coaching_tips.map((t) => `<li>💡 ${esc(t)}</li>`).join("")}</ul></div>`
    : "";

  return `
    <p class="backend-note">Analysert av backend: <code>${esc(a.backend)}</code></p>
    <div class="a-block"><h3>Sammendrag</h3><p class="summary">${esc(a.summary)}</p></div>
    <div class="a-block badge-row">
      <div class="mini"><span class="mini-label">Sentiment</span>
        <span class="sentiment sentiment-${esc(a.sentiment)}">${esc(a.sentiment)}</span></div>
      ${churn}
      ${reason}
    </div>
    <div class="a-block">
      <h3>QA-scorecard <span class="score-total score-${band(pct)}">${total}/${max} (${pct}%)</span></h3>
      <div class="score-bar"><div class="score-bar-fill fill-${band(pct)}" style="width: ${pct}%"></div></div>
      <ul class="scorecard">${scItems}</ul>
    </div>
    ${adherence}
    <div class="a-block"><h3>Nøkkelinfo</h3>
      <table class="kv">
        <tr><th>Intensjon</th><td>${esc(ki.intent) || "—"}</td></tr>
        <tr><th>Produkt/tjeneste</th><td>${esc(ki.product) || "—"}</td></tr>
        <tr><th>Utfall</th><td>${esc(ki.outcome) || "—"}</td></tr>
        <tr><th>Neste steg</th><td>${esc(ki.next_step) || "—"}</td></tr>
      </table>
    </div>
    <div class="a-block"><h3>Compliance-flagg</h3>${flags}</div>
    ${coaching}
    <div class="a-block"><h3>Foreslått oppfølging</h3>${follow}</div>
  `;
}

document.addEventListener("DOMContentLoaded", () => {
  const panel = document.getElementById("analysis-panel");
  const btn = document.getElementById("reanalyze-btn");
  const body = document.getElementById("analysis-body");
  if (!panel || !btn || !body) return;

  btn.addEventListener("click", async () => {
    const name = panel.dataset.name;
    btn.disabled = true;
    btn.textContent = "Analyserer…";
    try {
      const res = await fetch(`/call/${encodeURIComponent(name)}/analyze`, { method: "POST" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      body.innerHTML = renderAnalysis(data.analysis);
      // re-trigger inn-animasjon
      body.classList.remove("analysis-body-anim");
      void body.offsetWidth;
      body.classList.add("analysis-body-anim");
    } catch (e) {
      body.innerHTML = `<p class="flag">Feil ved analyse: ${esc(e.message)}</p>`;
    } finally {
      btn.disabled = false;
      btn.textContent = "↻ Kjør analyse på nytt";
    }
  });
});
