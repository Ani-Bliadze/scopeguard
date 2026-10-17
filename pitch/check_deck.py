"""Structural and provenance checks for pitch/ScopeGuard_Pitch.pptx. Does not replace visual review:
it also requires pitch/qa/review.json to contain a completed human/agent visual review bound to this
exact PPTX hash."""

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

PITCH = Path(__file__).parent
ROOT = PITCH.parent
DECK = PITCH / "ScopeGuard_Pitch.pptx"
problems: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(("ok  " if ok else "BAD ") + msg)
    if not ok:
        problems.append(msg)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


check(DECK.exists(), "deck exists")
z = zipfile.ZipFile(DECK)
names = z.namelist()
check(z.testzip() is None, "valid ZIP package")
slides = sorted(n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
notes = sorted(n for n in names if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n))
check(len(slides) == 8, f"exactly 8 slides ({len(slides)})")
check(len(notes) == 8, f"8 notes pages ({len(notes)})")
pres = z.read("ppt/presentation.xml").decode()
m = re.search(r'<p:sldSz cx="(\d+)" cy="(\d+)"', pres)
check(bool(m) and abs(int(m.group(1)) / int(m.group(2)) - 16 / 9) < 0.01, "16:9 slide size")
text_all = ""
for sl in slides:
    xml = z.read(sl).decode()
    runs = re.findall(r"<a:t>([^<]*)</a:t>", xml)
    check(len(runs) >= 3 and "<p:sp>" in xml, f"{sl}: native text and shapes ({len(runs)} runs)")
    text_all += " ".join(runs) + "\n"
for nt in notes:
    t = " ".join(re.findall(r"<a:t>([^<]*)</a:t>", z.read(nt).decode()))
    check(len(t) > 120, f"{nt}: substantive speaker notes ({len(t)} chars)")
    text_all += t + "\n"
charts = [n for n in names if re.fullmatch(r"ppt/charts/chart\d+\.xml", n)]
embeds = [n for n in names if n.startswith("ppt/embeddings/") and n.endswith(".xlsx")]
check(len(charts) >= 1 and len(embeds) >= 1, "native editable chart with embedded data")
check(not re.search(r"lorem|ipsum|\bTODO\b|\bsample data\b|placeholder|\[insert", text_all, re.I), "no placeholder/sample text")
check(not re.search(r"SCOPEGUARD_TEST_SECRET|sk-(proj-)?[A-Za-z0-9_-]{20,}|TEST-PID-\d|customer\d{5}@", text_all),
      "no canary, keys, personal IDs or emails in slide text/notes")
for exact in ["Your AI agent needs an answer. Not your entire database.",
              "The answer was delivered. The extra data was not.",
              "Don't give agents more data. Give them a safer route.",
              "Measured in a synthetic, task-scoped local demo; not a universal safety guarantee."]:
    check(exact.replace("'", "&apos;") in text_all or exact in text_all, f"required text present: {exact[:40]}…")

ev = PITCH / "assets" / "evidence.json"
check(ev.exists(), "evidence snapshot copied into pitch/assets")
if ev.exists():
    snap = json.loads(ev.read_text(encoding="utf-8"))
    current = json.loads((ROOT / "docs" / "demo_results.json").read_text(encoding="utf-8"))
    check(snap["deterministic"] == current, "deck evidence snapshot matches docs/demo_results.json")
for s in ["demo-sales.png", "demo-secret.png", "demo-connection.png"]:
    check((PITCH / "assets" / s).exists(), f"real UI screenshot {s}")
for i in range(1, 9):
    check((PITCH / "qa" / f"slide-{i:02d}.png").exists(), f"render slide-{i:02d}.png")
check((PITCH / "qa" / "montage.png").exists(), "montage.png")
lr = PITCH / "qa" / "layout-report.json"
if lr.exists():
    rep = json.loads(lr.read_text(encoding="utf-8-sig"))
    check(rep["slide_count"] == 8 and rep["wide_16x9"], "PowerPoint render: 8 slides, 16:9")
    check(not rep["findings"], f"PowerPoint layout findings: {rep['findings']}")
else:
    check(False, "layout-report.json present")
rv = PITCH / "qa" / "review.json"
if rv.exists():
    review = json.loads(rv.read_text(encoding="utf-8"))
    check(review.get("pptx_sha256") == sha(DECK), "visual review bound to the current PPTX hash")
    entries = review.get("slides", [])
    check(len(entries) == 8 and all(e.get("status") == "pass" and e.get("checked") for e in entries),
          "all 8 slides visually reviewed and passed")
else:
    check(False, "pitch/qa/review.json present")
print(f"\n{'DECK CHECK PASSED' if not problems else f'{len(problems)} problem(s)'}")
sys.exit(1 if problems else 0)
