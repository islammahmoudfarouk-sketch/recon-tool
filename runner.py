"""
RECON_X - runner.py
بينفذ الخطوات المختارة من الـ pipeline بالترتيب، كل خطوة كـ subprocess،
وبيستريم السطور أول بأول عن طريق queue عشان الـ SSE في app.py يقدر يعرضها live.
النتائج بتتحفظ منظمة في runs/<run_id>/ (أو في مكان مخصص لو المستخدم حدده)
بنفس تسمية الملفات المذكورة في الـ workflow.

فيه كمان:
- إيقاف تشغيل أي run شغال (stop/cancel).
- تشخيص تلقائي لأسباب فشل أي خطوة.
- تنبيه لو ناتج خطوة ناجحة جه صغير جدًا بشكل غير متوقع.

Author : Eng. Islam Mahmoud
License: انظر ملف LICENSE
"""
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).parent
PIPELINE_PATH = BASE_DIR / "pipeline.json"
RUNS_DIR = BASE_DIR / "runs"
RUNS_DIR.mkdir(exist_ok=True)
RUNS_INDEX_FILE = RUNS_DIR / "runs_index.json"

# كل الـ runs الشغالة/الخلصانة في الذاكرة (كافي لأداة local single-user)
RUNS = {}


def load_pipeline():
    with open(PIPELINE_PATH, encoding="utf-8") as f:
        return json.load(f)


def find_step(step_id):
    pipeline = load_pipeline()
    for phase in pipeline["phases"]:
        for step in phase["steps"]:
            if step["id"] == step_id:
                return phase, step
    return None, None


def step_category_map():
    """{filename_or_dirname: category} عشان نقدر نصنف الملفات في واجهة النتائج."""
    pipeline = load_pipeline()
    m = {}
    for phase in pipeline["phases"]:
        for step in phase["steps"]:
            prod = step.get("produces", "")
            cat = step.get("category", "other")
            for name in re.split(r"[,/]", prod):
                name = name.strip().split(" ")[0].rstrip("*")
                if name:
                    m[name] = cat
    return m


# ---------- أدوات دمج/دي-دوب عامة (بدون الاعتماد على anew) ----------

def dedupe_merge(files, output_path: Path, log_cb=None):
    """يدمج مجموعة ملفات نصية، يشيل الأسطر الفاضية والمكررة (مع الحفاظ على الترتيب)، ويكتب الناتج."""
    seen = set()
    merged = []
    total_in = 0
    for f in files:
        p = Path(f)
        if not p.exists():
            if log_cb:
                log_cb(f"    [-] {p.name} مش موجود - اتخطى")
            continue
        for line in p.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            total_in += 1
            if line not in seen:
                seen.add(line)
                merged.append(line)
    output_path.write_text("\n".join(merged) + ("\n" if merged else ""))
    if log_cb:
        log_cb(f"    [+] دمج {total_in} سطر من {len(files)} ملف -> {len(merged)} سطر فريد في {output_path.name}")
    return len(merged)


def builtin_merge_glob(outdir: Path, log_cb, glob_pattern: str, output_name: str):
    """يدعم glob حقيقي (Subs*.txt) أو قائمة أسماء مفصولة بفاصلة (WB1.txt,GAU1.txt,...)."""
    if "," in glob_pattern:
        candidates = [outdir / name.strip() for name in glob_pattern.split(",")]
    else:
        candidates = sorted(outdir.glob(glob_pattern))
        candidates = [c for c in candidates if c.name != output_name]

    if not candidates:
        log_cb(f"[!] مفيش ملفات تطابق '{glob_pattern}' - الخطوة اتخطيت")
        return
    log_cb(f"[*] هيدمج {len(candidates)} ملف محتمل...")
    dedupe_merge(candidates, outdir / output_name, log_cb)


# ---------- Builtin steps (مش محتاجة أداة خارجية) ----------

CATEGORY_PATTERNS = {
    "js.txt": r"\.js(\?|$)",
    "php.txt": r"\.php(\?|$)",
    "asp.txt": r"\.asp(\?|$)",
    "aspx.txt": r"\.aspx(\?|$)",
    "jsp.txt": r"\.jsp(\?|$)",
    "api_urls.txt": r"\.(json|xml|graphql|gql)(\?|$)",
    "backend_files.txt": r"\.(php|asp|aspx|jsp|cfm|cgi)(\?|$)",
    "login_flows.txt": r"login|signin|auth|oauth|reset|password",
    "file_uploads.txt": r"upload|file|download|image|media",
    "admin_panels.txt": r"admin|dashboard|internal|manage",
    "sensitive_files.txt": r"\.(env|bak|config|sql|log)(\?|$)",
    "interesting.txt": r"admin|login|signup|redirect|callback|auth|dev|test|beta|debug|staging|url=|r=|u=|goto=|return=|dest=",
    "cloud_leaks.txt": r"aws|s3|bucket|gcp|azure|vault|token|apikey|secret",
    "injection_params.txt": r"=",
}


