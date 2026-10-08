"""
Extraction eval
================
Scores how well a local model distills agent exchanges into memories and turns
statements into knowledge-graph triples, using the same prompts and parsing as
the SDK. Needs a running Ollama with the model pulled.

    python evals/run_extraction_eval.py --model llama3.2 [--out results.json]

Distillation
    recall     expected facts that were stored
    precision  stored facts that match an expected fact
    noise      facts stored for exchanges with nothing worth keeping
    fragments  stored facts shorter than 5 words (not self-contained)

Triples
    recall     expected subject -> object edges that were extracted
    generic    triples whose object label is the fallback "Entity"
"""

import argparse
import json
import os
import sys
import time

from dolphin_memory.config import DolphinConfig
from dolphin_memory.extraction import TripleExtractor

CASES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extraction_cases.json")


def _has(text: str, groups) -> bool:
    text = text.lower()
    return all(any(keyword in text for keyword in group) for group in groups)


def run_distill(extractor, cases):
    expected = found = stored = matched = noise = fragments = 0
    seconds = 0.0
    details = []
    for case in cases:
        start = time.time()
        facts = extractor.distill(case["exchange"])
        seconds += time.time() - start

        hits = [any(_has(f, groups) for f in facts) for groups in case["keep"]]
        useful = [f for f in facts if any(_has(f, groups) for groups in case["keep"])]

        expected += len(case["keep"])
        found += sum(hits)
        stored += len(facts)
        matched += len(useful)
        fragments += sum(1 for f in facts if len(f.split()) < 5)
        if not case["keep"]:
            noise += len(facts)
        details.append({"id": case["id"], "facts": facts, "hits": hits})
        print(f"  {case['id']:<22} {sum(hits)}/{len(hits)} kept, {len(facts)} stored", flush=True)

    return {
        "recall": found / expected if expected else 0.0,
        "precision": matched / stored if stored else 0.0,
        "noise": noise,
        "fragments": fragments,
        "stored": stored,
        "seconds_per_call": seconds / len(cases),
        "details": details,
    }


def run_triples(extractor, cases):
    expected = found = total = generic = 0
    seconds = 0.0
    details = []
    for case in cases:
        start = time.time()
        triples = extractor.extract(case["text"])
        seconds += time.time() - start

        hits = [
            any(_has(t["s"], [subject]) and _has(t["o"], [obj]) for t in triples)
            for subject, obj in case["edges"]
        ]
        expected += len(case["edges"])
        found += sum(hits)
        total += len(triples)
        generic += sum(1 for t in triples if t["ol"] == "Entity")
        details.append({"id": case["id"], "triples": triples, "hits": hits})
        print(f"  {case['id']:<22} {sum(hits)}/{len(hits)} edges, {len(triples)} triples", flush=True)

    return {
        "recall": found / expected if expected else 0.0,
        "generic": generic / total if total else 0.0,
        "triples": total,
        "seconds_per_call": seconds / len(cases),
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default="llama3.2")
    parser.add_argument("--out", help="write full results as JSON")
    args = parser.parse_args()

    with open(CASES, encoding="utf-8") as f:
        cases = json.load(f)

    extractor = TripleExtractor(
        DolphinConfig(ollama_model=args.model, extraction_profile="agent")
    )

    print(f"Model: {args.model}\nDistillation:", flush=True)
    distill = run_distill(extractor, cases["distill"])
    print("Triples:", flush=True)
    triples = run_triples(extractor, cases["triples"])

    print(
        f"\n{args.model}\n"
        f"  distill  recall {distill['recall']:.0%}  precision {distill['precision']:.0%}  "
        f"noise {distill['noise']}  fragments {distill['fragments']}  "
        f"({distill['seconds_per_call']:.1f}s/call)\n"
        f"  triples  recall {triples['recall']:.0%}  generic labels {triples['generic']:.0%}  "
        f"({triples['seconds_per_call']:.1f}s/call)"
    )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"model": args.model, "distill": distill, "triples": triples}, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
