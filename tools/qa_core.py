"""qa_core.py - shared infrastructure for the QA tools. The one rule: a check may only PASS when its evidence exists.

Statuses
  pass     the measurement ran, covered the whole file, and nothing unplanned was found
  fail     the measurement ran and found something wrong (the detail names it, with times)
  blocked  the measurement could not run or could not be trusted: tool missing, non-zero exit, filter error in the log,
           metadata missing or short, detector self-check failed. A blocked gate is never green.
  warn     a heuristic or a non-gating observation (never counted as a pass of a gate)
  info     context only

Overall: FAILED if any fail, else BLOCKED if any blocked, else PASSED. Exit codes: 0 PASSED, 1 FAILED, 3 BLOCKED, 2 usage error.
"""
import json, os, re, shutil, subprocess, sys, tempfile, time

FATAL_LOG = re.compile(r"\[(error|fatal)\]|(?i:no such filter|unknown filter|invalid argument|error (parsing|initializing|opening|while)|unable to|cannot (find|open|load)|could not (find|open|write)|conversion failed|failed to)")


class Res:
    def __init__(self, cmd, rc, out, err, secs):
        self.cmd, self.rc, self.out, self.err, self.secs = cmd, rc, out, err, secs

    def fatal_lines(self):
        return [l.strip() for l in (self.err or "").splitlines() if FATAL_LOG.search(l)]

    def tail(self, n=3):
        return " | ".join([l.strip() for l in (self.err or "").splitlines() if l.strip()][-n:])


def run_tool(cmd, timeout=None, binary=False):
    """Run a subprocess; never raises on a non-zero exit (the caller must look), raises FileNotFoundError if the tool is absent."""
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    dec = (lambda b: b) if binary else (lambda b: b.decode("utf-8", errors="replace"))
    return Res(cmd, r.returncode, dec(r.stdout), r.stderr.decode("utf-8", errors="replace"), time.time() - t0)


class Report:
    def __init__(self, subject, kind=""):
        self.subject, self.kind, self.checks = subject, kind, []

    def add(self, cid, status, value=None, detail="", evidence=None, heuristic=False):
        assert status in ("pass", "fail", "blocked", "warn", "info"), status
        c = {"id": cid, "status": status, "value": value, "detail": detail}
        if evidence is not None:
            c["evidence"] = evidence
        if heuristic:
            c["heuristic"] = True
        self.checks.append(c)
        return c

    def blocked(self, cid, cause, res=None):
        ev = {"cmd": " ".join(map(str, res.cmd))[:400], "exit": res.rc, "stderr_tail": res.tail(4)} if res is not None else None
        return self.add(cid, "blocked", None, cause, ev)

    def count(self, s):
        return sum(1 for c in self.checks if c["status"] == s)

    @property
    def overall(self):
        if self.count("fail"):
            return "FAILED"
        if self.count("blocked"):
            return "BLOCKED"
        return "PASSED"

    @property
    def exit_code(self):
        return {"PASSED": 0, "FAILED": 1, "BLOCKED": 3}[self.overall]

    def to_json(self, **extra):
        d = {"subject": self.subject, "kind": self.kind, "overall": self.overall, "summary": {s: self.count(s) for s in ("pass", "fail", "blocked", "warn", "info")}, "checks": self.checks}
        d.update(extra)
        return d

    def print(self):
        for c in self.checks:
            v = "" if c["value"] is None else (json.dumps(c["value"]) if isinstance(c["value"], (dict, list)) else str(c["value"]))
            print(f'{c["status"].upper():7} {c["id"]:22} {v[:60]:60} {c["detail"]}')
        s = self.to_json()["summary"]
        print(f'\n{self.overall}: {s["pass"]} pass, {s["fail"]} fail, {s["blocked"]} blocked, {s["warn"]} warn')


# ───────────── intervals ─────────────
def contained(ev, windows, tol):
    """True when the event [a,b] lies inside ONE authorised window (± tol). Overlap is not enough: an event that runs past
    the authorised window is exactly the accidental tail this exists to catch."""
    a, b = ev
    return any(a >= w[0] - tol and b <= w[1] + tol for w in windows)


def clip_to(ev, windows):
    return [(max(ev[0], w[0]), min(ev[1], w[1])) for w in windows if min(ev[1], w[1]) > max(ev[0], w[0])]


