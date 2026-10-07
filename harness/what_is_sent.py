"""Log every statement each method sends while loading 1,000 rows. Run with log_statement='all'.
usage: python what_is_sent.py <postgres log file>"""
import re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import load
log = Path(sys.argv[1]); df = load.make(1000)
for name, fn in load.METHODS.items():
    load.reset(); start = log.stat().st_size; time.sleep(0.3)
    fn(df); time.sleep(0.5)
    text = log.read_bytes()[start:].decode("utf-8", "replace")
    stmts = re.findall(r"LOG:  (?:statement|execute [^:]*): (.*)", text)
    kinds = {}
    for s in stmts:
        k = re.sub(r"\s+", " ", s)[:70]
        k = re.sub(r"\$\d+", "$n", k); k = re.sub(r"'[^']*'", "'..'", k); k = re.sub(r"\(\$n(, \$n)*\)", "(...)", k)
        kinds[k] = kinds.get(k, 0) + 1
    print(f"== {name}: {len(stmts)} statements logged")
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])[:4]:
        print(f"   {v:5}x  {k}")
