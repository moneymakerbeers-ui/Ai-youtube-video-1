#!/usr/bin/env python3
"""check_evidence.py - mechanical evidence review of facts.json against the saved snapshots and the narration. Independent of the schema:
a schema can only see that a field is filled in; this opens the files.

  python tools/check_evidence.py --project videos/<slug> [--out review/evidence-check.json] [--strict]

Machine findings (reproducible, no judgement):
  snapshot_missing    an evidence pointer names a snapshot file that is not in the project
  snapshot_changed    the file's sha256 differs from the one recorded when the claim was written
  quote_not_found     the quote is not (after whitespace/quote/dash normalisation) in the snapshot text
  quote_too_short     a "direct" quote of fewer than 6 words cannot carry a claim
  number_untraceable  a number the narration speaks (a scene citing the claim) appears in none of the claim's text, wording or quotes
  claim_unused        a claim no scene cites
  scene_number_no_claim  a scene speaks a number but cites no claim
  source_not_independent a "verified" claim whose sources all share one domain and none is primary/peer-reviewed/institutional
Needs a person (not machine-decidable, never reported as passed):
  model_processed     the quote was only checked against text a model returned: open the URL and confirm the sentence exists there
  interpretation      whether the passage really supports the claim ("supports: direct") is a judgement: the page lists each for a human
Every finding says what to do next. Exit: 0 no errors · 1 errors (--strict also fails on number_untraceable warnings) · 2 bad input.
"""
import argparse, hashlib, json, os, re, sys, time
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_json, write_json  # noqa: E402

NUMWORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100, "thousand": 1000, "million": 1e6, "billion": 1e9}
MULT = {"hundred": 1e2, "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}


def norm(t):
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", t).strip().casefold()


def numbers_in(text):
    """Numeric values mentioned in text: digits (with , and . and unit multipliers) and number words. Small ordinals and 'one' as a pronoun are ignored."""
    vals = set()
    t = text.replace("−", "-")
    for m in re.finditer(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:\s*(hundred|thousand|million|billion|trillion))?", t, re.I):
        v = float(m.group(1).replace(",", ""))
        if m.group(2):
            v *= MULT[m.group(2).lower()]
        vals.add(round(v, 6))
    for m in re.finditer(r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty)(?:\s+(hundred|thousand|million|billion|trillion))?\b", t, re.I):
        v = NUMWORDS[m.group(1).lower()] * (MULT[m.group(2).lower()] if m.group(2) else 1)
        vals.add(float(v))
    return vals


def domain(u):
    try:
        return urlparse(u).netloc.lower().removeprefix("www.")
    except Exception:  # noqa: BLE001
        return ""


def check(P, strict=False):
    facts = read_json(os.path.join(P, "facts.json"))
    scenes = read_json(os.path.join(P, "scenes.json"))["scenes"]
    F = []

    def add(kind, sev, msg, action, **kw):
        F.append({"kind": kind, "severity": sev, "message": msg, "action": action, **kw})

    claims = {c["id"]: c for c in facts.get("claims", [])}
    cited = {cid for s in scenes for cid in s.get("claimIds", [])}
    texts = {}
    for cid, c in claims.items():
        quotes = []
        for k, e in enumerate(c.get("evidence", [])):
            where = f"{cid}.evidence[{k}]"
            snap = os.path.join(P, e["snapshot"])
            if e["sourceIndex"] >= len(c["sources"]):
                add("machine", "error", f"{where}: sourceIndex {e['sourceIndex']} but the claim lists {len(c['sources'])} source(s)", "point sourceIndex at an entry of claim.sources", claimId=cid, check="source_index")
            if not os.path.isfile(snap):
                add("machine", "error", f"{where}: snapshot {e['snapshot']} is not in the project", f"fetch the page again and save its text to {e['snapshot']} (then record its sha256)", claimId=cid, check="snapshot_missing")
                continue
            raw = open(snap, "rb").read()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != e["snapshotSha256"]:
                add("machine", "error", f"{where}: {e['snapshot']} has sha256 {digest[:12]}… but the claim recorded {e['snapshotSha256'][:12]}…", "the file changed after the claim was written: re-read it, re-check the quote, then update snapshotSha256", claimId=cid, check="snapshot_changed")
            body = norm(raw.decode("utf-8", "replace"))
            q = e.get("quote")
            if q:
                quotes.append(q)
                if norm(q) not in body:
                    add("machine", "error", f"{where}: the quote is not in {e['snapshot']}", "copy the sentence exactly as it appears in the snapshot (or fix the claim); a paraphrase is not a quote", claimId=cid, check="quote_not_found", quote=q[:120])
                if e["supports"] == "direct" and len(q.split()) < 6:
                    add("machine", "warn", f"{where}: a 'direct' quote of only {len(q.split())} words", "quote the whole sentence that states the claim", claimId=cid, check="quote_too_short")
            elif e["locator"]["kind"] == "quote":
                add("machine", "error", f"{where}: locator.kind is quote but no quote is given", "add the exact quote", claimId=cid, check="quote_not_found")
            if e.get("snapshotKind", "raw") == "model_processed":
                add("human_needed", "warn", f"{where}: checked only against text a model returned for {c['sources'][min(e['sourceIndex'], len(c['sources']) - 1)].get('url', 'the source')}", "open the URL and confirm the quoted sentence is really on the page", claimId=cid, check="model_processed", quote=(q or "")[:160])
            if e["supports"] == "direct":
                add("human_needed", "info", f"{where}: does this passage state the claim? {e['interpretation']}", "read the quote next to the claim text and confirm it says the same thing", claimId=cid, check="interpretation", quote=(q or "")[:160], claimText=c["text"][:160])
        texts[cid] = " ".join([c["text"], c.get("spokenWording") or ""] + quotes)
        if c["status"] == "verified" and len(c["sources"]) >= 2:
            strong = any(s["type"] in ("primary", "peer_reviewed", "institution") for s in c["sources"])
            doms = {domain(s.get("url", "")) for s in c["sources"] if s.get("url")}
            if not strong and len(doms) < 2:
                add("machine", "error", f"{cid}: marked verified with {len(c['sources'])} sources that share one domain ({', '.join(d for d in doms if d) or 'no URLs'}) and none is primary or institutional", "find an independent source, or set the status to single_source", claimId=cid, check="source_not_independent")
        if cid not in cited:
            add("machine", "info", f"{cid}: no scene cites this claim", "use it in a scene or delete it", claimId=cid, check="claim_unused")
    for s in scenes:
        spoken = numbers_in(s["narration"])
        # a bare "one" is a pronoun more often than a number: only digits and larger number words are traced
        if not spoken:
            continue
        ids = [c for c in s.get("claimIds", []) if c in claims]
        if not ids:
            add("machine", "warn", f"scene {s['id']}: speaks the number(s) {sorted(spoken)[:4]} but cites no claim", "add the claim that supports the number (or reword without it)", sceneId=s["id"], check="scene_number_no_claim")
            continue
        have = set().union(*(numbers_in(texts[c]) for c in ids))
        for v in sorted(spoken - have):
            add("machine", "error" if strict else "warn", f"scene {s['id']}: narration says {v:g} but none of {', '.join(ids)} (text, wording, quotes) contains it", "change the narration to the number the source gives, or add the evidence that contains it", sceneId=s["id"], check="number_untraceable", narration=s["narration"][:140])
    return F


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--out")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    try:
        F = check(a.project, a.strict)
    except (OSError, KeyError, json.JSONDecodeError) as e:
        print(f"cannot read the project: {e}", file=sys.stderr)
        return 2
    for i, f in enumerate(F, 1):
        f["id"] = f"E{i:03d}"
    summ = {"errors": sum(f["severity"] == "error" for f in F), "warnings": sum(f["severity"] == "warn" for f in F), "humanNeeded": sum(f["kind"] == "human_needed" for f in F), "claims": len(read_json(os.path.join(a.project, "facts.json")).get("claims", []))}
    out = a.out or os.path.join(a.project, "review", "evidence-check.json")
    write_json(out, {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "summary": summ, "findings": F})
    for f in F:
        if f["severity"] in ("error", "warn"):
            print(f"{f['severity'].upper():5} {f['id']} [{f['kind']}] {f['message']}\n        -> {f['action']}")
    print(f"evidence: {summ['claims']} claim(s), {summ['errors']} error(s), {summ['warnings']} warning(s), {summ['humanNeeded']} item(s) need a person -> {out}")
    return 1 if summ["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