def fmt_iv(iv, n=6):
    return [(round(a, 2), round(b, 2)) for a, b in iv[:n]] + ([f"+{len(iv) - n} more"] if len(iv) > n else [])


# ───────────── detectors on ffmpeg logs ─────────────
def parse_black(log):
    return [(float(s), float(e)) for s, e in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)]


def parse_silence(log, dur):
    s = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", log)]
    e = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    return [(max(a, 0.0), e[i] if i < len(e) else dur) for i, a in enumerate(s)]


def parse_series(path, key):
    """metadata=print output → [(pts_time, value)]"""
    out, cur = [], None
    if not os.path.exists(path):
        return out
    for line in open(path, errors="replace"):
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            cur = float(m.group(1))
        m = re.search(re.escape(key) + r"=(-?[\d.]+)", line)
        if m and cur is not None:
            out.append((cur, float(m.group(1))))
    return out


def parse_loudness(log):
    i = log.rfind("Summary:")
    summ = log[i:] if i >= 0 else ""
    mi = re.search(r"I:\s+(-?[\d.]+) LUFS", summ)
    ml = re.search(r"LRA:\s+([\d.]+) LU", summ)
    mp = re.search(r"Peak:\s+(-?[\d.]+) dBFS", summ)
    ts = re.findall(r"\bt:\s*([\d.]+)", log)
    return {"I": float(mi.group(1)) if mi else None, "LRA": float(ml.group(1)) if ml else None, "TP": float(mp.group(1)) if mp else None, "lastT": float(ts[-1]) if ts else None}


# ───────────── motion series: the instrument behind every stillness gate ─────────────
# freezedetect compares the MEAN change of the whole frame, so a label fading in or a small bar growing is below its noise floor
# and the picture counts as "frozen" while it is visibly moving. The gates therefore use the largest change of any block of a
# pooled (area-averaged) frame between consecutive frames: sensitive to small movers, and pooling averages out codec noise.
def motion_chain(crop="", fpsf="", pool=96, sink="motion.txt"):
    return f"{crop}{fpsf}scale={pool}:-2:flags=area,format=gray,tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YMAX:file={sink}"


def diffs_by_frame(series, fps):
    """[(pts_time, ymax)] -> {frame_index: change from the previous frame}. tblend emits from the 2nd frame on."""
    return {int(round(t * fps)): v for t, v in series}


def still_runs(diffs, fps, T, min_s, n_frames=None):
    """Spans [a, b] seconds in which consecutive frames differ by <= T everywhere. A run of n quiet diffs is n+1 identical frames."""
    out, ks, i = [], sorted(diffs), 0
    while i < len(ks):
        if diffs[ks[i]] <= T:
            j = i
            while j + 1 < len(ks) and ks[j + 1] == ks[j] + 1 and diffs[ks[j + 1]] <= T:
                j += 1
            a, b = (ks[i] - 1) / fps, (ks[j] + 1) / fps
            if b - a >= min_s:
                out.append((a, b))
            i = j + 1
        else:
            i += 1
    return out


# ───────────── detector self-check: prove the instruments work on known events before trusting them on the file ─────────────
_SELF = {}


