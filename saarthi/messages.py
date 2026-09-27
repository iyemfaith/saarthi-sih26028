"""What people actually receive: SMS, IVR call, station board, PA announcement.

Design rules (the invisible pain points):
  * Most rural callers read 12-hour time with a day-part word, not "14:50".
  * "8 in 10" is understood by far more people than "80% confidence".
  * A Devanagari SMS is UCS-2: 70 chars/segment, so the same message costs 2-3x and
    garbles on older handsets. Roman-script Hindi fits one GSM-7 segment (160).
  * Every commercial SMS in India must match a DLT-registered template; variables
    are {#var#}. Headers are 6 characters plus a category suffix.
Boards keep the 24-hour clock Indian Railways boards already use.
"""
import math
from datetime import datetime, timedelta

T0 = datetime(2024, 8, 31)   # stdlib only: this module also runs in the browser (Pyodide)
HEADER = "JK-SARTHI-G"          # operator/circle prefix, 6-char header, -G = government sender
PE_ID = "1101XXXXXXXXXXXXX45"   # Principal Entity ID (placeholder until DLT registration)

GSM7 = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZ"
           "ÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
GSM7_EXT = set("^{}\\[~]|€")


def sms_meta(text):
    if all(c in GSM7 or c in GSM7_EXT for c in text):
        n = sum(2 if c in GSM7_EXT else 1 for c in text)
        seg = 1 if n <= 160 else math.ceil(n / 153)
        return dict(encoding="GSM-7", units=n, per_segment=160 if seg == 1 else 153, segments=seg)
    n = len(text.encode("utf-16-le")) // 2
    seg = 1 if n <= 70 else math.ceil(n / 67)
    return dict(encoding="UCS-2 (Unicode)", units=n, per_segment=70 if seg == 1 else 67, segments=seg)


def hm(t):
    ts = T0 + timedelta(minutes=round(float(t)))
    return ts.hour, ts.minute


def part(h, lang):
    if 4 <= h < 12:
        k = 0
    elif 12 <= h < 16:
        k = 1
    elif 16 <= h < 20:
        k = 2
    else:
        k = 3
    return {"hi": ["सुबह", "दोपहर", "शाम", "रात"], "hing": ["subah", "dopahar", "shaam", "raat"]}[lang][k]


def clock(t, lang="en"):
    h, m = hm(t)
    h12 = h % 12 or 12
    if lang == "en":
        return f"{h12}:{m:02d} {'AM' if h < 12 else 'PM'}"
    return f"{part(h, lang)} {h12}:{m:02d}"


def clock24(t):
    h, m = hm(t)
    return f"{h:02d}:{m:02d}"


def window(lo, hi, lang="en", sep="-"):
    (h0, m0), (h1, m1) = hm(lo), hm(hi)
    if lang == "en":
        a, b = clock(lo, "en"), clock(hi, "en")
        if a[-2:] == b[-2:]:
            a = a[:-3]
        return f"{a}{sep}{b}"
    p0, p1 = part(h0, lang), part(h1, lang)
    a = f"{h0 % 12 or 12}:{m0:02d}"
    b = f"{h1 % 12 or 12}:{m1:02d}"
    if lang == "hi":
        return f"{p0} {a} से {b if p0 == p1 else p1 + ' ' + b} के बीच"
    return f"{p0} {a} se {b if p0 == p1 else p1 + ' ' + b} ke beech"


def confidence(lo, hi, overdue=0):
    w = hi - lo
    if overdue > 15 or w > 60:
        return "low"
    return "high" if w <= 30 else "medium"


CONF = {"en": {"high": "High confidence", "medium": "Medium confidence", "low": "Low confidence"},
        "hi": {"high": "भरोसा: ऊँचा", "medium": "भरोसा: मध्यम", "low": "भरोसा: कम"},
        "hing": {"high": "Bharosa: ooncha", "medium": "Bharosa: madhyam", "low": "Bharosa: kam"}}