def builtin_extract(outdir: Path, log_cb, input_file="AllURLs.txt", **_):
    src = outdir / input_file
    if not src.exists():
        log_cb(f"[!] {input_file} مش موجود - شغل مرحلة URL discovery الأول")
        return
    cat_dir = outdir / "categories"
    cat_dir.mkdir(exist_ok=True)
    lines = src.read_text(errors="ignore").splitlines()
    log_cb(f"[*] بيصنف {len(lines)} رابط على {len(CATEGORY_PATTERNS)} فئة...")
    compiled = {name: re.compile(pat, re.I) for name, pat in CATEGORY_PATTERNS.items()}
    buckets = {name: [] for name in CATEGORY_PATTERNS}
    for line in lines:
        for name, rx in compiled.items():
            if rx.search(line):
                buckets[name].append(line)
    for name, items in buckets.items():
        uniq = sorted(set(items))
        (cat_dir / name).write_text("\n".join(uniq) + ("\n" if uniq else ""))
        log_cb(f"    {name}: {len(uniq)}")
    log_cb("[*] تم التصنيف. الملفات في categories/")


def builtin_params(outdir: Path, log_cb, input_file="AllURLs.txt", **_):
    src = outdir / input_file
    if not src.exists():
        log_cb(f"[!] {input_file} مش موجود")
        return
    lines = [l.strip() for l in src.read_text(errors="ignore").splitlines() if "=" in l]
    raw = sorted(set(lines))
    fuzzed = sorted(set(re.sub(r"=[^&]*", "=FUZZ", l) for l in lines))
    (outdir / "params.txt").write_text("\n".join(raw) + ("\n" if raw else ""))
    (outdir / "param_fuzz.txt").write_text("\n".join(fuzzed) + ("\n" if fuzzed else ""))
    log_cb(f"[*] params.txt: {len(raw)} رابط بباراميترز | param_fuzz.txt: {len(fuzzed)} نسخة FUZZ-ready")


SECRET_PATTERNS = {
    "generic_api_key": r"[a-zA-Z0-9_\-]{0,20}api[_-]?key[a-zA-Z0-9_\-]{0,5}['\"]?\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,45}['\"]",
    "generic_secret": r"[a-zA-Z0-9_\-]{0,20}secret[a-zA-Z0-9_\-]{0,5}['\"]?\s*[:=]\s*['\"][a-zA-Z0-9_\-]{8,45}['\"]",
    "generic_token": r"[a-zA-Z0-9_\-]{0,20}token[a-zA-Z0-9_\-]{0,5}['\"]?\s*[:=]\s*['\"][a-zA-Z0-9_\-]{8,45}['\"]",
    "aws_access_key": r"AKIA[0-9A-Z]{16}",
    "aws_secret": r"(?i)aws(.{0,20})?secret(.{0,20})?['\"][0-9a-zA-Z/+]{40}['\"]",
    "slack_token": r"xox[baprs]-[0-9a-zA-Z-]{10,48}",
    "google_api": r"AIza[0-9A-Za-z_\-]{35}",
    "firebase_url": r"[a-z0-9.\-]+\.firebaseio\.com",
    "private_key_block": r"-----BEGIN (RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY-----",
    "bearer_token": r"[Bb]earer\s+[a-zA-Z0-9\-._~+/]{20,}",
}