def selfcheck(th):
    """Synthesise 4 s of video with KNOWN events (1 s black; 1 s test-pattern motion; 1 s static colour; 1 s static colour with a
    24-px square crawling 1 px/frame) and 3 s of audio (tone, 1 s digital silence, tone), and require every detector to find
    exactly those. The crawling square is the case freezedetect misses, so the stillness instrument is held to it. Cached per
    process. Returns (ok, problems)."""
    key = ("v2", json.dumps(th.get("freeze"), sort_keys=True), json.dumps(th.get("black"), sort_keys=True), json.dumps(th.get("silence"), sort_keys=True))
    if key in _SELF:
        return _SELF[key]
    problems = []
    d = tempfile.mkdtemp(prefix="qa-self-")
    try:
        v = os.path.join(d, "v.mkv")
        fc = ("color=c=black:s=320x180:r=30:d=1,format=yuv420p[a];testsrc2=s=320x180:r=30:d=1,format=yuv420p[b];"
              "color=c=0x336699:s=320x180:r=30:d=1,format=yuv420p[c];"
              "color=c=0x336699:s=320x180:r=30:d=1[bg];color=c=white:s=24x24:r=30:d=1[sq];[bg][sq]overlay=x='40+n':y=70:format=rgb,format=yuv420p[e];"
              "[a][b][c][e]concat=n=4:v=1:a=0[v]")
        r1 = run_tool(["ffmpeg", "-v", "error", "-y", "-filter_complex", fc, "-map", "[v]", "-c:v", "ffv1", v])
        au = os.path.join(d, "a.wav")
        r2 = run_tool(["ffmpeg", "-v", "error", "-y", "-filter_complex", "sine=f=440:d=1,volume=0.3,aformat=sample_rates=48000:channel_layouts=mono[t1];anullsrc=r=48000:cl=mono,atrim=0:1[t2];sine=f=440:d=1,volume=0.3,aformat=sample_rates=48000:channel_layouts=mono[t3];[t1][t2][t3]concat=n=3:v=0:a=1[aa]", "-map", "[aa]", "-c:a", "pcm_s16le", au])
        if r1.rc or r2.rc:
            problems.append(f"could not synthesise the self-check media: {(r1.tail() if r1.rc else r2.tail())}")
        else:
            lu, mo = os.path.join(d, "lu"), os.path.join(d, "mo")
            rb = run_tool(["ffmpeg", "-nostdin", "-loglevel", "level+info", "-i", v, "-vf", f"blackdetect=d=0.05:pix_th={th['black']['pixTh']},signalstats,metadata=print:key=lavfi.signalstats.YAVG:file={lu}", "-an", "-f", "null", "-"])
            if rb.rc or rb.fatal_lines():
                problems.append(f"video analysis filters failed on known media: {rb.tail()}")
            else:
                b = parse_black(rb.err)
                if not (len(b) == 1 and abs(b[0][0]) < 0.1 and abs(b[0][1] - 1.0) < 0.15):
                    problems.append(f"blackdetect found {b} on media with exactly one black second at 0-1 s")
                ys = parse_series(lu, "lavfi.signalstats.YAVG")
                if len(ys) != 120:
                    problems.append(f"signalstats covered {len(ys)} of 120 frames")
            rm = run_tool(["ffmpeg", "-nostdin", "-loglevel", "level+info", "-i", v, "-vf", motion_chain("", "", th["freeze"]["pool"], mo), "-an", "-f", "null", "-"])
            if rm.rc or rm.fatal_lines():
                problems.append(f"the stillness instrument failed on known media: {rm.tail()}")
            else:
                dm = diffs_by_frame(parse_series(mo, "lavfi.signalstats.YMAX"), 30.0)
                T = th["freeze"]["maxDiffLevels"]
                seg = lambda a, b: [dm[k] for k in range(a, b) if k in dm]  # noqa: E731
                still, moving, crawl = seg(65, 89), seg(35, 59), seg(95, 119)
                if len(dm) != 119:
                    problems.append(f"the stillness instrument covered {len(dm)} of 119 frame pairs")
                if not still or sum(1 for x in still if x <= T) < 0.95 * len(still):
                    problems.append(f"the stillness instrument saw motion in a static second (changes {sorted(still)[-3:]})")
                if not moving or sum(1 for x in moving if x > T) < 0.9 * len(moving):
                    problems.append("the stillness instrument missed test-pattern motion")
                if not crawl or sum(1 for x in crawl if x > T) < 0.9 * len(crawl):
                    problems.append(f"the stillness instrument missed a 24-px square crawling 1 px/frame (changes {sorted(crawl)[:3]}, threshold {T})")
            rs = run_tool(["ffmpeg", "-nostdin", "-loglevel", "level+verbose", "-i", au, "-af", f"silencedetect=n={th['silence']['noiseDb']}dB:d=0.3,ebur128=peak=true:framelog=verbose", "-f", "null", "-"])
            if rs.rc or rs.fatal_lines():
                problems.append(f"audio analysis filters failed on known media: {rs.tail()}")
            else:
                s_ev = parse_silence(rs.err, 3.0)
                if not (len(s_ev) == 1 and abs(s_ev[0][0] - 1.0) < 0.1 and abs(s_ev[0][1] - 2.0) < 0.1):
                    problems.append(f"silencedetect found {s_ev} on audio with exactly one silent second at 1-2 s")
                L = parse_loudness(rs.err)
                if L["I"] is None or L["TP"] is None or L["lastT"] is None or L["lastT"] < 2.5:
                    problems.append(f"ebur128 summary unparsable or short: {L}")
    except FileNotFoundError as e:
        problems.append(f"tool missing: {e}")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    _SELF[key] = (not problems, problems)
    return _SELF[key]