def reasons_text(fc, tr, stn_name, lang="en"):
    """Plain-language reasons: model attributions first, then network context."""
    out = []
    names = {"en": stn_name["en"], "hi": stn_name["hi"], "hing": stn_name["en"]}[lang]
    for key, v in fc.get("reasons", []):
        if key == "route" and v < 0:
            out.append({"en": f"It usually makes up about {abs(round(v))} min before {names}.",
                        "hi": f"{names} से पहले यह गाड़ी आम तौर पर लगभग {abs(round(v))} मिनट की भरपाई कर लेती है।",
                        "hing": f"{names} se pehle yeh gaadi aksar {abs(round(v))} min cover kar leti hai."}[lang])
        elif key == "route" and v > 0:
            out.append({"en": f"This stretch usually adds about {round(v)} min.",
                        "hi": f"इस हिस्से में आम तौर पर लगभग {round(v)} मिनट की देरी बढ़ती है।",
                        "hing": f"Is hisse me aksar {round(v)} min deri badhti hai."}[lang])
        elif key == "trend" and v > 0:
            out.append({"en": "It has been losing time at recent stations.",
                        "hi": "पिछले स्टेशनों पर इसकी देरी बढ़ी है।",
                        "hing": "Pichhle stationon par deri badhi hai."}[lang])
        elif key == "trend" and v < 0:
            out.append({"en": "It has been making up time.", "hi": "पिछले स्टेशनों पर इसने समय की भरपाई की है।",
                        "hing": "Pichhle stationon par isne time cover kiya hai."}[lang])
        elif key == "silence" and v > 0:
            out.append({"en": f"No update for {tr.get('age', 0)} min, so the window is wider.",
                        "hi": f"{tr.get('age', 0)} मिनट से कोई सूचना नहीं, इसलिए समय-सीमा चौड़ी है।",
                        "hing": f"{tr.get('age', 0)} min se koi update nahi, isliye samay-seema badi hai."}[lang])
        elif key == "late_recovers" and v < 0:
            out.append({"en": "Late trains usually recover some time on this route.",
                        "hi": "देर से चल रही गाड़ियाँ इस रूट पर कुछ समय पूरा कर लेती हैं।",
                        "hing": "Late gaadiyan is route par kuch time cover kar leti hain."}[lang])
        elif key == "late_recovers" and v > 0:
            out.append({"en": "Trains this late usually lose more time: they give way to others.",
                        "hi": "इतनी देर से चल रही गाड़ियाँ आम तौर पर और पिछड़ जाती हैं, क्योंकि दूसरी गाड़ियों को रास्ता देना पड़ता है।",
                        "hing": "Itni late gaadiyan aksar aur pichhad jaati hain, doosri gaadiyon ko raasta dena padta hai."}[lang])
        elif key == "time_of_day" and v > 0:
            out.append({"en": "This is a busy hour on the route.", "hi": "यह इस रूट पर भीड़ का समय है।",
                        "hing": "Yeh is route par bheed ka samay hai."}[lang])
    if tr.get("rain", 0) >= 5:
        out.append({"en": "Rain along the route.", "hi": "रास्ते में बारिश हो रही है।",
                    "hing": "Raaste me baarish ho rahi hai."}[lang])
    if tr.get("ahead") and tr.get("ahead_gap", 999) <= 25 and (tr.get("ahead_delay") or 0) >= 30:
        out.append({"en": f"Train {tr['ahead']} just ahead is {tr['ahead_delay']} min late.",
                    "hi": f"ठीक आगे चल रही गाड़ी {tr['ahead']} {tr['ahead_delay']} मिनट देर से है।",
                    "hing": f"Aage chal rahi gaadi {tr['ahead']} {tr['ahead_delay']} min late hai."}[lang])
    return out[:3]


def short_name(en, n=16):
    s = en.replace("Express", "Exp").replace("Special", "Spl").replace("Humsafar", "Hmsfr")
    return s if len(s) <= n else s[:n].rstrip() + "."


def late_text(delay, lang):
    d = round(delay)
    if d < 5:
        return {"en": "On time", "hi": "समय पर", "hing": "Samay par"}[lang]
    h, m = divmod(d, 60)
    if lang == "en":
        return f"{d}m late" if d < 60 else f"{h}h{m:02d}m late"
    if lang == "hi":
        return f"{d} मिनट देरी" if d < 60 else f"{h} घंटे {m} मिनट देरी"
    return f"{d} min late" if d < 60 else f"{h} ghante {m} min late"


