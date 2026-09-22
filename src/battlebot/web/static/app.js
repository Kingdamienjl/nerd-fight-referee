/**
 * Nerd Fight Referee — Web Portal Client Logic
 */

document.addEventListener("DOMContentLoaded", () => {
  // State
  const state = {
    contenderA: {
      name: "",
      franchise: "",
      category: "",
      form: "base",
      imageUrl: "",
    },
    contenderB: {
      name: "",
      franchise: "",
      category: "",
      form: "base",
      imageUrl: "",
    },
    lastDecision: null,
    currentPhases: [],
    isSimulating: false,
  };


  // DOM Elements - Alpha (A)
  const searchInputA = document.getElementById("search-input-a");
  const suggestionsA = document.getElementById("suggestions-a");
  const btnClearA = document.getElementById("btn-clear-a");
  const imageA = document.getElementById("image-a");
  const displayNameA = document.getElementById("display-name-a");
  const pillFranchiseA = document.getElementById("pill-franchise-a");
  const pillCategoryA = document.getElementById("pill-category-a");
  const badgeReadyA = document.getElementById("badge-ready-a");
  const formSelectA = document.getElementById("form-select-a");
  const imgSearchA = document.getElementById("img-search-a");
  const btnFetchImgA = document.getElementById("btn-fetch-img-a");

  // DOM Elements - Omega (B)
  const searchInputB = document.getElementById("search-input-b");
  const suggestionsB = document.getElementById("suggestions-b");
  const btnClearB = document.getElementById("btn-clear-b");
  const imageB = document.getElementById("image-b");
  const displayNameB = document.getElementById("display-name-b");
  const pillFranchiseB = document.getElementById("pill-franchise-b");
  const pillCategoryB = document.getElementById("pill-category-b");
  const badgeReadyB = document.getElementById("badge-ready-b");
  const formSelectB = document.getElementById("form-select-b");
  const imgSearchB = document.getElementById("img-search-b");
  const btnFetchImgB = document.getElementById("btn-fetch-img-b");

  // Nexus & Options
  const toggleEnergy = document.getElementById("toggle-energy");
  const eqDesc = document.getElementById("eq-desc");
  const selectArena = document.getElementById("select-arena");
  const selectPrep = document.getElementById("select-prep");
  const toggleWebhook = document.getElementById("toggle-webhook");
  const btnSimulate = document.getElementById("btn-simulate-duel");
  const btnLabel = document.getElementById("btn-label");
  const progressWrap = document.getElementById("progress-wrap");
  const progressFill = document.getElementById("progress-fill");
  const progressStatus = document.getElementById("progress-status");

  // Results Section
  const resultsSection = document.getElementById("results-section");
  const winnerHeadline = document.getElementById("winner-headline");
  const diffBadge = document.getElementById("diff-badge");
  const oddsLabelA = document.getElementById("odds-label-a");
  const oddsLabelB = document.getElementById("odds-label-b");
  const oddsFillA = document.getElementById("odds-fill-a");
  const oddsFillB = document.getElementById("odds-fill-b");

  const resHeaderA = document.getElementById("res-header-a");
  const toolsA = document.getElementById("tools-a");
  const winA = document.getElementById("win-a");
  const riskA = document.getElementById("risk-a");

  const resHeaderB = document.getElementById("res-header-b");
  const toolsB = document.getElementById("tools-b");
  const winB = document.getElementById("win-b");
  const riskB = document.getElementById("risk-b");

  const quickVerdictText = document.getElementById("quick-verdict-text");
  const phase0Text = document.getElementById("phase-0-text");
  const phase1Text = document.getElementById("phase-1-text");
  const phase2Text = document.getElementById("phase-2-text");

  const btnReDispatch = document.getElementById("btn-re-dispatch");
  const deliveryStatus = document.getElementById("delivery-status");
  const discordEmbedTitle = document.getElementById("discord-embed-title");
  const discordEmbedFields = document.getElementById("discord-embed-fields");
  const discordPill = document.getElementById("discord-pill");

  // Portal Link Copy
  const btnCopyPortal = document.getElementById("btn-copy-portal");
  const copyPortalIcon = document.getElementById("copy-portal-icon");
  const copyPortalLabel = document.getElementById("copy-portal-label");
  if (btnCopyPortal) {
    btnCopyPortal.addEventListener("click", async () => {
      const url = "https://altprox.tail4e8997.ts.net/";
      try {
        await navigator.clipboard.writeText(url);
        copyPortalIcon.textContent = "✅";
        copyPortalLabel.textContent = "Copied!";
        showToast("Public Portal link copied to clipboard!", "success");
        setTimeout(() => {
          copyPortalIcon.textContent = "📋";
          copyPortalLabel.textContent = "Copy Link";
        }, 2500);
      } catch (err) {
        showToast(`URL: ${url}`, "info");
      }
    });
  }

  // Multi-Stage Controller Elements
  const stageTabs = document.querySelectorAll(".stage-tab");
  const phaseCards = document.querySelectorAll(".phase-card.clickable");
  const stageFocusView = document.getElementById("stage-focus-view");
  const playByPlayGrid = document.getElementById("play-by-play-grid");
  const focusStageBadge = document.getElementById("focus-stage-badge");
  const focusStageTitle = document.getElementById("focus-stage-title");
  const focusStageText = document.getElementById("focus-stage-text");
  const btnPrevStage = document.getElementById("btn-prev-stage");
  const btnNextStage = document.getElementById("btn-next-stage");
  const btnCloseFocus = document.getElementById("btn-close-focus");

  const STAGE_META = [
    { badge: "STAGE 1 OF 3", title: "Neutral & Probing Exchange" },
    { badge: "STAGE 2 OF 3", title: "Escalation & Tool Deployment" },
    { badge: "STAGE 3 OF 3", title: "Climax & Decisive Factor" },
  ];

  let currentFocusedStage = null;

  function setFocusedStage(index) {
    if (index === null || index === undefined || index === "all") {
      currentFocusedStage = null;
      if (stageFocusView) stageFocusView.classList.add("hidden");
      if (playByPlayGrid) playByPlayGrid.classList.remove("hidden");
      phaseCards.forEach(c => c.classList.remove("active"));
      stageTabs.forEach(t => t.classList.toggle("active", t.dataset.stage === "all"));
      return;
    }

    const idx = parseInt(index, 10);
    if (isNaN(idx) || idx < 0 || idx > 2) return;

    currentFocusedStage = idx;
    if (stageFocusView) stageFocusView.classList.remove("hidden");
    if (focusStageBadge) {
      focusStageBadge.textContent = STAGE_META[idx].badge;
      focusStageBadge.className = `focus-badge badge-stage-${idx + 1}`;
    }
    if (focusStageTitle) focusStageTitle.textContent = STAGE_META[idx].title;

    const text = (state.currentPhases && state.currentPhases[idx]) || "Analysis for this stage is currently being arbitrated.";
    if (focusStageText) focusStageText.textContent = text;

    if (btnPrevStage) btnPrevStage.disabled = (idx === 0);
    if (btnNextStage) btnNextStage.disabled = (idx === 2);

    phaseCards.forEach((c, i) => c.classList.toggle("active", i === idx));
    stageTabs.forEach(t => t.classList.toggle("active", t.dataset.stage === String(idx)));

    if (stageFocusView) {
      stageFocusView.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  stageTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const stage = tab.dataset.stage;
      setFocusedStage(stage === "all" ? null : stage);
    });
  });

  phaseCards.forEach(card => {
    card.addEventListener("click", () => {
      const stage = card.dataset.stage;
      setFocusedStage(stage);
    });
  });

  if (btnPrevStage) {
    btnPrevStage.addEventListener("click", () => {
      if (currentFocusedStage !== null && currentFocusedStage > 0) {
        setFocusedStage(currentFocusedStage - 1);
      }
    });
  }

  if (btnNextStage) {
    btnNextStage.addEventListener("click", () => {
      if (currentFocusedStage !== null && currentFocusedStage < 2) {
        setFocusedStage(currentFocusedStage + 1);
      }
    });
  }

  if (btnCloseFocus) {
    btnCloseFocus.addEventListener("click", () => {
      setFocusedStage(null);
    });
  }


  // Debounce utility
  function debounce(fn, ms) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  // Toast Notification utility
  function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // Check health on start
  async function checkHealth() {
    try {
      const res = await fetch("/api/health");
      if (res.ok) {
        const data = await res.json();
        const apiPill = document.getElementById("api-status-pill");
        if (apiPill) {
          apiPill.innerHTML = `<span class="status-dot dot-emerald"></span><span class="status-text">${data.llm_model.toUpperCase()} ONLINE</span>`;
        }
      }
    } catch (e) {
      console.warn("Backend health check failed:", e);
    }
  }
  checkHealth();

  // Energy toggle text update
  toggleEnergy.addEventListener("change", () => {
    if (toggleEnergy.checked) {
      eqDesc.textContent = "EQUALIZED ENERGY (Standardizing power frameworks)";
      eqDesc.style.color = "var(--cyan-core)";
    } else {
      eqDesc.textContent = "RAW LITERAL RULES (Ki ≠ Chakra ≠ Magic)";
      eqDesc.style.color = "var(--text-muted)";
    }
  });

  // Autocomplete Search Logic
  async function searchFighters(query, dropdownEl, cornerKey) {
    if (!query || query.trim().length < 1) {
      dropdownEl.classList.remove("active");
      dropdownEl.innerHTML = "";
      return;
    }

    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=10`);
      if (!res.ok) return;
      const data = await res.json();
      const list = data.results || [];

      if (list.length === 0) {
        dropdownEl.innerHTML = `<div class="suggestion-item"><span class="sugg-name">No catalog match found. Press Enter to use literal name.</span></div>`;
        dropdownEl.classList.add("active");
        return;
      }

      dropdownEl.innerHTML = "";
      list.forEach((item) => {
        const row = document.createElement("div");
        row.className = "suggestion-item";
        row.innerHTML = `
          <div>
            <div class="sugg-name">${item.name}</div>
            <div class="sugg-franchise">${item.franchise} • ${item.category}</div>
          </div>
          <span class="sugg-pill">${item.battle_ready ? "READY" : "STUB"}</span>
        `;
        row.addEventListener("click", () => {
          selectFighter(item, cornerKey);
          dropdownEl.classList.remove("active");
        });
        dropdownEl.appendChild(row);
      });
      dropdownEl.classList.add("active");
    } catch (err) {
      console.error("Search error:", err);
    }
  }

  // Select Fighter
  async function selectFighter(fighter, cornerKey) {
    const isA = cornerKey === "A";
    const st = isA ? state.contenderA : state.contenderB;
    st.name = fighter.name;
    st.franchise = fighter.franchise || "";
    st.category = fighter.category || "";

    // Update UI elements
    if (isA) {
      searchInputA.value = fighter.name;
      displayNameA.textContent = fighter.name;
      pillFranchiseA.textContent = `Franchise: ${fighter.franchise || "--"}`;
      pillCategoryA.textContent = `Category: ${fighter.category || "--"}`;
      badgeReadyA.textContent = "READY";
      badgeReadyA.classList.add("is-ready");
      imgSearchA.value = fighter.name;
    } else {
      searchInputB.value = fighter.name;
      displayNameB.textContent = fighter.name;
      pillFranchiseB.textContent = `Franchise: ${fighter.franchise || "--"}`;
      pillCategoryB.textContent = `Category: ${fighter.category || "--"}`;
      badgeReadyB.textContent = "READY";
      badgeReadyB.classList.add("is-ready");
      imgSearchB.value = fighter.name;
    }

    // Fetch and populate forms
    await loadForms(fighter.name, isA ? formSelectA : formSelectB, st);

    // Fetch and set character artwork
    await loadCharacterImage(fighter.name, fighter.franchise, isA ? imageA : imageB, st);
  }

  // Load Forms Dropdown
  async function loadForms(name, selectEl, st) {
    selectEl.innerHTML = `<option value="base">Canonical Base / Standard Form</option>`;
    try {
      const res = await fetch(`/api/forms?name=${encodeURIComponent(name)}`);
      if (res.ok) {
        const data = await res.json();
        const forms = data.forms || [];
        forms.forEach((f) => {
          const opt = document.createElement("option");
          opt.value = f;
          opt.textContent = f;
          selectEl.appendChild(opt);
        });
      }
    } catch (err) {
      console.warn("Forms fetch error:", err);
    }
    st.form = selectEl.value;
  }

  // Form change listeners
  formSelectA.addEventListener("change", (e) => {
    state.contenderA.form = e.target.value;
  });
  formSelectB.addEventListener("change", (e) => {
    state.contenderB.form = e.target.value;
  });

  // Load Image
  async function loadCharacterImage(name, franchise, imgEl, st) {
    try {
      const res = await fetch(`/api/character-image?name=${encodeURIComponent(name)}&franchise=${encodeURIComponent(franchise || "")}`);
      if (res.ok) {
        const data = await res.json();
        if (data.image_url) {
          imgEl.src = data.image_url;
          st.imageUrl = data.image_url;
        }
      }
    } catch (err) {
      console.warn("Image fetch error:", err);
    }
  }

  // Custom Image Search Handlers
  async function handleCustomImageSearch(cornerKey) {
    const isA = cornerKey === "A";
    const query = (isA ? imgSearchA.value : imgSearchB.value).trim();
    if (!query) return;

    const imgEl = isA ? imageA : imageB;
    const st = isA ? state.contenderA : state.contenderB;

    if (query.startsWith("http://") || query.startsWith("https://")) {
      imgEl.src = query;
      st.imageUrl = query;
      showToast(`Updated ${isA ? "Corner A" : "Corner B"} artwork directly from URL.`, "success");
      return;
    }

    showToast(`Searching artwork for "${query}"...`, "info");
    await loadCharacterImage(query, "", imgEl, st);
    showToast(`Refreshed artwork for ${isA ? "Corner A" : "Corner B"}.`, "success");
  }

  btnFetchImgA.addEventListener("click", () => handleCustomImageSearch("A"));
  btnFetchImgB.addEventListener("click", () => handleCustomImageSearch("B"));
  imgSearchA.addEventListener("keydown", (e) => { if (e.key === "Enter") handleCustomImageSearch("A"); });
  imgSearchB.addEventListener("keydown", (e) => { if (e.key === "Enter") handleCustomImageSearch("B"); });

  // Bind Search Inputs with Debounce
  const debouncedSearchA = debounce((val) => searchFighters(val, suggestionsA, "A"), 250);
  searchInputA.addEventListener("input", (e) => debouncedSearchA(e.target.value));
  searchInputA.addEventListener("focus", (e) => { if (e.target.value) debouncedSearchA(e.target.value); });

  const debouncedSearchB = debounce((val) => searchFighters(val, suggestionsB, "B"), 250);
  searchInputB.addEventListener("input", (e) => debouncedSearchB(e.target.value));
  searchInputB.addEventListener("focus", (e) => { if (e.target.value) debouncedSearchB(e.target.value); });

  // Clear buttons
  btnClearA.addEventListener("click", () => {
    searchInputA.value = "";
    suggestionsA.classList.remove("active");
    state.contenderA.name = "";
    displayNameA.textContent = "Contender Alpha";
    pillFranchiseA.textContent = "Franchise: --";
    pillCategoryA.textContent = "Category: --";
    badgeReadyA.textContent = "SELECT FIGHTER";
    badgeReadyA.classList.remove("is-ready");
    imageA.src = "https://placehold.co/400x550/161B26/EF4444?text=Contender+A";
  });

  btnClearB.addEventListener("click", () => {
    searchInputB.value = "";
    suggestionsB.classList.remove("active");
    state.contenderB.name = "";
    displayNameB.textContent = "Contender Omega";
    pillFranchiseB.textContent = "Franchise: --";
    pillCategoryB.textContent = "Category: --";
    badgeReadyB.textContent = "SELECT FIGHTER";
    badgeReadyB.classList.remove("is-ready");
    imageB.src = "https://placehold.co/400x550/161B26/06B6D4?text=Contender+B";
  });

  // Close suggestions when clicking outside
  document.addEventListener("click", (e) => {
    if (!searchInputA.contains(e.target) && !suggestionsA.contains(e.target)) {
      suggestionsA.classList.remove("active");
    }
    if (!searchInputB.contains(e.target) && !suggestionsB.contains(e.target)) {
      suggestionsB.classList.remove("active");
    }
  });

  // PROGRESS SIMULATION SEQUENCE
  const progressSteps = [
    { pct: 15, msg: "Connecting to Referee Combat Matrix..." },
    { pct: 35, msg: "Fetching character profiles & verifying battle eligibility..." },
    { pct: 55, msg: "Assembling battle packet & checking energy equalization..." },
    { pct: 75, msg: "Calculating speed deltas, AP vs Durability & hax counters..." },
    { pct: 90, msg: "Synthesizing 3-phase narrative & calling Discord webhook..." },
  ];

  let progressInterval = null;

  function startProgress() {
    progressWrap.classList.add("active");
    progressFill.style.width = "10%";
    progressStatus.textContent = progressSteps[0].msg;
    let stepIndex = 0;

    progressInterval = setInterval(() => {
      stepIndex++;
      if (stepIndex < progressSteps.length) {
        progressFill.style.width = `${progressSteps[stepIndex].pct}%`;
        progressStatus.textContent = progressSteps[stepIndex].msg;
      }
    }, 1800);
  }

  function finishProgress() {
    clearInterval(progressInterval);
    progressFill.style.width = "100%";
    progressStatus.textContent = "Duel arbitration complete!";
    setTimeout(() => {
      progressWrap.classList.remove("active");
    }, 1200);
  }

  // EXECUTE FIGHT SIMULATION
  btnSimulate.addEventListener("click", async () => {
    const nameA = (state.contenderA.name || searchInputA.value).trim();
    const nameB = (state.contenderB.name || searchInputB.value).trim();

    if (!nameA || !nameB) {
      showToast("Please specify both Contender A and Contender B!", "error");
      return;
    }

    if (state.isSimulating) return;
    state.isSimulating = true;
    btnSimulate.classList.add("is-loading");
    btnLabel.textContent = "ARBITRATING MATCHUP...";
    startProgress();

    const payload = {
      contender_a: nameA,
      form_a: state.contenderA.form,
      image_a: state.contenderA.imageUrl,
      contender_b: nameB,
      form_b: state.contenderB.form,
      image_b: state.contenderB.imageUrl,
      arena: selectArena.value,
      prep_time: selectPrep.value,
      energy_equalization: toggleEnergy.checked,
      dispatch_webhook: toggleWebhook.checked,
    };

    try {
      const response = await fetch("/api/fight", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json();
      finishProgress();

      if (!response.ok || data.ok === false) {
        const errMsg = data.message || (data.errors ? JSON.stringify(data.errors) : "Fight execution failed.");
        showToast(`Simulation halted: ${errMsg}`, "error");
        return;
      }

      state.lastDecision = data;
      renderResults(data);
      showToast("⚡ Duel simulation completed and arbitrated!", "success");

      if (data.webhook_result && data.webhook_result.ok) {
        showToast("📢 Result successfully broadcast to Discord channel!", "success");
      }
    } catch (err) {
      finishProgress();
      console.error("Fight error:", err);
      showToast(`Network or server error during arbitration: ${err.message}`, "error");
    } finally {
      state.isSimulating = false;
      btnSimulate.classList.remove("is-loading");
      btnLabel.textContent = "SIMULATE DUEL";
    }
  });

  function renderCitedText(element, text, sources = []) {
    element.replaceChildren();
    const byNumber = new Map((sources || []).map(source => [String(source.number), source]));
    const pattern = /\[(\d+)\](?:\((https?:[^\s]+?)\))?/g;
    let offset = 0;
    for (const match of String(text || "").matchAll(pattern)) {
      element.append(document.createTextNode(text.slice(offset, match.index)));
      const source = byNumber.get(match[1]);
      if (source && /^https?:\/\//i.test(source.url)) {
        const link = document.createElement("a");
        link.href = source.url;
        link.textContent = `(${match[1]})`;
        link.title = `${source.fighter}: ${source.title}${source.revision ? " — revision " + source.revision : ""}`;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        element.append(link);
      } else element.append(document.createTextNode("[source unavailable]"));
      offset = match.index + match[0].length;
    }
    element.append(document.createTextNode(String(text || "").slice(offset)));
  }

  // RENDER RESULTS TO DOM
  function renderResults(data) {
    resultsSection.classList.remove("hidden");

    const dec = data.decision || {};
    const winner = dec.winner || "Unresolved";
    const confidence = (dec.confidence || "MODERATE").toUpperCase();
    const oddsText = dec.battle_odds_text || "Even Match";

    winnerHeadline.textContent = winner === "Unresolved" ? "ASSESSMENT UNRESOLVED" : `${winner.toUpperCase()} — PREDICTED WINNER`;
    diffBadge.textContent = `DIFFICULTY: ${dec.difficulty || "Unresolved"}`;

    // Parse odds percentages
    const pctMatch = oddsText.match(/(\d+)%.*?(\d+)%/);
    let pctA = null;
    let pctB = null;
    if (pctMatch) {
      pctA = parseInt(pctMatch[1], 10);
      pctB = parseInt(pctMatch[2], 10);
    }
    oddsLabelA.textContent = `${data.contender_a}: ${pctA === null ? "Unresolved" : pctA + "%"}`;
    oddsLabelB.textContent = `${data.contender_b}: ${pctB === null ? "Unresolved" : pctB + "%"}`;
    oddsFillA.style.width = `${pctA || 0}%`;
    oddsFillB.style.width = `${pctB || 0}%`;

    // Fight Cards
    const cardA = dec.contender_a_card || {};
    const cardB = dec.contender_b_card || {};

    resHeaderA.textContent = `🥊 ${data.contender_a.toUpperCase()} — FIGHT CARD`;
    toolsA.textContent = (cardA.key_tools || []).join(" • ") || "Not established by the supplied evidence.";
    winA.textContent = cardA.win_path || "Not established by the supplied evidence.";
    riskA.textContent = cardA.risk || "Not established by the supplied evidence.";

    resHeaderB.textContent = `🥊 ${data.contender_b.toUpperCase()} — FIGHT CARD`;
    toolsB.textContent = (cardB.key_tools || []).join(" • ") || "Not established by the supplied evidence.";
    winB.textContent = cardB.win_path || "Not established by the supplied evidence.";
    riskB.textContent = cardB.risk || "Not established by the supplied evidence.";

    // Quick Verdict
    renderCitedText(quickVerdictText, dec.quick_verdict || "No complete assessment is available.", dec.sources);

    // 3-Phase Play-by-Play
    const sections = dec.sections || {};
    const phases = [
      sections.phase_0 || dec.narrative_phases?.[0] || "Opening assessment unavailable.",
      sections.phase_1 || dec.narrative_phases?.[1] || "Escalation assessment unavailable.",
      sections.phase_2 || dec.narrative_phases?.[2] || "Finishing assessment unavailable."
    ];
    state.currentPhases = phases;
    renderCitedText(phase0Text, phases[0], dec.sources);
    renderCitedText(phase1Text, phases[1], dec.sources);
    renderCitedText(phase2Text, phases[2], dec.sources);
    setFocusedStage(null);

    // Discord Live Preview
    renderDiscordPreview(data, dec);

    // Scroll to results
    resultsSection.scrollIntoView({ behavior: "smooth" });
  }

  function renderDiscordPreview(data, dec) {
    discordEmbedTitle.textContent = dec.display_title || `⚔️ ${data.contender_a.toUpperCase()} VS ${data.contender_b.toUpperCase()}`;
    
    if (data.webhook_result && data.webhook_result.ok) {
      deliveryStatus.textContent = "✅ DISPATCHED TO DISCORD WEBHOOK";
      deliveryStatus.style.color = "var(--emerald-core)";
    } else {
      deliveryStatus.textContent = "READY TO DISPATCH";
      deliveryStatus.style.color = "var(--amber-core)";
    }

    discordEmbedFields.replaceChildren();
    for (const [label, body] of [
      [data.contender_a + " — Fight Card", (dec.contender_a_card?.key_tools || []).slice(0, 3).join(" • ")],
      [data.contender_b + " — Fight Card", (dec.contender_b_card?.key_tools || []).slice(0, 3).join(" • ")],
      ["Quick Verdict", dec.quick_verdict || "Assessment unavailable."],
      ["Battle Assessment", `Predicted winner: ${dec.winner || "Unresolved"}; Difficulty: ${dec.difficulty || "Unresolved"}`]
    ]) {
      const row = document.createElement("div");
      const heading = document.createElement("strong");
      heading.textContent = label + ": ";
      const content = document.createElement("span");
      renderCitedText(content, body, dec.sources);
      row.append(heading, content);
      discordEmbedFields.append(row);
    }

  }

  // RE-DISPATCH BUTTON
  btnReDispatch.addEventListener("click", async () => {
    if (!state.lastDecision) {
      showToast("No active simulation to dispatch!", "error");
      return;
    }

    btnReDispatch.disabled = true;
    btnReDispatch.textContent = "Broadcasting...";

    try {
      const res = await fetch("/api/webhook/dispatch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          decision: state.lastDecision.decision,
          contender_a: state.lastDecision.contender_a,
          contender_b: state.lastDecision.contender_b,
          image_a_url: state.lastDecision.image_a,
          image_b_url: state.lastDecision.image_b,
        }),
      });

      const resData = await res.json();
      if (res.ok && resData.ok) {
        showToast("✅ Successfully dispatched result to Discord Webhook!", "success");
        deliveryStatus.textContent = "✅ DISPATCHED TO DISCORD WEBHOOK";
        deliveryStatus.style.color = "var(--emerald-core)";
      } else {
        showToast(`Discord webhook error: ${resData.error || "Failed to send."}`, "error");
      }
    } catch (e) {
      showToast(`Webhook dispatch failed: ${e.message}`, "error");
    } finally {
      btnReDispatch.disabled = false;
      btnReDispatch.innerHTML = `<span class="dispatch-icon">📢</span><span>Send Result to Discord Webhook</span>`;
    }
  });

});
