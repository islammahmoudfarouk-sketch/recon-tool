let currentRunId = null;
let uploadedFiles = [];
// بيتبع مجلد الـ run الحالي عشان أي تشغيل جديد لنفس الـ target يكمل في نفس المجلد
// تلقائيًا بدل ما يعمل مجلد جديد كل مرة تدوس فيها RUN_PIPELINE.
let currentOutdir = null;
let currentOutdirTarget = null;

const logEl = document.getElementById("log");

function appendLog(line) {
  logEl.textContent += line + "\n";
  logEl.scrollTop = logEl.scrollHeight;
}

// ---------- Tool check ----------
async function checkTools() {
  const container = document.getElementById("toolsStatus");
  container.innerHTML = "جاري الفحص...";
  const res = await fetch("/api/check-tools");
  const data = await res.json();
  container.innerHTML = "";
  let okCount = 0;
  data.forEach((item) => {
    const chip = document.createElement("div");
    chip.className = "tool-chip";
    const cls = item.status === "installed" ? "ok" : item.status === "builtin" ? "builtin" : "missing";
    if (cls === "ok" || cls === "builtin") okCount++;
    chip.innerHTML = `<span class="status-dot ${cls}"></span>${item.tool}`;
    if (item.status === "missing") {
      const btn = document.createElement("button");
      btn.textContent = "نصّب";
      btn.className = "btn small";
      btn.onclick = async () => {
        btn.textContent = "...";
        const r = await fetch(`/api/install/${item.id}`, { method: "POST" });
        const j = await r.json();
        alert(j.message);
        checkTools();
      };
      chip.appendChild(btn);
    }
    container.appendChild(chip);
    const dot = document.getElementById(`dot-${item.id}`);
    if (dot) dot.className = `status-dot ${cls}`;
  });
  document.getElementById("toolsSummary").textContent = `${okCount}/${data.length} جاهزة`;
}
document.getElementById("checkBtn").addEventListener("click", checkTools);

// ---------- Phase collapse ----------
document.querySelectorAll(".phase-header").forEach((h) => {
  h.addEventListener("click", (e) => {
    if (e.target.classList.contains("phase-check")) return;
    const phaseId = h.querySelector(".phase-toggle").dataset.phase;
    const stepsDiv = document.getElementById(`steps-${phaseId}`);
    const toggle = h.querySelector(".phase-toggle");
    const collapsed = stepsDiv.style.display === "none";
    stepsDiv.style.display = collapsed ? "flex" : "none";
    toggle.textContent = collapsed ? "▾" : "▸";
  });
});

// ---------- Phase select-all ----------
document.querySelectorAll(".phase-check").forEach((cb) => {
  cb.addEventListener("click", (e) => e.stopPropagation());
  cb.addEventListener("change", () => {
    const phaseId = cb.dataset.phase;
    document
      .querySelectorAll(`.step-check[data-phase="${phaseId}"]`)
      .forEach((s) => { s.checked = cb.checked; });
    updateSelectedCount();
  });
});

document.querySelectorAll(".step-check").forEach((cb) => {
  cb.addEventListener("change", updateSelectedCount);
});

function updateSelectedCount() {
  const n = document.querySelectorAll(".step-check:checked").length;
  document.getElementById("selectedCount").textContent = `${n} خطوة متحددة`;
}

// ---------- Gear toggles (per-step options) ----------
document.querySelectorAll(".gear").forEach((g) => {
  g.addEventListener("click", () => {
    const target = document.getElementById(g.dataset.target);
    target.style.display = target.style.display === "none" ? "flex" : "none";
  });
});

// ---------- Search/filter ----------
document.getElementById("searchBox").addEventListener("input", (e) => {
  const q = e.target.value.trim().toLowerCase();
  document.querySelectorAll(".step-block").forEach((block) => {
    const tool = block.dataset.tool;
    const match = !q || tool.includes(q);
    block.classList.toggle("hidden-step", !match);
    block.classList.toggle("matched", !!q && match);
  });
});

// ---------- Presets ----------
document.getElementById("selectAll").addEventListener("click", () => {
  document.querySelectorAll(".step-check").forEach((s) => (s.checked = true));
  updateSelectedCount();
});
document.getElementById("selectNone").addEventListener("click", () => {
  document.querySelectorAll(".step-check").forEach((s) => (s.checked = false));
  updateSelectedCount();
});
document.getElementById("selectRecommended").addEventListener("click", () => {
  document.querySelectorAll(".step-block").forEach((block) => {
    const cb = block.querySelector(".step-check");
    cb.checked = block.dataset.recommended === "true";
  });
  updateSelectedCount();
});
document.getElementById("selectSafe").addEventListener("click", () => {
  document.querySelectorAll(".step-block").forEach((block) => {
    const cb = block.querySelector(".step-check");
    if (block.dataset.intrusive === "true") cb.checked = false;
  });
  updateSelectedCount();
});

