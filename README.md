# RECON_X — Recon Automation Tool

أداة ويب محلية (Flask) بطابع Hacker-terminal لأتمتة مراحل الـ recon اللي في الـ workflow بتاعك:
Subdomain enumeration → Merge/Dedupe → Alive hosts → URL discovery → تصنيف البيانات →
JS/Secret scanning → Infra/OSINT → Port discovery → Directory fuzzing → Params & Vuln scan.

36 خطوة موزعة على 11 مرحلة، تغطي تقريبًا كل الأدوات المذكورة في الملف الأصلي.

**Author:** Eng. Islam Mahmoud
**License:** MIT — انظر ملف [LICENSE](LICENSE)

## ⚠ تحذير أمان مهم قبل ما تشغّلها

الأداة دي بتنفذ أوامر shell حقيقية على جهازك (الأدوات المذكورة في `pipeline.json`)، ومفيهاش أي
تسجيل دخول أو مصادقة - دي أداة **local-only** مصممة تشتغل على جهازك إنت بس وتتفتح من
`127.0.0.1` (المتصفح بتاعك على نفس الجهاز).

**متشغّلش الأداة بإعداد يخليها متاحة من برا جهازك** (زي `app.run(host="0.0.0.0")` بدل
`127.0.0.1`، أو عمل port forwarding/reverse proxy ليها على الإنترنت) - أي حد عنده وصول
للشبكة في الحالة دي هيقدر ينفذ أوامر على جهازك من غير أي حماية. لو محتاج تشغّلها من جهاز تاني
في نفس الشبكة بتاعتك، استخدم SSH tunnel أو VPN بدل ما تفتحها مباشرة.

## التشغيل

```bash
cd recon_tool
pip install -r requirements.txt --break-system-packages
python app.py
```

افتح المتصفح على: `http://127.0.0.1:5000`

## طريقة الاستخدام

1. **دخّل الـ target** + أي إعدادات اختيارية (wordlists, resolvers, Chaos API key, GitHub token, ASN).
   تقدر كمان ترفع ملف جاهز (زي قايمة سب-دومينز عندك) من "رفع ملف جاهز".
2. **افحص الأدوات** المنصبة، ودوس "نصّب" جنب أي حاجة ناقصة (go install / apt / pip حسب نوعها).
3. **اختار المراحل**:
   - ابحث عن أداة معينة بالـ search box.
   - "⭐ المسار الموصى به" يختار خطوات آمنة وسريعة نسبيًا.
   - "🛡 غير هجومي فقط" يشيل التحديد عن الخطوات الهجومية (nuclei, sqlmap) من اللي محدد.
   - دوس أيقونة ⚙ جنب أي خطوة عشان تظبط **ملف الإدخال** بتاعها (مثلاً تخلي httpx يشتغل على ملف غير AllSubs.txt)، أو **الـ flags** (checkboxes)، أو extra args حرة.
4. **"⏮ متابعة من Run سابق"**: اختار run قديم من الليستة، وأي خطوات جديدة هتتنفذ في نفس المجلد
   (يعني تقدر تشغل subfinder النهاردة، وبكرة تكمل عليه httpx بدون ما تعيد كل حاجة).
5. دوس **RUN_PIPELINE** وتابع اللوج اللايف.
6. في قسم النتائج:
   - كل ملف معروض مع تصنيفه (فئته).
   - تقدر تختار أي مجموعة ملفات وتدمجهم في ملف واحد بدون تكرار ("🧬 دمج الملفات المحددة").
   - "📄 افتح التقرير الكامل" لملخص HTML بالأرقام.

## تحديثات آخر إصدار

- **تصحيح أغلاط حقيقية في الأوامر**: `puredns` كان بيستخدم `-o` وهي مش flag حقيقية فيه (الصحيح `-w`)،
  `sqlmap` كان فيه `-o` زيادة بتتفسر كـ "تفعيل كل التحسينات" مش مسار ناتج (مسحتها وخليت `--output-dir` بس)،
  و`paramspider` دلوقتي بياخد fallback تلقائي لو نسخة الأداة عندك مش بتدعم `-o`.
- **زر ⏹ STOP**: تقدر توقف أي run شغال في أي وقت - بيقتل العملية وكل العمليات الفرعية بتاعتها
  (مش بس الـ shell wrapper) عشان ما تفضل حاجة شغالة في الخلفية.