def builtin_js_secrets(outdir: Path, log_cb, input_file="categories/js.txt", should_stop=None, **_):
    """
    بيجيب أول N ملف JS من categories/js.txt (لو موجود) وبيعمل fetch وفحص regex للأسرار.
    ده fetch بسيط وآمن (GET requests عادية زي المتصفح) - مفيهوش أي استغلال أو تخطي حماية.
    """
    js_list = outdir / input_file
    if not js_list.exists():
        log_cb(f"[!] {input_file} مش موجود - شغل extract_categories الأول")
        return
    urls = [u.strip() for u in js_list.read_text(errors="ignore").splitlines() if u.strip()]
    urls = urls[:200]
    log_cb(f"[*] بيفحص {len(urls)} ملف JS (أول 200) بحثاً عن أسرار محتملة...")

    import urllib.request

    compiled = {name: re.compile(pat) for name, pat in SECRET_PATTERNS.items()}
    findings = []
    for i, url in enumerate(urls):
        if should_stop and should_stop():
            log_cb("[!] اتوقف بناءً على طلب المستخدم")
            break
        if not url.startswith("http"):
            url = "https://" + url
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = resp.read(2_000_000).decode(errors="ignore")
        except Exception:
            continue
        for name, rx in compiled.items():
            for m in rx.finditer(body):
                snippet = m.group(0)
                if len(snippet) > 80:
                    snippet = snippet[:80] + "..."
                findings.append(f"[{name}] {url} -> {snippet}")
        if (i + 1) % 20 == 0:
            log_cb(f"    ...{i+1}/{len(urls)}")

    out_file = outdir / "secrets_found.txt"
    out_file.write_text("\n".join(findings) + ("\n" if findings else ""))
    log_cb(f"[*] لقى {len(findings)} احتمال secret. التفاصيل في secrets_found.txt")


def builtin_osint_links(outdir: Path, log_cb, target="", **_):
    """بيولد روابط جاهزة لمصادر OSINT ودوركات بحث (بدون تنفيذ أي طلبات فعلية - مجرد لينكات)."""
    t = target
    lines = [
        f"# OSINT Sources for {t}",
        f"https://securitytrails.com/domain/{t}",
        f"https://shrewdeye.app/search?q={t}",
        f"https://subdomainfinder.c99.nl/scans/-/{t}",
        f"https://netlas.io/host/{t}",
        f"https://urlscan.io/search/#{t}",
        f"https://otx.alienvault.com/browse/domain/{t}",
        f"https://search.censys.io/search?resource=hosts&q={t}",
        f"https://www.virustotal.com/gui/domain/{t}",
        f"https://crt.sh/?q=%25.{t}",
        f"https://bgp.he.net/dns/{t}",
        f"https://www.shodan.io/search?query=hostname:{t}",
        f"https://search.dnslytics.com/domain/{t}",
        f"https://viewdns.info/reverseip/?host={t}",
        "",
        "# Google Dorks (دور عليها يدوي على Google)",
        f'site:*.{t} intext:"docs.google.com/spreadsheets"',
        f'site:docs.google.com/spreadsheets "{t}"',
        f'site:docs.google.com/spreadsheets "password" "{t}"',
        f'site:docs.google.com/spreadsheets "@{t}"',
        f'site:pastebin.com "{t}"',
        f'site:{t} filetype:env OR filetype:log OR filetype:sql',
        "",
        "# GitHub Dorks (دور عليها يدوي على GitHub Search)",
        f'"{t}" password',
        f'"{t}" api_key',
        f'"{t}" secret',
        f'org:{t}',
        "https://github.com/Proviesec/github-dorks",
        "https://mr-koanti.github.io/github.html",
    ]
    (outdir / "osint_links.txt").write_text("\n".join(lines) + "\n")
    log_cb(f"[*] اتكتب osint_links.txt - {len(lines)} سطر (روابط + دوركات جاهزة للنسخ)")


BUILTIN_HANDLERS = {
    "__builtin_extract__": builtin_extract,
    "__builtin_params__": builtin_params,
    "__builtin_js_secrets__": builtin_js_secrets,
    "__builtin_osint_links__": builtin_osint_links,
}


# ---------- تشخيص الأخطاء التلقائي ----------

