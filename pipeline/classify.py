"""Rule-based classification of supervisor shift notes.

Taxonomy (docs/CLASSIFICATION.md §2) -- 7 categories, 4 carry a reason for extra
hours, 3 do not:

    client_requested   absence_cover   late_handover   equipment_failure
    routine            blank           unclassified

Why rules and not an LLM: the notes are ~50 templated sentences with mild
typos, name-swaps, and a fixed ~20-word isiZulu / Afrikaans vocabulary -- not
open-ended prose. A keyword classifier is deterministic, 100% inspectable,
free, and re-runs on next week's export with no changes. (The brief: a
well-argued "an LLM is the wrong tool here" scores as well as a clever one.)

This module maps note -> category + sub-fields. It does NOT attribute overtime
hours to a cause -- that is a separate step that needs the shift chronology.
"""
from __future__ import annotations

import difflib
import re

import pandas as pd

from .load import Export

CATEGORIES = [
    "client_requested", "absence_cover", "late_handover",
    "equipment_failure", "routine", "blank", "unclassified",
]

DRIVER = {
    "client_requested": "asked_for",
    "absence_cover": "operational_failure",
    "late_handover": "operational_failure",
    "equipment_failure": "operational_failure",
    "routine": "none",
    "blank": "none",
    "unclassified": "none",
}

# --------------------------------------------------------------------------
# multilingual lexicon -- isiZulu / Afrikaans terms mapped to their English
# trigger. Kept explicit so a future export just adds lines, not code.
# --------------------------------------------------------------------------
LEXICON = {
    # isiZulu
    "akezanga": "did not come",          "akafikanga": "did not arrive",
    "namhlanje": "today",                "ngimele yena": "I stood in for them",
    "ngihlale": "I stayed",              "ngasala": "I stayed",
    "akukho lutho": "nothing to report", "ngicela": "please (sort this out)",
    "kuze kube": "until",                "ayikho": "there is none",
    # Afrikaans
    "aflos": "relief",                   "opgedaag": "showed up",
    "moes aanbly": "had to stay on",     "gedek vir": "covered for",
    "geddek vir": "covered for",         "siek gemeld": "reported sick",
    "oorhandiging": "handover",          "gewag vir sleutels": "waited for keys",
    "sleutels": "keys",                  "masjien": "machine",
    "stukkend": "broken",                "met die hand gedoen": "done by hand",
    "ekstra ure": "extra hours",         "klient": "client",
    "niks om te rapporteer nie": "nothing to report", "geen voorvalle": "no incidents",
    "nagskof": "night shift",
}

# --------------------------------------------------------------------------
# patterns. Typo tolerance is baked into the regexes (the template analysis
# showed the typo families: macine/machnie, agn/again, releif/reliief, sek/
# seek gemeld, gedk/geddek, sift/shift, gaurd/guadr, ...).
# --------------------------------------------------------------------------
_FILLER = {
    "", "-", "--", ".", "..", "...", "n/a", "na", "nil", "none", "ntr",
    "ok", "okay", "k", "sharp", "fine", "good", "noted", "no comment",
    "x", "-.", ".-",
}
# "all good" / "all fine" / "all quiet" are RE_ROUTINE (they state the shift was
# uneventful); bare "ok" / "fine" / "sharp" are _FILLER (an acknowledgement).

# fuzzy spellings of a few very common words, applied before the category
# regexes so "reliief"/"machhine"/"hadnover" match. Deliberately narrow.
_FUZZ = [
    (re.compile(r"\bre+l[ie]{1,4}f\b", re.I), "relief"),
    (re.compile(r"\bmac+h*i*e*ne?\b|\bmachien\b|\bmachnie\b", re.I), "machine"),
    (re.compile(r"\bhan+d?ov+er\b|\bhadnover\b|\bhanover\b", re.I), "handover"),
    (re.compile(r"\bcl[ie]{1,3}tn?\b|\bcll?ient\b|\bcli?nt\b", re.I), "client"),
    (re.compile(r"\bcov?r*e+r?d\b|\bcvered\b", re.I), "covered"),
    (re.compile(r"\bnob[od]{2,4}y\b|\bnoody\b", re.I), "nobody"),
    (re.compile(r"\bstk+end\b|\bstukend\b", re.I), "stukkend"),
    (re.compile(r"\bab[se]{1,3}t\b", re.I), "absent"),
    (re.compile(r"\bsi+c*k+\b|\bsicck\b|\bsikc\b|\bsic\b", re.I), "sick"),
    (re.compile(r"\brep+ac?ement\b|\breplacment\b", re.I), "replacement"),
    (re.compile(r"\bsto+d\b", re.I), "stood"),
    (re.compile(r"\bs[ip]{1,3}[ou]se\b|\bspupose\b|\bsuppoes\b", re.I), "suppose"),
    (re.compile(r"\bsi?ll\b(?= on site)", re.I), "still"),
    (re.compile(r"\bo?n+ly\b|\boly\b", re.I), "only"),
    (re.compile(r"\bakez\w*\b", re.I), "akezanga"),
    (re.compile(r"\bdut+y\b", re.I), "duty"),
    (re.compile(r"\bf[ma]{2,4}ily\b", re.I), "family"),
    (re.compile(r"\bp[so]{1,3}ts\b", re.I), "posts"),
]


