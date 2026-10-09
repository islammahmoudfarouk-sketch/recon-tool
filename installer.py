"""
RECON_X - installer.py
يفحص توفر أدوات الـ recon على الجهاز، ويحاول تنصيب الناقص منها
تلقائياً لو أمكن (go install / apt) أو يوضح إنها محتاجة تنصيب يدوي.

Author : Eng. Islam Mahmoud
License: انظر ملف LICENSE
"""
import json
import shutil
import subprocess
from pathlib import Path

PIPELINE_PATH = Path(__file__).parent / "pipeline.json"


def load_pipeline():
    with open(PIPELINE_PATH, encoding="utf-8") as f:
        return json.load(f)


def iter_steps(pipeline):
    for phase in pipeline["phases"]:
        for step in phase["steps"]:
            yield phase, step


def check_binary(bin_name: str) -> bool:
    if not bin_name:
        return True
    return shutil.which(bin_name) is not None


def check_all():
    """يرجع status لكل الأدوات: installed / missing / builtin (مفيهاش binary خارجي)."""
    pipeline = load_pipeline()
    results = []
    for phase, step in iter_steps(pipeline):
        if step.get("builtin"):
            results.append({
                "phase": phase["title"],
                "id": step["id"],
                "tool": step["tool"],
                "status": "builtin",
            })
            continue
        bin_name = step.get("bin")
        if bin_name is None:
            # تعتمد على أدوات موجودة بالفعل زي curl/jq (مفروض متاحة على Kali)
            ok = all(check_binary(b) for b in ["curl", "jq"])
            results.append({
                "phase": phase["title"],
                "id": step["id"],
                "tool": step["tool"],
                "status": "installed" if ok else "missing",
                "bin": "curl/jq",
            })
            continue
        ok = check_binary(bin_name)
        results.append({
            "phase": phase["title"],
            "id": step["id"],
            "tool": step["tool"],
            "status": "installed" if ok else "missing",
            "bin": bin_name,
            "install": step.get("install"),
        })
    return results


def install_step(step_id: str, log_cb=None):
    """يحاول تنصيب أداة واحدة بناءً على نوعها، ويرجع (success: bool, message: str)."""
    pipeline = load_pipeline()
    target_step = None
    for _, step in iter_steps(pipeline):
        if step["id"] == step_id:
            target_step = step
            break
    if target_step is None:
        return False, "الخطوة مش موجودة في الـ pipeline"

    install_cfg = target_step.get("install")
    bin_name = target_step.get("bin")

    if check_binary(bin_name):
        return True, f"{target_step['tool']} متنصبة بالفعل"

    if install_cfg is None:
        return True, "الخطوة دي مش محتاجة تنصيب (builtin أو بتستخدم curl/jq)"

    itype = install_cfg["type"]

    def _run(cmd):
        if log_cb:
            log_cb(f"$ {cmd}")
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=600
        )
        if log_cb and proc.stdout:
            log_cb(proc.stdout)
        if log_cb and proc.stderr:
            log_cb(proc.stderr)
        return proc.returncode == 0

    if itype == "go":
        if not check_binary("go"):
            return False, "محتاج Go مثبت الأول (sudo apt install golang-go)"
        pkg = install_cfg["pkg"]
        ok = _run(f"go install -v {pkg}")
        if ok and not check_binary(bin_name):
            # go install بيحط الباينري في GOPATH/bin اللي ممكن مش في PATH
            return False, (
                f"اتنصبت بس مش لاقيها في PATH. "
                f"أضف ده لـ ~/.bashrc: export PATH=$PATH:$(go env GOPATH)/bin"
            )
        return ok, "تم التنصيب عبر go install" if ok else "فشل go install"

    if itype == "apt":
        pkg = install_cfg["pkg"]
        ok = _run(f"sudo apt-get install -y {pkg}")
        return ok, "تم التنصيب عبر apt" if ok else "فشل apt install"

    if itype == "pip":
        pkg = install_cfg["pkg"]
        ok = _run(f"pip install --break-system-packages -U {pkg}")
        return ok, "تم التنصيب عبر pip" if ok else "فشل pip install"

    if itype == "manual":
        return False, install_cfg.get("note", "محتاج تنصيب يدوي")

    return False, "نوع تنصيب غير معروف"
