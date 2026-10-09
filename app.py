"""
RECON_X - app.py
واجهة ويب محلية (Flask) لأداة أتمتة الـ recon.
شغّلها بـ: python app.py  ثم افتح http://127.0.0.1:5000

Author : Eng. Islam Mahmoud
License: انظر ملف LICENSE
"""
import json
from pathlib import Path

from flask import Flask, jsonify, render_template, request, Response, send_file

import installer
import runner
import report

app = Flask(__name__)

UPLOAD_DIR = Path(__file__).parent / "uploads_staging"
UPLOAD_DIR.mkdir(exist_ok=True)


@app.route("/")
def index():
    pipeline = installer.load_pipeline()
    return render_template("index.html", pipeline=pipeline)


@app.route("/api/check-tools")
def api_check_tools():
    return jsonify(installer.check_all())


@app.route("/api/install/<step_id>", methods=["POST"])
def api_install(step_id):
    logs = []
    ok, msg = installer.install_step(step_id, log_cb=logs.append)
    return jsonify({"ok": ok, "message": msg, "logs": logs})


@app.route("/api/runs")
def api_list_runs():
    """كل الـ runs السابقة (من الديسك) عشان تقدر تكمل عليها أو تختار منها ملف إدخال."""
    return jsonify(runner.list_past_runs())


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """رفع ملف (زي قائمة سب-دومينز جاهزة) هيتحط في الـ run الجديد."""
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "مفيش ملف"}), 400
    dest = UPLOAD_DIR / f.filename
    f.save(dest)
    return jsonify({"filename": f.filename})


@app.route("/api/run", methods=["POST"])
def api_run():
    data = request.get_json(force=True)
    target = (data.get("target") or "").strip()
    step_ids = data.get("steps") or []
    options = data.get("options") or {}
    inputs = data.get("inputs") or {}
    flags_selected = data.get("flags_selected") or {}
    reuse_outdir = data.get("reuse_outdir") or None
    uploaded_files = data.get("uploaded_files") or []
    save_path = (data.get("save_path") or "").strip() or None

    if not target:
        return jsonify({"error": "لازم تدخل target"}), 400
    if not step_ids:
        return jsonify({"error": "لازم تختار مرحلة واحدة على الأقل"}), 400

    if save_path and not reuse_outdir:
        try:
            Path(save_path).expanduser().mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return jsonify({"error": f"مكان الحفظ ده مش متاح للكتابة: {e}"}), 400

    run_id = runner.new_run(target, step_ids, options, inputs=inputs,
                             flags_selected=flags_selected, reuse_outdir=reuse_outdir,
                             custom_base_dir=save_path)

    # انسخ أي ملفات مرفوعة لمجلد الـ run الجديد قبل ما ينفذ الخطوات
    run = runner.RUNS[run_id]
    outdir = Path(run["outdir"])
    for fname in uploaded_files:
        src = UPLOAD_DIR / fname
        if src.exists():
            (outdir / fname).write_bytes(src.read_bytes())

    return jsonify({"run_id": run_id, "outdir": run["outdir"]})


@app.route("/api/run/<run_id>/stream")
def api_stream(run_id):
    run = runner.RUNS.get(run_id)
    if run is None:
        return "run not found", 404

    def gen():
        for line in list(run["logs"]):
            yield f"data: {json.dumps(line)}\n\n"
        if run["status"] == "finished":
            yield "event: done\ndata: {}\n\n"
            return
        while True:
            item = run["q"].get()
            if item is None:
                yield "event: done\ndata: {}\n\n"
                break
            yield f"data: {json.dumps(item)}\n\n"

    return Response(gen(), mimetype="text/event-stream")


@app.route("/api/run/<run_id>/status")
def api_status(run_id):
    run = runner.RUNS.get(run_id)
    if run is None:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "status": run["status"],
        "current_step": run["current_step"],
        "done_steps": run["done_steps"],
        "failed_steps": run["failed_steps"],
        "diagnostics": run["diagnostics"],
        "warnings": run["warnings"],
    })


@app.route("/api/run/<run_id>/stop", methods=["POST"])
def api_stop(run_id):
    ok = runner.request_stop(run_id)
    if not ok:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/files-in-dir")
def api_files_in_dir():
    """يسرد ملفات مجلد run سابق (عشان نعرضها كاقتراحات لحقل input file).
    الأداة دي local-only وبتشتغل بصلاحيات المستخدم نفسه على جهازه، فمسموح نقرا أي مجلد
    يحدده المستخدم بنفسه (زي مكان حفظ مخصص)."""
    dir_param = request.args.get("dir", "")
    if not dir_param:
        return jsonify([])
    target_dir = Path(dir_param).expanduser().resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        return jsonify([])
    cat_map = runner.step_category_map()
    files = []
    for p in sorted(target_dir.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(target_dir))
            files.append({"name": rel, "category": cat_map.get(p.name, "other")})
    return jsonify(files)


@app.route("/api/run/<run_id>/files")
def api_files(run_id):
    run = runner.RUNS.get(run_id)
    if run is None:
        return jsonify({"error": "not found"}), 404
    outdir = Path(run["outdir"])
    cat_map = runner.step_category_map()
    files = []
    for p in sorted(outdir.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(outdir))
            cat = cat_map.get(p.name, cat_map.get(rel, "other"))
            files.append({"name": rel, "size": p.stat().st_size, "category": cat})
    return jsonify(files)


@app.route("/api/run/<run_id>/download/<path:filename>")
def api_download(run_id, filename):
    run = runner.RUNS.get(run_id)
    if run is None:
        return "not found", 404
    outdir = Path(run["outdir"]).resolve()
    fpath = (outdir / filename).resolve()
    if not fpath.exists() or outdir not in fpath.parents:
        return "not found", 404
    return send_file(fpath, as_attachment=True)


@app.route("/api/run/<run_id>/merge", methods=["POST"])
def api_merge(run_id):
    """دمج ملفات مختارة يدوياً (من أي فئة) مع إزالة التكرار، في ملف واحد جديد."""
    run = runner.RUNS.get(run_id)
    if run is None:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True)
    filenames = data.get("files") or []
    output_name = (data.get("output") or "merged_custom.txt").strip()
    if not filenames:
        return jsonify({"error": "اختار ملف واحد على الأقل"}), 400

    outdir = Path(run["outdir"]).resolve()
    full_paths = []
    for name in filenames:
        p = (outdir / name).resolve()
        if outdir in p.parents and p.exists():
            full_paths.append(p)

    logs = []
    count = runner.dedupe_merge(full_paths, outdir / output_name, logs.append)
    return jsonify({"ok": True, "output": output_name, "unique_lines": count, "logs": logs})


@app.route("/api/run/<run_id>/report")
def api_report(run_id):
    run = runner.RUNS.get(run_id)
    if run is None:
        return "not found", 404
    html_report = report.build_report(run)
    report_path = Path(run["outdir"]) / "report.html"
    report_path.write_text(html_report, encoding="utf-8")
    return html_report


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