def _defuzz(text: str) -> str:
    for rx, repl in _FUZZ:
        text = rx.sub(repl, text)
    return text


RE_ROUTINE = re.compile(
    r"nothing to report|no incidents?|no issues?( on site)?|"
    r"quiet (shift|night)|as per normal|as normal|uneventful|"
    r"akukho lutho|niks om te rapporteer nie|geen voorvalle|ayikho|"
    r"all (was )?(quiet|calm|good|fine|clear|well|in order|ok)\b|"
    r"nothing (to note|happened)|routine (shift|patrol)",
    re.I,
)

# equipment / facilities failure
RE_EQUIP = re.compile(
    r"\b(mac[h]?ine|machnie|generator|scrubber|buffer|geyser|gate motor|"
    r"boiler|compressor|lift)\b|"
    r"lift (out of order|broke|not working|stuck)|"
    r"(broke(n| down)?|down again|out of order|kaput|faulty?|fault|failed|"
    r"tripped|load ?shed|no power|power (out|cut|failure))|"
    r"masjien (is )?stukkend|met die hand gedoen|"
    r"(did|done) the floor (by hand|manually)|carried up (the )?stairs|"
    r"manually|by hand",
    re.I,
)

# handover delayed
RE_HANDOVER = re.compile(
    r"handover|hand[- ]?over|oorhandiging|ob ?book( not signed)?|"
    r"waiting on paperwork|waited .{0,15}(for )?(handover|keys|relief to sign)|"
    r"keys? missing|gewag vir sleutels|waited for keys|"
    r"(shift )?handover (late|delayed|not done)|late handover|relieved late",
    re.I,
)

# absence / cover -- the big one
RE_ABSENCE = re.compile(
    r"no[- ]?sh(o|ow|wo|w)\b|no call|no ?show no ?call|"
    r"did ?n.?t (come|pitch|arrive|sho?w|wo?rk|rock up)|"
    r"did not (come|pitch|arrive|show)|nev(er|re) (came|arrived|pitched|showed)|"
    r"nob[od]{2,4}y (came|showed|arrived|pitched)|no[- ]?one (came|showed)|"
    r"no replace?ment( sent)?|no relief\b|"
    r"relief (no ?show|did ?n.?t|nev(er|re)|not (here|there)|only (arrived|came)|"
    r"was suppose?d? to|coming.{0,25}(nob[od]{2,4}y|no ?one))|"
    r"still on site.{0,30}relief|waited (for )?relief|"
    r"next shift .{0,25}(pitch|sho?w|came|arriv|akafikanga)|"
    r"(had to|and|so i|then i) cover(ed)?\b|"
    r"cover(ed|ing) (for |the (post|beat|gate|reception|desk)|\w+ post|"
    r"\w+.?s post|his post|her post)|covered for \w+ (again|agn)|"
    r"covering \w+ (post|beat)|"
    r"stood in for|standing in for|stand in for|"
    r"took .{0,25}(shift|rounds|post|beat) (as well|over|too|also)|"
    r"took over .{0,15}(shift|post|rounds)|"
    r"2 ?p[a-z]{1,5} 1 ?gua?rd|double (post|duty|shift)|worked (str)?through|"
    r"man(ned|ning) (both|two)|both posts|"
    r"(absent|off sick|booked off|at the clinic|on leave|"
    r"family responsib(ility)? leave|compassionate leave|"
    r"family responsibility)|"
    r"akezanga|akafikanga|ngimele yena|ngihlale|ngasala|"
    r"aflos|het nie opgedaag nie|moes aanbly|ge+d+ek vir|"
    r"s[ie]{1,2}k gem[el]{2,4}d|absconded|awol",
    re.I,
)