ERROR_PATTERNS = [
    (r"command not found|not recognized as an internal", "الأداة مش متنصبة أو مش موجودة في PATH. روح قسم «فحص الأدوات» ونصّبها."),
    (r"no such file or directory", "في ملف أو مسار ناقص (زي wordlist أو ملف input) - تأكد من المسار اللي دخلته واتأكد إنه موجود."),
    (r"permission denied", "مفيش صلاحية كافية للوصول للملف/المجلد - جرب تغيّر صلاحيات المجلد أو مكان الحفظ."),
    (r"unknown flag|unrecognized arguments|flag provided but not defined|invalid option|unknown option", "في flag غير مدعوم في النسخة المنصبة من الأداة عندك - جرب تحدث الأداة أو شيل الـ flag ده من pipeline.json."),
    (r"connection refused|i/o timeout|no route to host|network is unreachable", "في مشكلة اتصال بالـ target أو بالشبكة - تأكد من اتصالك بالإنترنت أو إن الـ target متاح."),
    (r"too many requests|rate limit|429", "السيرفر بيعمل rate limiting - قلل threads/rate الأداة وجرب تاني بعد شوية."),
    (r"could not resolve host|no such host|dns lookup failed|nxdomain", "تعذر حل الدومين (DNS) - تأكد من كتابة الـ target صحيح وإنه موجود فعلاً."),
    (r"unauthorized|401|invalid.{0,10}token|invalid.{0,10}api.?key", "فيه مشكلة في الـ API key/Token اللي دخلته - تأكد إنه صحيح ومفعّل."),
    (r"out of memory|killed\b", "العملية استهلكت موارد كتير وانقتلت - قلل threads أو حجم الـ wordlist."),
    (r"panic:|traceback \(most recent", "الأداة نفسها كرشت (panic/traceback) - احتمال bug في الأداة أو مدخلات غير متوقعة."),
    (r"context deadline exceeded", "انتهى الوقت المسموح للعملية (timeout) - الـ target بطيء أو الشبكة ضعيفة."),
]


def diagnose_failure(tool_name, output_lines, returncode):
    text = "\n".join(output_lines[-60:]).lower()
    for pattern, suggestion in ERROR_PATTERNS:
        if re.search(pattern, text, re.I):
            return suggestion
    if not output_lines:
        return f"الخطوة فشلت (كود خروج {returncode}) بدون أي رسالة - جرب تشغلها يدوي في التيرمينال عشان تشوف التفاصيل."
    return f"الخطوة فشلت (كود خروج {returncode}) - راجع آخر سطور اللوج فوق للتفاصيل."


# ---------- تنبيه الناتج الصغير ----------

MIN_LINES_DEFAULT = 1


def check_small_output(outdir: Path, step):
    """يرجع رسالة تحذير لو ملف الناتج فاضي/صغير جدًا، أو None لو كل حاجة تمام.
    بيتخطى الملفات المتعددة/الـ wildcard/المجلدات لأنه مفيش طريقة مضمونة نقيّمها بسهولة."""
    produces = (step.get("produces") or "").strip()
    if not produces:
        return None

    fname = produces.split(" ")[0].strip()
    if not fname or "*" in fname or fname.endswith("/") or "," in fname:
        return None

    fpath = outdir / fname
    if not fpath.exists():
        return None  # الفشل بالفعل بيتمسك في مكان تاني

    try:
        size = fpath.stat().st_size
    except OSError:
        return None

    if fname.endswith(".json"):
        content = fpath.read_text(errors="ignore").strip()
        if size == 0 or content in ("[]", "{}", "null", ""):
            return f"ناتج {step['tool']} فاضي ({fname}) - الأداة مرجعتش أي نتيجة."
        return None

    if size == 0:
        return f"ناتج {step['tool']} فاضي تمامًا ({fname}, 0 bytes) - محتمل الأداة ماشتغلتش صح أو الـ target مفيهوش نتائج."

    line_count = sum(1 for _ in fpath.open(errors="ignore"))
    if line_count <= MIN_LINES_DEFAULT:
        return f"ناتج {step['tool']} صغير جدًا ({fname}: {line_count} سطر) - تأكد إن ده متوقع ومش علامة على مشكلة."
    return None


# ---------- Run orchestration ----------

def new_run(target: str, step_ids: list, options: dict, inputs: dict = None,
            flags_selected: dict = None, reuse_outdir: str = None, custom_base_dir: str = None):
    run_id = uuid.uuid4().hex[:12]

    if reuse_outdir:
        outdir = Path(reuse_outdir)
        outdir.mkdir(parents=True, exist_ok=True)
    elif custom_base_dir:
        base = Path(custom_base_dir).expanduser()
        base.mkdir(parents=True, exist_ok=True)
        outdir = base / f"{target.replace('/', '_')}_{run_id}"
        outdir.mkdir(parents=True, exist_ok=True)
    else:
        outdir = RUNS_DIR / f"{target.replace('/', '_')}_{run_id}"
        outdir.mkdir(parents=True, exist_ok=True)

    RUNS[run_id] = {
        "id": run_id,
        "target": target,
        "outdir": str(outdir),
        "steps": step_ids,
        "options": options or {},
        "inputs": inputs or {},
        "flags_selected": flags_selected or {},
        "status": "queued",
        "logs": [],
        "q": queue.Queue(),
        "current_step": None,
        "done_steps": [],
        "failed_steps": [],
        "diagnostics": [],   # [{step_id, tool, message}]
        "warnings": [],      # [{step_id, tool, message}]
        "started_at": time.time(),
        "proc": None,
        "cancel_requested": False,
    }

    meta = {"run_id": run_id, "target": target, "outdir": str(outdir), "started_at": RUNS[run_id]["started_at"]}
    (outdir / "run_meta.json").write_text(json.dumps(meta))
    _append_to_runs_index(meta)

    t = threading.Thread(target=_execute_run, args=(run_id,), daemon=True)
    t.start()
    return run_id


