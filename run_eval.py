"""Run simulated calls for every persona under each agent configuration and score them.

    python run_eval.py                      # the full experiment grid (cached model calls make re-runs fast)
    python run_eval.py --only persona:qwen2.5:3b:code_flow --personas en01,hg01

Each configuration is variant:model:flow_mode. Results go to results/calls/<config>.jsonl and results/summary.json.
The customer simulator is the same model for every configuration, so only the agent changes.
"""
import argparse
import json
import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from voiceagent.agent import Agent, run_call  # noqa: E402
from voiceagent.llm import ChatModel  # noqa: E402
from voiceagent.metrics import score, summarise  # noqa: E402
from voiceagent.simulator import Customer, load_personas  # noqa: E402

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"
SIMULATOR = "llama3.2:3b"

GRID = [
    # prompt engineering: same model, three prompt variants
    ("zero_shot", "qwen2.5:3b", "code_flow"),
    ("few_shot", "qwen2.5:3b", "code_flow"),
    ("persona", "qwen2.5:3b", "code_flow"),
    # who owns the flow: the model, or code
    ("persona", "qwen2.5:3b", "llm_flow"),
    # model comparison with the best prompt
    ("persona", "llama3.2:3b", "code_flow"),
    ("persona", "gemma2:2b", "code_flow"),
]


def name(cfg) -> str:
    return ":".join(cfg)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="run one configuration, e.g. persona:qwen2.5:3b:code_flow")
    ap.add_argument("--personas", help="comma-separated persona ids")
    ap.add_argument("--dev", action="store_true", help="use the development personas (for prompt iteration, never the test set)")
    args = ap.parse_args()

    personas = load_personas(ROOT / "data" / ("dev_personas.json" if args.dev else "personas.json"))
    if args.personas:
        keep = set(args.personas.split(","))
        personas = [p for p in personas if p["id"] in keep]
    grid = GRID
    if args.only:
        v, *m, f = args.only.split(":")
        grid = [(v, ":".join(m), f)]

    cache = RESULTS / "llm_cache.jsonl"
    sim = ChatModel(SIMULATOR, cache=cache)
    models = {}
    summary_path = RESULTS / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    (RESULTS / "calls").mkdir(parents=True, exist_ok=True)

    for cfg in grid:
        variant, model, flow_mode = cfg
        models.setdefault(model, ChatModel(model, cache=cache))
        agent = Agent(models[model], variant=variant, flow_mode=flow_mode)
        rows, scored = [], []
        start = time.time()
        for p in personas:
            seed = zlib.crc32(p["id"].encode()) % 10_000
            call = run_call(agent, Customer(p, sim), seed=seed)
            s = score(call, p)
            rows.append({"config": name(cfg), "persona": p["id"], "language": p["language"], "behavior": p["behavior"],
                         "expected": p["expected_outcome"], **call, "score": {k: v for k, v in s.items() if k != "ms"}})
            scored.append(s)
            print(f"{name(cfg):34} {p['id']}  {call['outcome']:15} {'ok ' if s['outcome_correct'] else 'BAD'} "
                  f"fields={s['field_accuracy']}  turns={s['turns']}", flush=True)
        out = RESULTS / "calls" / f"{name(cfg).replace(':', '_')}.jsonl"
        if args.dev:
            dev = RESULTS / "dev"
            dev.mkdir(exist_ok=True)
            (dev / f"{name(cfg).replace(':', '_')}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        elif not args.personas:
            out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
            summary[name(cfg)] = {"variant": variant, "model": model, "flow_mode": flow_mode, **summarise(scored)}
            summary_path.write_text(json.dumps(summary, indent=2))
        print(f"== {name(cfg)}: {json.dumps(summarise(scored))}  ({time.time() - start:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
