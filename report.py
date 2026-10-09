"""
RECON_X - report.py
يبني تقرير HTML مختصر بعد انتهاء الـ run.

Author : Eng. Islam Mahmoud
License: انظر ملف LICENSE
"""
from pathlib import Path
import html


def _count_lines(p: Path) -> int:
    if not p.exists():
        return 0
    return sum(1 for _ in p.open(errors="ignore"))


def build_report(run) -> str:
    outdir = Path(run["outdir"])
    target = run["target"]

    all_subs = _count_lines(outdir / "AllSubs.txt")
    alive = _count_lines(outdir / "AliveSubs.txt")
    all_urls = _count_lines(outdir / "AllURLs.txt")
    secrets = _count_lines(outdir / "secrets_found.txt")
    nuclei = _count_lines(outdir / "nuclei_results.txt")
    ports = _count_lines(outdir / "ports.txt")

    cat_dir = outdir / "categories"
    cat_rows = ""
    if cat_dir.exists():
        for f in sorted(cat_dir.glob("*.txt")):
            n = _count_lines(f)
            if n:
                cat_rows += f"<tr><td>{html.escape(f.name)}</td><td>{n}</td></tr>"

    done = ", ".join(run["done_steps"]) or "-"
    failed = ", ".join(run["failed_steps"]) or "-"

    secrets_preview = ""
    secrets_file = outdir / "secrets_found.txt"
    if secrets_file.exists():
        lines = secrets_file.read_text(errors="ignore").splitlines()[:30]
        secrets_preview = "<br>".join(html.escape(l) for l in lines)

    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<title>تقرير Recon - {html.escape(target)}</title>
<style>
body{{font-family:Tahoma,Arial,sans-serif;background:#0f1115;color:#e6e6e6;padding:24px;max-width:900px;margin:auto}}
h1{{color:#7dd3fc}}
table{{border-collapse:collapse;width:100%;margin:12px 0}}
td,th{{border:1px solid #333;padding:8px 10px;text-align:right}}
.stat{{display:inline-block;background:#1a1d24;border-radius:10px;padding:14px 20px;margin:6px;min-width:120px;text-align:center}}
.stat b{{display:block;font-size:22px;color:#7dd3fc}}
.mono{{font-family:monospace;background:#1a1d24;padding:10px;border-radius:8px;white-space:pre-wrap;font-size:13px}}
</style>
</head>
<body>
<h1>تقرير Recon: {html.escape(target)}</h1>
<p>Run ID: {run['id']}</p>

<div>
<div class="stat"><b>{all_subs}</b>Subdomains</div>
<div class="stat"><b>{alive}</b>Alive Hosts</div>
<div class="stat"><b>{all_urls}</b>URLs</div>
<div class="stat"><b>{ports}</b>Ports</div>
<div class="stat"><b>{secrets}</b>Secrets محتملة</div>
<div class="stat"><b>{nuclei}</b>Nuclei Findings</div>
</div>

<h2>تصنيف الروابط</h2>
<table><tr><th>الفئة</th><th>العدد</th></tr>{cat_rows or '<tr><td colspan=2>لا يوجد</td></tr>'}</table>

<h2>Secrets محتملة (أول 30)</h2>
<div class="mono">{secrets_preview or 'لا يوجد'}</div>

<h2>حالة التنفيذ</h2>
<p><b>تمت بنجاح:</b> {html.escape(done)}</p>
<p><b>فشلت/اتخطت:</b> {html.escape(failed)}</p>

<p style="color:#888;font-size:12px">تنبيه: النتائج دي خام وبتحتاج تحقق يدوي قبل أي استخدام (false positives ممكنة خصوصاً في الـ secrets).</p>

<hr style="border-color:#222;margin-top:24px">
<p style="color:#555;font-size:11px;text-align:center">RECON_X &copy; Eng. Islam Mahmoud</p>
</body>
</html>"""
