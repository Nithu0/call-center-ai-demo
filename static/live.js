// Live tale-til-tekst — klient-side STT via Web Speech API + analyse mot
// POST /analyze-text. Egen lane: denne fila styrer KUN /live-siden.
//
// Flyt:
//   1. Web Speech API (nb-NO, continuous, interimResults) → live tekst.
//      Interim = grå, endelig = hvit. Valgfri lyd-nivå-indikator via AudioContext.
//   2. "Analyser denne samtalen" → POST /analyze-text {text, call_type}
//      → svaret {analysis, transcript} rendres i analyse-panelet.
//   3. Fallback uten Web Speech API: manuelt tekstfelt, samme analyse.

(function () {
  "use strict";

  // ---------- felles helpers (speil av static/app.js) ---------- //
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function band(pct) {
    return pct >= 80 ? "good" : pct >= 50 ? "mid" : "bad";
  }

  function renderAnalysis(a) {
    a = a || {};
    const sc = a.scorecard || { items: [] };
    const items = sc.items || [];
    const total = sc.total != null ? sc.total : items.reduce((n, i) => n + (i.score || 0), 0);
    const max = sc.max_score != null ? sc.max_score : items.length;
    const pct = sc.percent != null ? sc.percent : (max ? Math.round((100 * total) / max) : 0);

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
      ${a.backend ? `<p class="backend-note">Analysert av backend: <code>${esc(a.backend)}</code></p>` : ""}
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

  // ---------- analyse-kall (delt av live + fallback) ---------- //
  async function analyzeText(text, bodyEl, btnEl, btnLabel) {
    text = (text || "").trim();
    if (!text) {
      bodyEl.innerHTML = `<p class="flag">⚠ Ingen tekst å analysere ennå.</p>`;
      return;
    }
    const oldLabel = btnEl ? btnEl.textContent : "";
    if (btnEl) { btnEl.disabled = true; btnEl.textContent = "Analyserer…"; }
    bodyEl.innerHTML = `<p class="live-empty">Analyserer samtalen …</p>`;
    try {
      const res = await fetch("/analyze-text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text, call_type: "kundeservice" }),
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      bodyEl.innerHTML = renderAnalysis(data.analysis || data);
      bodyEl.classList.remove("analysis-body-anim");
      void bodyEl.offsetWidth;
      bodyEl.classList.add("analysis-body-anim");
    } catch (e) {
      bodyEl.innerHTML = `<p class="flag">Feil ved analyse: ${esc(e.message)}</p>`;
    } finally {
      if (btnEl) { btnEl.disabled = false; btnEl.textContent = btnLabel || oldLabel; }
    }
  }

  // ---------- oppsett ---------- //
  document.addEventListener("DOMContentLoaded", () => {
    const analysisBody = document.getElementById("analysis-body");
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    const speechUI = document.getElementById("speech-ui");
    const fallbackUI = document.getElementById("fallback-ui");

    // --- FALLBACK: ingen Web Speech API --- //
    if (!SpeechRecognition) {
      if (fallbackUI) fallbackUI.hidden = false;
      const fbBtn = document.getElementById("fallback-analyze-btn");
      const fbText = document.getElementById("fallback-text");
      if (fbBtn && fbText) {
        fbBtn.addEventListener("click", () =>
          analyzeText(fbText.value, analysisBody, fbBtn, "✨ Analyser denne samtalen"));
      }
      return;
    }

    // --- WEB SPEECH-MODUS --- //
    if (speechUI) speechUI.hidden = false;

    const recordBtn = document.getElementById("record-btn");
    const recordLabel = document.getElementById("record-label");
    const statusEl = document.getElementById("live-status");
    const timerEl = document.getElementById("timer");
    const levelBar = document.getElementById("level-bar");
    const finalEl = document.getElementById("transcript-final");
    const interimEl = document.getElementById("transcript-interim");
    const emptyEl = document.getElementById("transcript-empty");
    const analyzeBtn = document.getElementById("analyze-btn");
    const clearBtn = document.getElementById("clear-btn");

    let recognition = null;
    let recording = false;
    let wantStop = false;       // bruker trykket stopp (ikke auto-restart da)
    let finalText = "";         // akkumulert endelig tekst (ren tekst for analyse)
    let timerId = null;
    let startedAt = 0;

    // lyd-nivå (valgfritt — feiler stille om mikrofon-stream ikke gis)
    let audioCtx = null, analyser = null, micStream = null, rafId = null;

    function setStatus(state, label) {
      statusEl.className = "live-status live-status-" + state;
      statusEl.textContent = label;
    }
    function fmt(ms) {
      const s = Math.floor(ms / 1000);
      const m = String(Math.floor(s / 60)).padStart(2, "0");
      const ss = String(s % 60).padStart(2, "0");
      return `${m}:${ss}`;
    }
    function tickTimer() { timerEl.textContent = fmt(Date.now() - startedAt); }

    function currentSpeaker() {
      const r = document.querySelector('input[name="speaker"]:checked');
      return r ? r.value : "alt";
    }
    function speakerTag() {
      const v = currentSpeaker();
      return v === "alt" ? "" : `<span class="who">${v === "agent" ? "Agent" : "Kunde"}:</span>`;
    }
    function speakerPlain() {
      const v = currentSpeaker();
      return v === "alt" ? "" : (v === "agent" ? "Agent: " : "Kunde: ");
    }

    function appendFinal(chunk) {
      chunk = chunk.trim();
      if (!chunk) return;
      if (emptyEl) emptyEl.hidden = true;
      finalText += (finalText ? "\n" : "") + speakerPlain() + chunk;
      const line = document.createElement("p");
      line.className = "live-final-line";
      line.innerHTML = speakerTag() + esc(chunk);
      finalEl.appendChild(line);
      finalEl.parentElement.scrollTop = finalEl.parentElement.scrollHeight;
      if (analyzeBtn) analyzeBtn.disabled = false;
    }

    // --- lyd-nivå-indikator --- //
    async function startLevelMeter() {
      try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const src = audioCtx.createMediaStreamSource(micStream);
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 512;
        src.connect(analyser);
        const buf = new Uint8Array(analyser.frequencyBinCount);
        const loop = () => {
          analyser.getByteTimeDomainData(buf);
          let peak = 0;
          for (let i = 0; i < buf.length; i++) {
            const v = Math.abs(buf[i] - 128);
            if (v > peak) peak = v;
          }
          const pct = Math.min(100, Math.round((peak / 128) * 180));
          levelBar.style.width = pct + "%";
          rafId = requestAnimationFrame(loop);
        };
        loop();
      } catch (e) {
        // mikrofon-tilgang nektet/ikke tilgjengelig → nivå-meter er valgfritt
        if (levelBar) levelBar.style.width = "0%";
      }
    }
    function stopLevelMeter() {
      if (rafId) cancelAnimationFrame(rafId), (rafId = null);
      if (micStream) micStream.getTracks().forEach((t) => t.stop()), (micStream = null);
      if (audioCtx) { try { audioCtx.close(); } catch (_) {} audioCtx = null; }
      if (levelBar) levelBar.style.width = "0%";
    }

    function buildRecognition() {
      const rec = new SpeechRecognition();
      rec.lang = "nb-NO";
      rec.continuous = true;
      rec.interimResults = true;

      rec.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const res = event.results[i];
          if (res.isFinal) appendFinal(res[0].transcript);
          else interim += res[0].transcript;
        }
        interimEl.textContent = interim ? " " + interim : "";
      };
      rec.onerror = (e) => {
        if (e.error === "not-allowed" || e.error === "service-not-allowed") {
          setStatus("idle", "Mikrofon nektet");
          stopAll();
        }
        // "no-speech"/"aborted" ignoreres — onend håndterer restart
      };
      rec.onend = () => {
        // continuous-økter avsluttes av seg selv; restart til bruker stopper
        if (recording && !wantStop) {
          try { rec.start(); } catch (_) {}
        }
      };
      return rec;
    }

    function startAll() {
      finalText = finalText; // behold tidligere tekst (gjør at man kan fortsette)
      wantStop = false;
      recording = true;
      recognition = buildRecognition();
      try { recognition.start(); } catch (_) {}
      startedAt = startedAt || Date.now();
      if (!timerId) timerId = setInterval(tickTimer, 250);
      startLevelMeter();
      recordBtn.classList.add("is-recording");
      recordLabel.textContent = "⏹️ Stopp opptak";
      setStatus("rec", "Tar opp …");
    }
    function stopAll() {
      wantStop = true;
      recording = false;
      if (recognition) { try { recognition.stop(); } catch (_) {} }
      if (timerId) clearInterval(timerId), (timerId = null);
      stopLevelMeter();
      interimEl.textContent = "";
      recordBtn.classList.remove("is-recording");
      recordLabel.textContent = "🎙️ Start opptak";
      setStatus(finalText ? "done" : "idle", finalText ? "Stoppet — klar for analyse" : "Klar");
      if (finalText && analyzeBtn) analyzeBtn.disabled = false;
    }

    recordBtn.addEventListener("click", () => (recording ? stopAll() : startAll()));

    clearBtn.addEventListener("click", () => {
      finalText = "";
      startedAt = 0;
      finalEl.innerHTML = "";
      interimEl.textContent = "";
      timerEl.textContent = "00:00";
      if (emptyEl) emptyEl.hidden = false;
      if (analyzeBtn) analyzeBtn.disabled = true;
      analysisBody.innerHTML =
        `<p class="live-empty">Analysen vises her etter at du har analysert en samtale.</p>`;
      setStatus("idle", "Klar");
    });

    analyzeBtn.addEventListener("click", () => {
      if (recording) stopAll();
      analyzeText(finalText, analysisBody, analyzeBtn, "✨ Analyser denne samtalen");
    });
  });
})();