- **📁 مكان الحفظ**: حقل اختياري تدخل فيه مسار كامل على جهازك، والنتائج هتتخزن هناك بدل المجلد
  الافتراضي. الـ runs دي بتظهر كمان في "⏮ متابعة من Run سابق".
- **تشخيص تلقائي للأخطاء**: لو خطوة فشلت، الأداة بتحلل الرسالة (command not found, DNS error,
  rate limit, permission denied, invalid flag...) وتقولك سبب محتمل وحل مقترح - في اللوج مباشرة
  وفي بانر "⚠ تحذيرات وتشخيصات" تحت اللوج بعد ما الـ run يخلص.
- **تنبيه الناتج الصغير**: لو أداة خلصت بنجاح لكن ناتجها فاضي أو صغير جدًا بشكل غير متوقع
  (0 سطر، أو ملف JSON فاضي)، هتلاقي تنبيه في نفس البانر يوضح ليه ده يستحق المراجعة.

## تحديثات هذا الإصدار

- **واجهة Hacker-theme** كاملة (terminal/matrix style, glow effects, scanline).
- **أدوات أكتر**: gauplus, hakrawler, gospider, paramspider, github-subdomains, chaos,
  amass (passive+brute منفصلين), ffuf subdomain fuzz, asnmap, whois, gobuster, arjun,
  trufflehog (filesystem), sqlmap، بالإضافة لروابط OSINT + Google/GitHub dorks جاهزة.
- **دمج/تنقية بدون الاعتماد على anew**: كل عمليات الدمج (Subs*.txt → AllSubs.txt،
  WB1/GAU*/KTN1/... → AllURLs.txt) بقت builtin بايثون (أسرع وما يحتاجش تنصيب أداة خارجية)،
  + إمكانية دمج أي ملفات تختارها يدويًا من شاشة النتائج.
- **اختيار ملف الإدخال لكل أداة**: أي خطوة بتاخد ملف كمدخل (httpx, waybackurls, gau, katana,
  naabu, nmap, nuclei, extract_categories...) عندها حقل تقدر تغير فيه اسم الملف، أو
  تجيبه من run سابق عبر "متابعة من Run سابق".
- **خيارات عرض (flags) لكل أداة**: httpx, nuclei, naabu, nmap, ffuf عندهم checkboxes
  لأهم الـ flags بدل ما تكون ثابتة في الكود، + حقل extra args حر لأي حاجة تانية.

## إضافة أدوات جديدة

كل حاجة متحكوم فيها من `pipeline.json` - أضف step جديد بنفس الشكل:

```json
{
  "id": "mytool",
  "tool": "My Tool",
  "bin": "mytool",
  "category": "urls",
  "install": {"type": "go", "pkg": "github.com/.../mytool@latest"},
  "input_param": "input_file",
  "input_default": "AliveSubs.txt",
  "cmd": "mytool -i {outdir}/{input_file} -o {outdir}/out.txt {flags} {extra_args}",
  "produces": "out.txt",
  "flags": [{"label": "Verbose", "flag": "-v", "default": false}]
}
```

وهيظهر أوتوماتيك في الواجهة (checkbox + فحص توفره + حقل input/flags لو موجودين) من غير ما تلمس كود تاني.

## ملاحظات مهمة

- استخدم الأداة دي بس على targets عندك إذن صريح تختبرها (scope بتاع bug bounty program،
  أو أنظمة تمتلكها/عندك تصريح كتابي عليها).
- الخطوات المعلّم عليها "⚠ هجومي" (nuclei, sqlmap) بتبعت طلبات فعلية فيها اختبار ثغرات
  للـ target - استخدمها بحرص وفي السكوب بتاعك بس.
- `secrets_found.txt` نتايجه خام (regex matching) ولازم تتأكد يدويًا إن كل finding حقيقي قبل أي استخدام.
- مراحل زي amass, naabu, nuclei, directory fuzzing, sqlmap ممكن تاخد وقت طويل حسب حجم الـ target.
- أدوات محتاجة API keys (chaos, github-subdomains) بقى ليها حقول مخصصة في الواجهة.
- مصادر OSINT اليدوية (securitytrails, shodan, الخ) ودوركات Google/GitHub بقت متاحة كروابط
  جاهزة في `osint_links.txt` (خطوة "روابط OSINT") - الأداة بتولدها بس مش بتنفذ أي بحث فعلي.

## الكاتب

تم تطوير هذه الأداة بواسطة **Eng. Islam Mahmoud**.

مرخصة تحت [MIT License](LICENSE).