def _append_to_runs_index(meta):
    """سجل مركزي لكل الـ runs (حتى اللي في مكان حفظ مخصص) عشان نقدر نعرضهم في ⏮ متابعة من Run سابق."""
    try:
        if RUNS_INDEX_FILE.exists():
            index = json.loads(RUNS_INDEX_FILE.read_text())
        else:
            index = []
    except Exception:
        index = []
    index.append(meta)
    index = index[-200:]  # حد أقصى 200 سجل
    RUNS_INDEX_FILE.write_text(json.dumps(index))


def list_past_runs():
    """يرجع كل الـ runs المسجلة (من أي مكان حفظ) الأحدث أولاً."""
    try:
        index = json.loads(RUNS_INDEX_FILE.read_text()) if RUNS_INDEX_FILE.exists() else []
    except Exception:
        index = []

    # fallback: لو السجل مش موجود (نسخة قديمة) اقرأ من runs/ المحلي
    seen_outdirs = {m.get("outdir") for m in index}
    for d in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not d.is_dir() or str(d) in seen_outdirs:
            continue
        meta_file = d / "run_meta.json"
        if meta_file.exists():
            try:
                index.append(json.loads(meta_file.read_text()))
            except Exception:
                pass

    index.sort(key=lambda m: m.get("started_at", 0), reverse=True)
    out = []
    for m in index[:60]:
        outdir = m.get("outdir", "")
        name = Path(outdir).name if outdir else "?"
        out.append({"outdir": outdir, "name": name, "target": m.get("target", "?"), "run_id": m.get("run_id", name)})
    return out


def _log(run_id, msg):
    run = RUNS[run_id]
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    run["logs"].append(line)
    run["q"].put(line)


def _kill_process_tree(proc):
    """بيقتل العملية وكل العمليات الفرعية بتاعتها (مهم لأن shell=True بيشغل shell
    كـ parent والأداة الفعلية ممكن تفضل شغالة كـ orphan لو قتلنا الـ shell بس)."""
    if proc is None:
        return
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass


def request_stop(run_id):
    run = RUNS.get(run_id)
    if run is None:
        return False
    run["cancel_requested"] = True
    proc = run.get("proc")
    if proc is not None and proc.poll() is None:
        _kill_process_tree(proc)
    return True


def _build_flags_string(step, flags_selected):
    """بيحول اختيارات الـ checkboxes لسلسلة flags فعلية."""
    if not step.get("flags"):
        return ""
    chosen_labels = set(flags_selected or [])
    parts = []
    for f in step["flags"]:
        is_on = f["label"] in chosen_labels if chosen_labels else f.get("default", False)
        if is_on:
            parts.append(f["flag"])
    return " ".join(parts)