// ---------- File upload ----------
document.getElementById("fileUpload").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/upload", { method: "POST", body: fd });
  const data = await res.json();
  if (data.filename) {
    uploadedFiles.push(data.filename);
    const list = document.getElementById("uploadedList");
    list.textContent = "اتحفظ: " + uploadedFiles.join(", ") + " (هيتحط في مجلد الـ run تلقائي)";
  }
});

// ---------- Previous runs ----------
async function loadPrevRuns() {
  const res = await fetch("/api/runs");
  const runs = await res.json();
  const sel = document.getElementById("prevRuns");
  sel.innerHTML = '<option value="">-- run جديد --</option>';
  runs.forEach((r) => {
    const opt = document.createElement("option");
    opt.value = r.outdir;
    opt.textContent = `${r.target} (${r.name})`;
    sel.appendChild(opt);
  });
}
document.getElementById("prevRuns").addEventListener("change", async (e) => {
  const outdir = e.target.value;
  if (!outdir) {
    // المستخدم رجّع الاختيار لـ "run جديد" يدويًا - يبطّل الاستمرار التلقائي
    currentOutdir = null;
    currentOutdirTarget = null;
    updateFolderIndicator();
    return;
  }
  // اختيار يدوي لـ run قديم بيبقى هو المجلد الحالي كمان
  currentOutdir = outdir;
  currentOutdirTarget = document.getElementById("target").value.trim();
  updateFolderIndicator();

  // هات أسماء الملفات الموجودة في الـ run القديم ده عشان نعرضها كخيارات في datalists
  const res = await fetch(`/api/files-in-dir?dir=${encodeURIComponent(outdir)}`);
  if (!res.ok) return;
  const files = await res.json();
  document.querySelectorAll("datalist[id^='filelist-']").forEach((dl) => {
    dl.innerHTML = "";
    files.forEach((f) => {
      const opt = document.createElement("option");
      opt.value = f.name;
      dl.appendChild(opt);
    });
  });
});
loadPrevRuns();

// ---------- متابعة تلقائية لنفس مجلد الـ run ----------
function updateFolderIndicator() {
  const el = document.getElementById("currentFolderIndicator");
  if (currentOutdir) {
    el.innerHTML = `📂 شغال حاليًا في نفس المجلد: <b>${currentOutdir}</b> (هيفضل يستخدمه لحد ما تدوس "🆕 مجلد جديد")`;
  } else {
    el.textContent = "📂 هيتعمل مجلد جديد مع أول تشغيل";
  }
}

document.getElementById("newFolderBtn").addEventListener("click", () => {
  currentOutdir = null;
  currentOutdirTarget = null;
  document.getElementById("prevRuns").value = "";
  updateFolderIndicator();
});

updateFolderIndicator();

// سنة حقوق الملكية في الفوتر
const yearEl = document.getElementById("copyYear");
if (yearEl) yearEl.textContent = new Date().getFullYear();

