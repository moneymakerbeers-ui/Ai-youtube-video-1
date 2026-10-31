#!/usr/bin/env python3
"""ledger.py - the spend gate and the resumable ledger for every PAID call (Higgsfield credits, ElevenLabs characters, licensed music, anything else).

Nothing paid may run unless (1) the creator approved THAT service in state.json (per-service ceilings: credits, characters and dollars are
different currencies), (2) the estimate fits under the remaining ceiling counting what is already spent AND what is in flight, and (3) the
ledger shows no earlier request for the same key that may already have been charged. A resume therefore never repeats a paid job:

  key state        what a resume does
  done             reuse the file; spend nothing                                  (exit 0 with the file)
  submitted(job)   QUERY the provider with the job id; never submit again          (exit 5)
  intent           the process died around the request: it MAY have been charged;
                   look in the provider's history before anything else              (exit 6)
  failed           retry allowed once per key (attempt 2), then a human decides    (exit 0 / 4)

CLI (Claude runs these around every paid MCP/API call; ledger.jsonl is append-only, one JSON object per line):
  ledger.py --project P approve  --service higgsfield --ceiling 15 --unit credits [--quote "..."]
  ledger.py --project P decline  --service elevenlabs
  ledger.py --project P intent   --key higgsfield:hero_01 --service higgsfield --estimate 2.5 [--unit credits]
  ledger.py --project P submitted --key K --job-id J
  ledger.py --project P done     --key K [--actual N] [--file assets/hero_01.png]
  ledger.py --project P failed   --key K [--note "..."]
  ledger.py --project P resolve  --key K (--job-id J | --abandon)        (a human/Claude looked at the provider's history after an interrupted intent)
  ledger.py --project P status                                           (spend per service vs ceiling, in-flight, pending items)
Exit: 0 ok · 2 usage · 4 refused (not approved / over ceiling / retry used up) · 5 already submitted (query the job) · 6 interrupted (check history).
Python: `from ledger import Ledger, PaidCall`.
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_json, write_json  # noqa: E402

UNITS = {"higgsfield": "credits", "elevenlabs": "chars", "music": "usd", "stock": "usd", "compute": "usd"}


class Refused(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


class Ledger:
    def __init__(self, project):
        self.project = project
        self.path = os.path.join(project, "ledger.jsonl")
        self.state_path = os.path.join(project, "state.json")

    # ── state.json (spend gate) ──
    def _state(self):
        if os.path.exists(self.state_path):
            return read_json(self.state_path)
        slug = os.path.basename(os.path.abspath(self.project))
        return {"slug": slug, "idea": "", "stages": {}, "spendGate": {"status": "not_reached", "services": {}}, "ledger": {"higgsfieldCredits": 0, "elevenlabsChars": 0, "otherUsd": 0}, "deliverables": {}, "blocked": []}

    def state(self):
        """state.json as a dict (the default shape when the file does not exist yet)."""
        return self._state()

    def save_state(self, st):
        write_json(self.state_path, st)

    def approve(self, service, ceiling, unit=None, quote=None, note=None):
        cfg = read_json(os.path.join(self.project, "config.json")) if os.path.exists(os.path.join(self.project, "config.json")) else {}
        spend = cfg.get("maxPaidSpend", {})
        if service == "higgsfield" and float(ceiling) > 20 and not spend.get("higgsfieldCeilingRaisedByCreator"):
            raise Refused(4, "a Higgsfield ceiling above 20 credits needs config.json maxPaidSpend.higgsfieldCeilingRaisedByCreator = true (the creator raised it in this run)")
        if service == "higgsfield" and spend.get("higgsfieldCredits") is not None and float(ceiling) > spend["higgsfieldCredits"] and not spend.get("higgsfieldCeilingRaisedByCreator"):
            raise Refused(4, f"the configured Higgsfield budget is {spend['higgsfieldCredits']} credits; approve at most that, or set higgsfieldCeilingRaisedByCreator when the creator raised it")
        st = self._state()
        g = st.setdefault("spendGate", {"status": "not_reached", "services": {}})
        g.setdefault("services", {})[service] = {"approved": True, "ceiling": float(ceiling), "unit": unit or UNITS.get(service, "usd"), **({"quote": quote} if quote else {}), **({"note": note} if note else {})}
        g["status"] = "approved"
        g["approvedAt"] = now()
        write_json(self.state_path, st)
        return g["services"][service]

    def decline(self, service):
        st = self._state()
        g = st.setdefault("spendGate", {"status": "not_reached", "services": {}})
        g.setdefault("services", {})[service] = {"approved": False, "ceiling": 0.0, "unit": UNITS.get(service, "usd")}
        if g.get("status") != "approved":
            g["status"] = "declined"
        write_json(self.state_path, st)

    def service(self, name):
        return (self._state().get("spendGate", {}).get("services", {}) or {}).get(name)

    # ── the append-only log ──
    def entries(self):
        if not os.path.exists(self.path):
            return []
        out = []
        for ln, line in enumerate(open(self.path, encoding="utf-8"), 1):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise Refused(4, f"ledger.jsonl line {ln} is not valid JSON ({e}); fix or restore it before any paid call")
        return out

    def _append(self, e):
        e = {"ts": now(), **e}
        os.makedirs(self.project, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())  # the intent must be on disk BEFORE the request leaves
        self._sync_totals()
        return e

    def last(self, key):
        es = [e for e in self.entries() if e["key"] == key]
        return es[-1] if es else None

    def attempts(self, key):
        return max([e.get("attempt", 1) for e in self.entries() if e["key"] == key] or [0])

    def totals(self, service):
        spent, reserved = 0.0, 0.0
        latest = {}
        for e in self.entries():
            if e["service"] == service:
                latest[e["key"]] = e
        for e in latest.values():
            if e["status"] == "done":
                spent += e.get("actual", e["estimate"])
            elif e["status"] in ("intent", "submitted"):
                reserved += e["estimate"]  # in flight (or interrupted and unresolved): still counts against the ceiling
        return spent, reserved

    def _sync_totals(self):
        if not os.path.exists(self.state_path):
            return
        st = read_json(self.state_path)
        t = lambda s: round(self.totals(s)[0], 3)  # noqa: E731
        st["ledger"] = {"higgsfieldCredits": t("higgsfield"), "elevenlabsChars": t("elevenlabs"), "otherUsd": round(sum(t(s) for s in ("music", "stock", "compute")), 3)}
        write_json(self.state_path, st)

    # ── transitions ──
    def intent(self, key, service, estimate, unit=None):
        """Raises Refused. Returns the new entry, or {'reuse': entry} when the key is already done."""
        last = self.last(key)
        if last and last["status"] == "done":
            return {"reuse": last}
        if last and last["status"] == "submitted":
            raise Refused(5, f"{key} was already submitted as job {last.get('jobId')}: query that job (do NOT submit again); when it finished, `ledger.py done --key {key}`")
        if last and last["status"] == "intent":
            raise Refused(6, f"{key} has an interrupted request (intent at {last['ts']}, no job id): it may already have been charged. Look in the provider's history for it; then `ledger.py resolve --key {key} --job-id <id>` if you find it, or `--abandon` if you are sure it never left")
        svc = self.service(service)
        if not svc or not svc.get("approved"):
            raise Refused(4, f"{service} is not approved at the Spend Gate (state.json spendGate.services.{service}); no paid call may run. Run the free path or ask the creator, then `ledger.py approve --service {service} --ceiling N`")
        unit = unit or svc.get("unit") or UNITS.get(service, "usd")
        if svc.get("unit") and unit != svc["unit"]:
            raise Refused(4, f"{service} is approved in {svc['unit']}, the request is priced in {unit}")
        attempt = (self.attempts(key) or 0) + 1
        if attempt > 2:
            raise Refused(4, f"{key} already failed twice (one retry per asset): a human decides whether to try again")
        spent, reserved = self.totals(service)
        if spent + reserved + float(estimate) > svc["ceiling"] + 1e-9:
            raise Refused(4, f"{key}: {estimate} {unit} would take {service} to {spent + reserved + float(estimate):g} of the approved {svc['ceiling']:g} {unit} ({spent:g} spent, {reserved:g} in flight); stop and report, or the creator raises this service's ceiling")
        return self._append({"key": key, "service": service, "status": "intent", "unit": unit, "estimate": float(estimate), "attempt": attempt})

    def _need(self, key):
        last = self.last(key)
        if not last:
            raise Refused(2, f"no ledger entry for {key}")
        return last

    def submitted(self, key, job_id):
        last = self._need(key)
        return self._append({**{k: last[k] for k in ("key", "service", "unit", "estimate", "attempt")}, "status": "submitted", "jobId": str(job_id)})

    def done(self, key, actual=None, file=None, note=None):
        last = self._need(key)
        e = {**{k: last[k] for k in ("key", "service", "unit", "estimate", "attempt")}, "status": "done"}
        if last.get("jobId"):
            e["jobId"] = last["jobId"]
        if actual is not None:
            e["actual"] = float(actual)
        if file:
            e["file"] = file
        if note:
            e["note"] = note
        return self._append(e)

    def failed(self, key, note=None):
        last = self._need(key)
        e = {**{k: last[k] for k in ("key", "service", "unit", "estimate", "attempt")}, "status": "failed", "actual": 0.0}
        if last.get("jobId"):
            e["jobId"] = last["jobId"]
        if note:
            e["note"] = note
        return self._append(e)

    def resolve(self, key, job_id=None, abandon=False):
        last = self._need(key)
        if last["status"] != "intent":
            raise Refused(2, f"{key} is {last['status']}, not an interrupted intent")
        if abandon:
            return self._append({**{k: last[k] for k in ("key", "service", "unit", "estimate", "attempt")}, "status": "failed", "actual": 0.0, "note": "interrupted intent resolved by hand: the request never left (nothing charged)"})
        return self.submitted(key, job_id)

    def pending(self):
        latest = {}
        for e in self.entries():
            latest[e["key"]] = e
        return [e for e in latest.values() if e["status"] in ("intent", "submitted")]

    def status(self):
        st = self._state().get("spendGate", {}).get("services", {})
        rows = []
        for name in sorted(set(st) | {e["service"] for e in self.entries()}):
            spent, reserved = self.totals(name)
            s = st.get(name, {})
            rows.append({"service": name, "approved": bool(s.get("approved")), "unit": s.get("unit") or UNITS.get(name, "usd"), "ceiling": s.get("ceiling", 0), "spent": round(spent, 3), "inFlight": round(reserved, 3)})
        return rows


class PaidCall:
    """A paid request that cannot be paid twice. submit(key) -> job id (the only call that spends); poll(job_id) -> None while running, else the result;
    fetch(result) -> file path (written into the project); recover(key) -> job id or None (look the interrupted request up in the provider's history)."""

    def __init__(self, project, service, unit=None, sleep=time.sleep, poll_every=2.0, timeout=600.0):
        self.L, self.service, self.unit, self.sleep, self.poll_every, self.timeout = Ledger(project), service, unit, sleep, poll_every, timeout

    def run(self, key, estimate, submit, poll=None, fetch=None, recover=None):
        last = self.L.last(key)
        job = None
        if last and last["status"] == "done":
            return {"reused": True, "file": last.get("file"), "jobId": last.get("jobId")}
        if last and last["status"] == "submitted":
            job = last["jobId"]  # query it; never submit again
        elif last and last["status"] == "intent":
            found = recover(key) if recover else None
            if not found:
                raise Refused(6, f"{key} has an interrupted request and no way to look it up; check the provider's history, then `ledger.py resolve`")
            self.L.resolve(key, job_id=found)
            job = found
        if job is None:
            self.L.intent(key, self.service, estimate, self.unit)
            if os.environ.get("PAID_FAULT") == "after_intent":  # test hook: the process dies after the intent is written, before the request leaves
                raise SystemExit(99)
            try:
                job = submit(key)
            except BaseException as e:  # the request may or may not have left: leave the intent in place (a resume will look it up)
                if getattr(e, "never_sent", False):
                    self.L.failed(key, f"request never left: {e}")
                raise
            self.L.submitted(key, job)
            if os.environ.get("PAID_FAULT") == "after_submit":  # test hook: the process dies after the provider accepted the request
                raise SystemExit(99)
        t0 = time.time()
        res = poll(job) if poll else job
        while res is None:
            if time.time() - t0 > self.timeout:
                raise Refused(5, f"{key}: job {job} is still running after {self.timeout:g}s; query it later (it is recorded as submitted; a resume will not submit again)")
            self.sleep(self.poll_every)
            res = poll(job)
        out = fetch(res) if fetch else None
        self.L.done(key, file=out if isinstance(out, str) else None)
        return {"reused": False, "file": out, "jobId": job}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("approve"); p.add_argument("--service", required=True); p.add_argument("--ceiling", type=float, required=True); p.add_argument("--unit"); p.add_argument("--quote"); p.add_argument("--note")
    p = sub.add_parser("decline"); p.add_argument("--service", required=True)
    p = sub.add_parser("intent"); p.add_argument("--key", required=True); p.add_argument("--service", required=True); p.add_argument("--estimate", type=float, required=True); p.add_argument("--unit")
    p = sub.add_parser("submitted"); p.add_argument("--key", required=True); p.add_argument("--job-id", required=True)
    p = sub.add_parser("done"); p.add_argument("--key", required=True); p.add_argument("--actual", type=float); p.add_argument("--file"); p.add_argument("--note")
    p = sub.add_parser("failed"); p.add_argument("--key", required=True); p.add_argument("--note")
    p = sub.add_parser("resolve"); p.add_argument("--key", required=True); p.add_argument("--job-id"); p.add_argument("--abandon", action="store_true")
    sub.add_parser("status"); sub.add_parser("pending")
    a = ap.parse_args()
    L = Ledger(a.project)
    try:
        if a.cmd == "approve":
            print(json.dumps(L.approve(a.service, a.ceiling, a.unit, a.quote, a.note)))
        elif a.cmd == "decline":
            L.decline(a.service); print(f"{a.service}: declined")
        elif a.cmd == "intent":
            r = L.intent(a.key, a.service, a.estimate, a.unit)
            if "reuse" in r:
                print(f"REUSE {a.key}: already done" + (f" -> {r['reuse'].get('file')}" if r["reuse"].get("file") else "") + "; spend nothing")
            else:
                print(f"OK {a.key}: intent recorded ({a.estimate:g} {r['unit']}, attempt {r['attempt']}); now make the request, then `ledger.py submitted --key {a.key} --job-id <id>`")
        elif a.cmd == "submitted":
            L.submitted(a.key, a.job_id); print(f"{a.key}: submitted as job {a.job_id}")
        elif a.cmd == "done":
            L.done(a.key, a.actual, a.file, a.note); print(f"{a.key}: done")
        elif a.cmd == "failed":
            L.failed(a.key, a.note); print(f"{a.key}: failed (recorded)")
        elif a.cmd == "resolve":
            if not (a.job_id or a.abandon):
                ap.error("resolve needs --job-id or --abandon")
            L.resolve(a.key, a.job_id, a.abandon); print(f"{a.key}: resolved")
        elif a.cmd == "pending":
            for e in L.pending():
                print(f"{e['status']:9} {e['key']}  {e['estimate']:g} {e['unit']}  job={e.get('jobId')}  since {e['ts']}")
        elif a.cmd == "status":
            for r in L.status():
                print(f"{r['service']:12} {'approved' if r['approved'] else 'NOT approved':12} spent {r['spent']:g} / {r['ceiling']:g} {r['unit']}  (in flight {r['inFlight']:g})")
            if not L.status():
                print("no paid service approved or used: the free path only")
    except Refused as e:
        print(f"REFUSED: {e.msg}", file=sys.stderr)
        return e.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