# client / centre-management requested extra work
RE_CLIENT = re.compile(
    r"\bcl[ie]{1,3}nt\b|\bcll?ient\b|\bcli?nt\b|\bkl[ie]{1,3}nt\b|\bcl[ie]nt\b|"
    r"centre m(gr|gmt|anage)|site manager|"
    r"requested by (centre|site|mgmt|management)|centre manage?ment|"
    r"(cl[ie]{1,3}nt|centre|site mgr|office|mgmt) (as?ked|requested|wanted|"
    r"signed|approved|instructed|said)|"
    r"approved by (office|client|centre|mgmt)|signed off|sign(ed)? by client|"
    r"ok.?d by (centre|client|mgmt)|per client email|"
    r"stock ?take|deep clean|(before|for) the audit|load[- ]?in|"
    r"for the (delivery|event|function|vip|inspection)|event set ?up|"
    r"extra (man|guard|patrol|cover) (on|at|for|requested)|"
    r"additional (cover|patrol|man) (requested|for)|"
    r"klient het ekstra ure gevra|goedgekeur",
    re.I,
)

# the note contradicts itself: client on the surface, no-show underneath
RE_LIE = re.compile(
    r"(real rea[so]{1,3}n|actual(ly)?|truth is|but its|but it.?s|but really).{0,40}"
    r"(no ?show|relief|cover|did ?n.?t (come|pitch))|"
    r"(no ?show|relief no ?show).{0,25}(again|agn)?.{0,15}"
    r"(but )?(client )?(signed|paid|asked)",
    re.I,
)

RE_AUTHORISED_YES = re.compile(
    r"signed off|approved|ok.?d by|authorised|authorized|"
    r"per client email.{0,20}approved|centre (mgmt|management) (ok|approved)|"
    r"they know they pay|signed (for|by)",
    re.I,
)
RE_AUTHORISED_UNCLEAR = re.compile(
    r"don.?t know if .{0,20}(approved|signed|office)|not sure if|"
    r"pending (approval|sign)|await(ing)? (sign|approval)|unconfirmed",
    re.I,
)

RE_REASON_SICK = re.compile(
    r"off sick|booked off( sick)?|at the clinic|s[ie]{1,2}k gem[el]{2,4}d|"
    r"sick ?leave|not well|\bill\b|\bunwell\b|hospital|siek", re.I)
RE_REASON_LEAVE = re.compile(
    r"fam+ily responsib|compassionate leave|on leave|annual leave|"
    r"bereavement|funeral|family responsibility", re.I)
RE_REASON_NOSHOW = re.compile(
    r"no[- ]?show|no call|did ?n.?t (come|pitch|arrive|show)|"
    r"nev(er|re) (came|arrived|pitched)|nob[od]{2,4}y came|"
    r"no (replacement|relief)|control room says relief coming|"
    r"akez|akafikanga|het nie opgedaag|absconded|awol",
    re.I)

# a name token used to pull an absentee surname. Case-insensitive: notes have
# both "covering for Ngcobo" and "gedek vir molefe" / "stood in for zulu".
RE_NAME = re.compile(
    r"(?:covering (?:for )?|stood in for|took |covered for |ge+d+ek vir |"
    r"\bfor |\bvir |stand(?:ing)? in for |worked through, )([a-z]{3,})|"
    r"\bu([a-z]{3,}) akez|"
    r"\b([a-z]{3,}) (?:absent|did ?n|off sick|akez|at the clinic|"
    r"on fam(?:ily|mily)|no ?show|took (?:her|his) (?:rounds|beat))",
    re.I,
)
_NAME_STOPWORDS = {
    "next", "control", "client", "centre", "site", "the", "had", "took",
    "covered", "covering", "double", "relief", "nobody", "someone", "please",
    "worked", "stayed", "shift", "post", "guard", "guuard", "gaurd", "guad",
    "extra", "additional", "duty", "today", "her", "his", "own", "roster",
}


def normalize(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"[.!,~\-\s]+$", "", t)      # trailing punctuation / whitespace
    t = re.sub(r"\s+", " ", t)
    return t


def _absentee(raw: str) -> str:
    low = raw.lower()
    for m in RE_NAME.finditer(raw):
        name = next((g for g in m.groups() if g), None)
        if name and name.lower() not in _NAME_STOPWORDS and len(name) >= 3:
            return name.capitalize()          # "molefe" -> "Molefe"
    if re.search(r"\brelief\b|n[ex]{1,3}t shift|no replacement|aflos|no one|"
                 r"control room", low):
        return "unnamed_relief"
    return ""