def _execute_run(run_id):
    run = RUNS[run_id]
    run["status"] = "running"
    outdir = Path(run["outdir"])
    target = run["target"]
    options = run["options"]
    inputs = run["inputs"]
    flags_selected = run["flags_selected"]

    _log(run_id, f"=== بدء التشغيل للهدف: {target} ===")

    for step_id in run["steps"]:
        if run["cancel_requested"]:
            _log(run_id, "[!] تم إيقاف التشغيل بناءً على طلب المستخدم")
            break

        phase, step = find_step(step_id)
        if step is None:
            _log(run_id, f"[!] خطوة غير معروفة: {step_id}")
            continue

        run["current_step"] = step_id
        _log(run_id, f"--- [{phase['title']}] {step['tool']} ---")

        missing_reqs = []
        for req in step.get("requires", []):
            if not options.get(req):
                missing_reqs.append(req)
        if missing_reqs:
            hint = step.get("requires_hint", "")
            _log(run_id, f"[!] متخطي الخطوة - ناقص: {', '.join(missing_reqs)}. {hint}")
            run["failed_steps"].append(step_id)
            continue

        input_file = inputs.get(step_id) or step.get("input_default", "")

        if step.get("builtin"):
            handler_key = step["cmd"]
            if handler_key == "__builtin_merge_glob__":
                bargs = step.get("builtin_args", {})
                try:
                    builtin_merge_glob(outdir, lambda m: _log(run_id, m),
                                        bargs.get("glob", ""), bargs.get("output", "merged.txt"))
                    run["done_steps"].append(step_id)
                except Exception as e:
                    _log(run_id, f"[!] خطأ: {e}")
                    run["failed_steps"].append(step_id)
                continue

            handler = BUILTIN_HANDLERS.get(handler_key)
            if handler is None:
                _log(run_id, f"[!] builtin handler مش موجود لـ {handler_key}")
                run["failed_steps"].append(step_id)
                continue
            try:
                handler(outdir, lambda m: _log(run_id, m), input_file=input_file, target=target,
                        should_stop=lambda: run["cancel_requested"])
                run["done_steps"].append(step_id)
                warn = check_small_output(outdir, step)
                if warn:
                    run["warnings"].append({"step_id": step_id, "tool": step["tool"], "message": warn})
                    _log(run_id, f"    [!] تحذير: {warn}")
            except Exception as e:
                _log(run_id, f"[!] خطأ: {e}")
                run["failed_steps"].append(step_id)
            continue

        bin_name = step.get("bin")
        if bin_name and shutil.which(bin_name) is None:
            _log(run_id, f"[!] الأداة {bin_name} مش متنصبة - متخطي الخطوة")
            run["failed_steps"].append(step_id)
            continue

        if step.get("input_param") and input_file:
            if not (outdir / input_file).exists():
                _log(run_id, f"[!] ملف الإدخال {input_file} مش موجود في مجلد الـ run - متخطي الخطوة")
                run["failed_steps"].append(step_id)
                continue

        flags_str = _build_flags_string(step, flags_selected.get(step_id))
        extra_args = (options.get(f"extra_args__{step_id}") or "").strip()

        cmd = step["cmd"].format(
            target=target,
            target_escaped=re.escape(target),
            outdir=str(outdir),
            wordlist_dns=options.get("wordlist_dns", ""),
            wordlist_dir=options.get("wordlist_dir", ""),
            resolvers=options.get("resolvers", ""),
            chaos_api_key=options.get("chaos_api_key", ""),
            github_token=options.get("github_token", ""),
            asn=options.get("asn", ""),
            input_file=input_file,
            flags=flags_str,
            extra_args=extra_args,
        )

        step_output_lines = []
        try:
            proc = subprocess.Popen(
                cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, cwd=str(outdir), start_new_session=True,
            )
            run["proc"] = proc
            for line in proc.stdout:
                clean = line.rstrip()
                step_output_lines.append(clean)
                _log(run_id, clean)
                if run["cancel_requested"]:
                    _kill_process_tree(proc)
                    break
            proc.wait()
            run["proc"] = None

            if run["cancel_requested"]:
                _log(run_id, "[!] الخطوة اتوقفت بناءً على طلب المستخدم")
                run["failed_steps"].append(step_id)
                break

            if proc.returncode == 0:
                run["done_steps"].append(step_id)
                warn = check_small_output(outdir, step)
                if warn:
                    run["warnings"].append({"step_id": step_id, "tool": step["tool"], "message": warn})
                    _log(run_id, f"    [!] تحذير: {warn}")
            else:
                diagnosis = diagnose_failure(step["tool"], step_output_lines, proc.returncode)
                _log(run_id, f"[!] الخطوة خرجت بكود {proc.returncode}")
                _log(run_id, f"    🔎 تشخيص: {diagnosis}")
                run["failed_steps"].append(step_id)
                run["diagnostics"].append({"step_id": step_id, "tool": step["tool"], "message": diagnosis})
        except Exception as e:
            run["proc"] = None
            diagnosis = diagnose_failure(step["tool"], step_output_lines + [str(e)], -1)
            _log(run_id, f"[!] فشل تنفيذ الأمر: {e}")
            _log(run_id, f"    🔎 تشخيص: {diagnosis}")
            run["failed_steps"].append(step_id)
            run["diagnostics"].append({"step_id": step_id, "tool": step["tool"], "message": diagnosis})

    run["current_step"] = None
    run["proc"] = None
    run["status"] = "stopped" if run["cancel_requested"] else "finished"
    _log(run_id, "=== تم إيقاف التشغيل ===" if run["cancel_requested"] else "=== انتهى التشغيل ===")
    run["q"].put(None)  # إشارة انتهاء للـ SSE
