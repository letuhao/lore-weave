"""F3 stage 2 — the FE door scan.

F10: four structured editors existed and were imported, but the ONE condition rendering their entry
(`blocking && completed && decision==='pending'`) was false for four of six atom kinds. They were
dead UI. No test caught it because every editor test mounted the editor DIRECTLY with a fabricated
prop, so the gate was never executed.

Reachability-by-import therefore proves nothing. Three things do:
  1. a component with ZERO inbound mount (JSX *or* panel-catalog registration) is dead by
     construction — no predicate needed;
  2. a component with exactly ONE inbound parent has a single point of failure, and that one guard
     is what F10 was;
  3. for those, whether ANY test mounts the PARENT. If every test mounts the child directly, the
     gate is unexercised — the exact F10 setup, sitting there right now.

Read-only. Reports; does not judge.
"""
import collections
import pathlib
import re

ROOT = pathlib.Path("d:/Works/source/lore-weave/frontend/src")
FEATURES = ROOT / "features"

NAME_HINT = re.compile(r"(Editor|Panel|Dialog|Drawer|Modal|Form|Review|Picker|Manager|List|View)$")


def is_test(p: pathlib.Path) -> bool:
    return "__tests__" in p.parts or p.name.endswith((".test.tsx", ".test.ts"))


files = [p for p in FEATURES.rglob("*.tsx") if not is_test(p)]
tests = [p for p in FEATURES.rglob("*.tsx") if is_test(p)]
src = {p: p.read_text(encoding="utf-8", errors="replace") for p in files}
tsrc = {p: p.read_text(encoding="utf-8", errors="replace") for p in tests}
print(f"scanning {len(files)} components / {len(tests)} test files under features/")

defined: dict[str, pathlib.Path] = {}
for p, s in src.items():
    for m in re.finditer(r"export\s+(?:default\s+)?function\s+([A-Z][A-Za-z0-9_]*)", s):
        defined.setdefault(m.group(1), p)
    for m in re.finditer(r"export\s+const\s+([A-Z][A-Za-z0-9_]*)\s*[:=]", s):
        defined.setdefault(m.group(1), p)

inbound: dict[str, list[pathlib.Path]] = collections.defaultdict(list)
for p, s in src.items():
    for name, home in defined.items():
        if home != p and re.search(rf"<{name}[\s/>]", s):
            inbound[name].append(p)

# A panel is mounted by REGISTRY, not JSX: studio/panels/catalog.ts maps `component: X`. Without
# this every dockable panel reads as dead — the scanner's own false-positive class, found by
# CHECKING the first two hits instead of reporting them.
catalog_path = FEATURES / "studio" / "panels" / "catalog.ts"
catalog = catalog_path.read_text(encoding="utf-8", errors="replace")
for m in re.finditer(r"component:\s*([A-Z][A-Za-z0-9_]*)", catalog):
    inbound[m.group(1)].append(catalog_path)

cands = {n: f for n, f in defined.items() if NAME_HINT.search(n)
         and ("composition" in str(f) or "plan-forge" in str(f))}


def rel(p: pathlib.Path) -> str:
    return str(p.relative_to(ROOT)).replace("\\", "/")


def mounted_in_tests(name: str) -> int:
    return sum(1 for s in tsrc.values() if re.search(rf"<{name}[\s/>]", s))


dead = sorted(n for n in cands if not inbound[n])
single = sorted(n for n in cands if len(inbound[n]) == 1)

print(f"\n=== composition / plan-forge candidates: {len(cands)} ===")
print(f"\n--- ZERO inbound mount ({len(dead)}) — dead by construction ---")
for n in dead:
    print(f"  {n:32s} {rel(cands[n])}")
if not dead:
    print("  (none)")

print(f"\n=== door-gate coverage for the {len(single)} single-parent components ===")
print("a child mounted directly in tests while its PARENT never is = the exact F10 setup\n")
rows = []
for n in single:
    parent = inbound[n][0].stem
    rows.append((n, parent, mounted_in_tests(n), mounted_in_tests(parent)))

unexercised = [r for r in rows if r[3] == 0]
covered = [r for r in rows if r[3] > 0]

print(f"--- GATE NEVER EXERCISED ({len(unexercised)}) — ranked by how well the CHILD is tested ---")
print("    (a well-tested child behind an untested gate is precisely how F10 shipped)")
for n, parent, ct, _ in sorted(unexercised, key=lambda r: -r[2]):
    warn = "   <-- child tested, gate not" if ct else ""
    print(f"  {n:30s} parent={parent:26s} childTests={ct:2d} parentTests= 0{warn}")

print(f"\n--- parent mounted somewhere, gate at least reachable ({len(covered)}) ---")
for n, parent, ct, pt in sorted(covered):
    print(f"  {n:30s} parent={parent:26s} childTests={ct:2d} parentTests={pt:2d}")