def _absence_reason(raw: str) -> str:
    if RE_REASON_SICK.search(raw):
        return "sick"
    if RE_REASON_LEAVE.search(raw):
        return "leave"
    if RE_REASON_NOSHOW.search(raw):
        return "no_show"
    return "unknown"


def _authorised(raw: str) -> str:
    if RE_AUTHORISED_UNCLEAR.search(raw):
        return "unclear"
    if RE_AUTHORISED_YES.search(raw):
        return "yes"
    return "unclear"      # client asked but no sign-off mentioned -> unclear


def classify_note(raw: str) -> dict:
    """note text -> {category, overtime_driver, authorised, absentee,
    absence_reason, surface_vs_driver_conflict, matched_rule}."""
    norm = normalize(raw)
    out = dict(category="unclassified", overtime_driver="none", authorised="n/a",
               absentee="", absence_reason="", surface_vs_driver_conflict=False,
               matched_rule="")

    if norm in _FILLER or re.fullmatch(r"[\W_]*", norm) or len(norm) <= 2:
        out.update(category="blank", matched_rule="filler/empty")
        return out

    raw = _defuzz(raw)          # normalise the worst typos before matching
    client_hit = bool(RE_CLIENT.search(raw))
    if client_hit and (RE_LIE.search(raw) or RE_ABSENCE.search(raw)) and \
            RE_LIE.search(raw):
        out.update(category="absence_cover", overtime_driver="operational_failure",
                   surface_vs_driver_conflict=True, matched_rule="lie",
                   absentee=_absentee(raw), absence_reason=_absence_reason(raw))
        return out

    for name, rx, cat in [
        ("equipment", RE_EQUIP, "equipment_failure"),
        ("absence", RE_ABSENCE, "absence_cover"),
        ("handover", RE_HANDOVER, "late_handover"),
        ("client", RE_CLIENT, "client_requested"),
        ("routine", RE_ROUTINE, "routine"),
    ]:
        if rx.search(raw):
            out.update(category=cat, overtime_driver=DRIVER[cat],
                       matched_rule=name)
            if cat == "absence_cover":
                out["absentee"] = _absentee(raw)
                out["absence_reason"] = _absence_reason(raw)
            elif cat == "client_requested":
                out["authorised"] = _authorised(raw)
            return out

    return out  # unclassified


def _canonical_surnames(export: Export) -> list[str]:
    """Distinct surnames (last name token) from the employee register."""
    names = export.employees["full_name"].dropna()
    return sorted({n.split()[-1] for n in names if n.split()})


def canonicalise_absentee(name: str, surnames: list[str]) -> str:
    """Snap an extracted absentee name to the nearest register surname
    (spelling variants like Mokena / Mokoena collapse). Left as-is if it is
    'unnamed_relief', blank, or not close to any surname."""
    if not name or name == "unnamed_relief":
        return name
    lower = {s.lower(): s for s in surnames}
    if name.lower() in lower:
        return lower[name.lower()]
    hit = difflib.get_close_matches(name.lower(), lower.keys(), n=1, cutoff=0.82)
    return lower[hit[0]] if hit else name


def classify_export(export: Export) -> pd.DataFrame:
    """Internal enriched frame: one row per note with category + sub-fields.
    Absentee names are canonicalised against employees.csv surnames."""
    notes = export.shift_notes.copy()
    notes["note"] = notes["note"].fillna("")
    fields = notes["note"].map(classify_note).apply(pd.Series)
    out = pd.concat([notes[["shift_id", "note"]], fields], axis=1)

    surnames = _canonical_surnames(export)
    out["absentee"] = out["absentee"].map(
        lambda n: canonicalise_absentee(n, surnames)
    )
    return out


def note_classifications_csv(export: Export) -> pd.DataFrame:
    """The submission file: exactly shift_id, category, note -- one row per
    note in shift_notes.csv."""
    enriched = classify_export(export)
    return enriched[["shift_id", "category", "note"]].copy()


if __name__ == "__main__":
    import sys

    from .load import load_export

    exp = load_export(sys.argv[1] if len(sys.argv) > 1 else "data")
    df = classify_export(exp)
    print(f"{len(df)} notes classified\n")
    print(df["category"].value_counts().to_string())
    print(f"\novertime_driver:\n{df['overtime_driver'].value_counts().to_string()}")
    print(f"\nsurface_vs_driver_conflict (notes that lie): "
          f"{int(df['surface_vs_driver_conflict'].sum())}")
    unc = df[df["category"] == "unclassified"]
    print(f"\nunclassified: {len(unc)} ({len(unc) / len(df):.1%})")
    for n in unc["note"].head(25):
        print(f"   {n!r}")