def gsm_safe(s):
    """Typographic characters silently force UCS-2 (70 chars/segment). Strip them."""
    for x, y in (("\u2013", "-"), ("\u2014", "-"), ("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"'), ("\u2026", "...")):
        s = s.replace(x, y)
    return s


def sms_name(en, n=20):
    s = gsm_safe(en).replace("Express", "Exp").replace("Special", "Spl").replace("SF ", "").replace("Humsafar", "Hmsfr")
    return s if len(s) <= n else s[:n].rstrip(" -.") + "."


def fit(variants):
    """First variant that fits one SMS segment in its own encoding; else the shortest."""
    for v in variants:
        if sms_meta(v)["segments"] == 1:
            return v
    return min(variants, key=len)


def sms_set(kind, ctx):
    """ctx: no, name_en, name_hi, st_en, st_hi, lo, hi, delay, leave_by, role, old_lo, old_hi, pf, prev_st."""
    n = ctx["no"]
    se, sh = gsm_safe(ctx["st_en"]), ctx["st_hi"]
    nm, nm_s = sms_name(ctx["name_en"]), sms_name(ctx["name_en"], 12)

    def win(lo, hi, lg):
        w = window(lo, hi, lg)
        return w if lg == "hi" else gsm_safe(w)

    w = {lg: win(ctx["lo"], ctx["hi"], lg) for lg in ("en", "hi", "hing")}
    k8 = {"en": "8 in 10", "hi": "10 में 8 बार", "hing": "10 me 8 baar"}
    lt = {lg: late_text(ctx["delay"], lg) for lg in ("en", "hi", "hing")}
    lb = {lg: clock(ctx["leave_by"], lg) for lg in ("en", "hi", "hing")} if ctx.get("leave_by") else {"en": "", "hi": "", "hing": ""}
    board = ctx.get("role", "board") == "board"
    pf = ctx.get("pf")
    pf_en = f", PF {pf}" if pf else ""
    out = {}
    if kind == "window":
        act_en = f"Boarding? Leave home by {lb['en']}" if board else f"Receiving? Reach station by {lb['en']}"
        act_en2 = f"Leave by {lb['en']}" if board else f"Reach by {lb['en']}"
        out["en"] = fit([
            f"SAARTHI: {n} {nm} at {se} likely {w['en']} ({k8['en']}). {lt['en']}. {act_en}. We SMS only if it shifts 10+ min. 139",
            f"SAARTHI: {n} {nm} at {se} likely {w['en']} ({k8['en']}). {lt['en']}. {act_en}. Update only if 10+ min change.",
            f"SAARTHI: {n} {nm_s} at {se} likely {w['en']} ({k8['en']}). {lt['en']}. {act_en2}. SMS only if 10+ min change.",
            f"SAARTHI: {n} at {se} likely {w['en']} ({k8['en']}). {lt['en']}. {act_en2}."])
        act_hg = f"Ghar se niklen {lb['hing']} tak" if board else f"Station pahunchen {lb['hing']} tak"
        out["hing"] = fit([
            f"SAARTHI: {n} {nm} {se} par {w['hing']} ({k8['hing']}). {lt['hing']}. {act_hg}. 139",
            f"SAARTHI: {n} {nm_s} {se} par {w['hing']} ({k8['hing']}). {lt['hing']}. {act_hg}.",
            f"SAARTHI: {n} {se} par {w['hing']} ({k8['hing']}). {act_hg}."])
        act_hi = f"घर से निकलें {lb['hi']} तक" if board else f"स्टेशन पहुँचें {lb['hi']} तक"
        out["hi"] = f"सारथी: {n} {sh} पर {w['hi']} ({k8['hi']})। {lt['hi']}। {act_hi}। 139"
        tpl = "SAARTHI: {#var#} {#var#} at {#var#} likely {#var#} ({#var#}). {#var#}. {#var#}. {#var#}"
    elif kind == "change":
        ow = {lg: win(ctx["old_lo"], ctx["old_hi"], lg) for lg in ("en", "hi", "hing")}
        verb = "Leave by" if board else "Reach by"
        out["en"] = fit([
            f"SAARTHI UPDATE: {n} {nm} at {se} now likely {w['en']} (was {ow['en']}). {verb} {lb['en']}. 139",
            f"SAARTHI UPDATE: {n} at {se} now {w['en']} (was {ow['en']}). {verb} {lb['en']}."])
        vh = "Niklen" if board else "Pahunchen"
        out["hing"] = fit([
            f"SAARTHI UPDATE: {n} ab {se} par {w['hing']} (pehle {ow['hing']}). {vh} {lb['hing']} tak.",
            f"SAARTHI UPDATE: {n} {se} {w['hing']} (pehle {ow['hing']})."])
        vhi = "निकलें" if board else "पहुँचें"
        out["hi"] = f"सारथी अपडेट: {n} अब {sh} पर {w['hi']} (पहले {ow['hi']})। {vhi} {lb['hi']} तक।"
        tpl = "SAARTHI UPDATE: {#var#} at {#var#} now likely {#var#} (was {#var#}). {#var#} {#var#}. 139"
    elif kind == "leave":
        out["en"] = fit([f"SAARTHI: Leave now for {se}. {n} {nm} likely {w['en']}. Have a safe journey. 139",
                         f"SAARTHI: Leave now for {se}. {n} likely {w['en']}."])
        out["hing"] = fit([f"SAARTHI: Abhi {se} ke liye niklen. {n} {w['hing']} pahunchegi. Shubh yatra. 139",
                           f"SAARTHI: Abhi {se} ke liye niklen. {n} {w['hing']}."])
        out["hi"] = f"सारथी: अभी {sh} के लिए निकलें। {n} {w['hi']} पहुँचेगी। शुभ यात्रा। 139"
        tpl = "SAARTHI: Leave now for {#var#}. {#var#} {#var#} likely {#var#}. Have a safe journey. 139"
    elif kind == "arriving":
        ps = gsm_safe(ctx["prev_st"])
        out["en"] = fit([f"SAARTHI: {n} {nm} has left {ps}. At {se} {w['en']}{pf_en}. 139",
                         f"SAARTHI: {n} left {ps}. {se} {w['en']}{pf_en}."])
        out["hing"] = fit([f"SAARTHI: {n} {ps} se chal chuki hai. {se} par {w['hing']}{pf_en}.",
                           f"SAARTHI: {n} {ps} se chali. {se} {w['hing']}."])
        pf_hi = f", प्लेटफॉर्म {pf}" if pf else ""
        out["hi"] = f"सारथी: {n} {ctx['prev_st_hi']} से चल चुकी है। {sh} पर {w['hi']}{pf_hi}।"
        tpl = "SAARTHI: {#var#} {#var#} has left {#var#}. At {#var#} {#var#}{#var#}. 139"
    else:
        raise ValueError(kind)
    return dict(kind=kind, header=HEADER, pe_id=PE_ID, template=tpl,
                template_id={"window": "1107172XXXXXXXX0101", "change": "1107172XXXXXXXX0102",
                             "leave": "1107172XXXXXXXX0103", "arriving": "1107172XXXXXXXX0104"}[kind],
                texts={lg: dict(text=tx, **sms_meta(tx)) for lg, tx in out.items()})


def ivr(ctx, lang="hi"):
    """Inbound 139-style call flow and the outbound wake-up call, as spoken prompts."""
    n = " ".join(str(ctx["no"]))
    w = window(ctx["lo"], ctx["hi"], "en" if lang == "en" else "hi")
    if lang == "en":
        flow = [
            dict(who="ivr", say="Namaskar. This is SAARTHI, railway arrival help. हिंदी के लिए 1 दबाएँ. For English, press 2."),
            dict(who="caller", key="2"),
            dict(who="ivr", say="Please enter your five digit train number."),
            dict(who="caller", key=str(ctx["no"])),
            dict(who="ivr", say=f"Train {n}, {ctx['name_en']}. For {ctx['st_en']}, press 1."),
            dict(who="caller", key="1"),
            dict(who="ivr", say=(f"{ctx['name_en']} will most likely reach {ctx['st_en']} between "
                                 f"{w.replace('-', ' and ')}. In 8 out of 10 cases like this, the train arrives inside "
                                 f"this time. It is running {late_text(ctx['delay'], 'en').replace('m late', ' minutes late')}. "
                                 + (f"If you are boarding, leave home by {clock(ctx['leave_by'], 'en')}. " if ctx.get('leave_by') else "")
                                 + "Press 1 to get this on SMS. Press 2 and we will call you 45 minutes before you should leave. "
                                   "Press 9 to hear this again.")),
            dict(who="caller", key="2"),
            dict(who="ivr", say=f"Done. We will call you at {clock(ctx['leave_by'] - 45, 'en')}. Thank you." if ctx.get('leave_by') else "Done. Thank you."),
        ]
        wake = (f"Namaskar. This is your SAARTHI wake-up call. Train {n}, {ctx['name_en']}, is expected at "
                f"{ctx['st_en']} between {w.replace('-', ' and ')}. Please leave in about 45 minutes. Press 1 to snooze 10 minutes.")
    else:
        flow = [
            dict(who="ivr", say="नमस्कार। सारथी रेल आगमन सहायता में आपका स्वागत है। हिंदी के लिए 1 दबाएँ। For English, press 2."),
            dict(who="caller", key="1"),
            dict(who="ivr", say="कृपया अपनी गाड़ी का पाँच अंकों वाला नंबर दबाएँ।"),
            dict(who="caller", key=str(ctx["no"])),
            dict(who="ivr", say=f"गाड़ी संख्या {n}, {ctx['name_hi']}। {ctx['st_hi']} के लिए 1 दबाएँ।"),
            dict(who="caller", key="1"),
            dict(who="ivr", say=(f"{ctx['name_hi']} {ctx['st_hi']} पर सबसे ज़्यादा संभावना {w} पहुँचेगी। "
                                 f"ऐसी स्थिति में 10 में से 8 बार गाड़ी इसी समय के बीच आती है। गाड़ी अभी {late_text(ctx['delay'], 'hi')} से चल रही है। "
                                 + (f"अगर आपको चढ़ना है, तो {clock(ctx['leave_by'], 'hi')} तक घर से निकलें। " if ctx.get('leave_by') else "")
                                 + "यह जानकारी SMS पर पाने के लिए 1 दबाएँ। निकलने से 45 मिनट पहले कॉल पाने के लिए 2 दबाएँ। दोबारा सुनने के लिए 9 दबाएँ।")),
            dict(who="caller", key="2"),
            dict(who="ivr", say=f"हो गया। हम आपको {clock(ctx['leave_by'] - 45, 'hi')} पर कॉल करेंगे। धन्यवाद।" if ctx.get('leave_by') else "हो गया। धन्यवाद।"),
        ]
        wake = (f"नमस्कार, यह सारथी की ओर से जगाने वाली कॉल है। गाड़ी {n}, {ctx['name_hi']}, {ctx['st_hi']} पर {w} पहुँचने की संभावना है। "
                f"कृपया लगभग 45 मिनट में घर से निकलें। 10 मिनट बाद फिर याद दिलाने के लिए 1 दबाएँ।")
    return dict(lang=lang, number="139", flow=flow, wake=wake)


def announcement(ctx):
    """PA script for platform staff, Hindi first then English (Indian station convention)."""
    w24 = f"{clock24(ctx['lo'])} से {clock24(ctx['hi'])} के बीच"
    pf = ctx.get("pf")
    hi = (f"यात्रीगण कृपया ध्यान दें। गाड़ी संख्या {' '.join(str(ctx['no']))}, {ctx['origin_hi']} से चलकर {ctx['dest_hi']} को जाने वाली "
          f"{ctx['name_hi']}, अपने निर्धारित समय से {late_text(ctx['delay'], 'hi')} से चल रही है। इसके {w24} "
          f"{f'प्लेटफॉर्म संख्या {pf} पर ' if pf else ''}आने की संभावना है। आपको हुई असुविधा के लिए हमें खेद है।")
    en = (f"May I have your attention please. Train number {' '.join(str(ctx['no']))}, {ctx['name_en']} from "
          f"{ctx['origin_en']} to {ctx['dest_en']}, is running {late_text(ctx['delay'], 'en').replace('m late', ' minutes late')}. "
          f"It is expected between {clock24(ctx['lo'])} and {clock24(ctx['hi'])}{f' on platform number {pf}' if pf else ''}. "
          "We regret the inconvenience caused.")
    return dict(hi=hi, en=en)