// ---------- Run ----------
document.getElementById("runBtn").addEventListener("click", async () => {
  const target = document.getElementById("target").value.trim();
  const steps = Array.from(document.querySelectorAll(".step-check:checked")).map((s) => s.value);

  const options = {
    wordlist_dns: document.getElementById("wordlist_dns").value.trim(),
    wordlist_dir: document.getElementById("wordlist_dir").value.trim(),
    resolvers: document.getElementById("resolvers").value.trim(),
    chaos_api_key: document.getElementById("chaos_api_key").value.trim(),
    github_token: document.getElementById("github_token").value.trim(),
    asn: document.getElementById("asn").value.trim(),
  };

  // extra args لكل خطوة
  document.querySelectorAll(".extra-args-field").forEach((inp) => {
    if (inp.value.trim()) options[`extra_args__${inp.dataset.step}`] = inp.value.trim();
  });

  // input file overrides
  const inputs = {};
  document.querySelectorAll(".input-file-field").forEach((inp) => {
    inputs[inp.dataset.step] = inp.value.trim();
  });

  // flags المختارة لكل خطوة
  const flags_selected = {};
  document.querySelectorAll(".flag-check").forEach((cb) => {
    if (!flags_selected[cb.dataset.step]) flags_selected[cb.dataset.step] = [];
    if (cb.checked) flags_selected[cb.dataset.step].push(cb.value);
  });

  // لو فيه اختيار يدوي من الدروب داون هو الأولوية، وإلا لو عندنا مجلد شغالين فيه
  // بالفعل لنفس الـ target، كمّل فيه تلقائيًا بدل ما تعمل مجلد جديد كل مرة.
  const manualPrevRun = document.getElementById("prevRuns").value || null;
  let reuse_outdir = manualPrevRun;
  if (!reuse_outdir && currentOutdir && currentOutdirTarget === target) {
    reuse_outdir = currentOutdir;
  }
  const save_path = document.getElementById("savePath").value.trim() || null;

  if (!target) { alert("دخّل target الأول"); return; }
  if (!steps.length) { alert("اختار مرحلة واحدة على الأقل"); return; }

  logEl.textContent = "";
  document.getElementById("runState").textContent = " ⏳ جاري البدء...";
  document.getElementById("resultsPanel").style.display = "none";
  document.getElementById("alertsPanel").style.display = "none";
  setRunningUI(true);

  const res = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target, steps, options, inputs, flags_selected, reuse_outdir, save_path, uploaded_files: uploadedFiles }),
  });
  const data = await res.json();
  if (data.error) {
    alert(data.error);
    document.getElementById("runState").textContent = "";
    setRunningUI(false);
    return;
  }

  currentRunId = data.run_id;
  currentOutdir = data.outdir;
  currentOutdirTarget = target;
  updateFolderIndicator();
  document.getElementById("runState").textContent = ` 🟢 شغال (run: ${currentRunId})`;

  const es = new EventSource(`/api/run/${currentRunId}/stream`);
  es.onmessage = (ev) => appendLog(JSON.parse(ev.data));
  es.addEventListener("done", async () => {
    es.close();
    const st = await (await fetch(`/api/run/${currentRunId}/status`)).json();
    document.getElementById("runState").textContent = st.status === "stopped" ? " ⏹ متوقف" : " ✅ انتهى";
    setRunningUI(false);
    renderAlerts(st.diagnostics || [], st.warnings || []);
    loadResults();
    loadPrevRuns();
  });
});

function setRunningUI(running) {
  document.getElementById("runBtn").disabled = running;
  document.getElementById("runBtn").style.opacity = running ? 0.5 : 1;
  document.getElementById("stopBtn").style.display = running ? "inline-block" : "none";
}

document.getElementById("stopBtn").addEventListener("click", async () => {
  if (!currentRunId) return;
  await fetch(`/api/run/${currentRunId}/stop`, { method: "POST" });
  document.getElementById("runState").textContent = " ⏳ جاري الإيقاف...";
});

function renderAlerts(diagnostics, warnings) {
  const panel = document.getElementById("alertsPanel");
  const diagList = document.getElementById("diagList");
  const warnList = document.getElementById("warnList");
  diagList.innerHTML = "";
  warnList.innerHTML = "";

  diagnostics.forEach((d) => {
    const div = document.createElement("div");
    div.className = "alert-item diag";
    div.innerHTML = `<b>❌ ${d.tool} فشلت</b><span class="fix">🔎 ${d.message}</span>`;
    diagList.appendChild(div);
  });
  warnings.forEach((w) => {
    const div = document.createElement("div");
    div.className = "alert-item warn";
    div.innerHTML = `<b>⚠ ${w.tool}</b><span>${w.message}</span>`;
    warnList.appendChild(div);
  });

  panel.style.display = (diagnostics.length || warnings.length) ? "block" : "none";
}

async function loadResults() {
  const res = await fetch(`/api/run/${currentRunId}/files`);
  const files = await res.json();
  const panel = document.getElementById("resultsPanel");
  const list = document.getElementById("fileList");
  list.innerHTML = "";
  files.forEach((f) => {
    const row = document.createElement("div");
    row.className = "file-row";
    row.innerHTML = `
      <input type="checkbox" class="merge-check" value="${f.name}">
      <a href="/api/run/${currentRunId}/download/${f.name}" target="_blank">${f.name}</a>
      <span class="file-cat">${f.category}</span>
      <span class="muted">${f.size}B</span>
    `;
    list.appendChild(row);
  });
  document.getElementById("reportLink").href = `/api/run/${currentRunId}/report`;
  panel.style.display = "block";
}

document.getElementById("mergeBtn").addEventListener("click", async () => {
  if (!currentRunId) { alert("لازم تشغل run الأول"); return; }
  const files = Array.from(document.querySelectorAll(".merge-check:checked")).map((c) => c.value);
  if (!files.length) { alert("اختار ملفات للدمج"); return; }
  const output = document.getElementById("mergeOutputName").value.trim() || "merged_custom.txt";
  const res = await fetch(`/api/run/${currentRunId}/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ files, output }),
  });
  const data = await res.json();
  if (data.error) { alert(data.error); return; }
  document.getElementById("mergeResult").textContent =
    `✅ اتدمجوا في ${data.output} - ${data.unique_lines} سطر فريد`;
  loadResults();
});

// فحص تلقائي أول ما الصفحة تفتح
checkTools();
updateSelectedCount();
