import argparse
import json
from pathlib import Path

import joblib

from data_watch.model import evaluate, read_csv, train
from data_watch.store import ingest, initialize


def main():
    parser = argparse.ArgumentParser(description="Data Watch: treinar, avaliar e reproduzir métricas")
    commands = parser.add_subparsers(dest="command", required=True)
    fit = commands.add_parser("train")
    fit.add_argument("--history", type=Path, default=Path("data/history.csv"))
    fit.add_argument("--model", type=Path, default=Path("var/model.joblib"))
    fit.add_argument("--seed", type=int, default=42)
    fit.add_argument("--quantile", type=float, default=0.98)
    evaluation = commands.add_parser("evaluate")
    evaluation.add_argument("--csv", type=Path, default=Path("data/replay.csv"))
    evaluation.add_argument("--model", type=Path, default=Path("var/model.joblib"))
    evaluation.add_argument("--report", type=Path, default=Path("reports/evaluation.json"))
    replay = commands.add_parser("replay")
    replay.add_argument("--csv", type=Path, default=Path("data/replay.csv"))
    replay.add_argument("--model", type=Path, default=Path("var/model.joblib"))
    replay.add_argument("--db", type=Path, default=Path("var/metrics.sqlite3"))
    args = parser.parse_args()
    try:
        if args.command == "train":
            bundle = train(args.history, args.model, args.seed, args.quantile)
            result = {key: value for key, value in bundle.items() if key != "estimator"}
        elif args.command == "evaluate":
            report = evaluate(joblib.load(args.model), args.csv, args.report)
            result = {key: report[key] for key in ("isolation_forest", "fixed_rule_baseline", "evaluation_rows", "injected_anomalies")}
        else:
            rows, _ = read_csv(args.csv)  # Valida o arquivo inteiro antes de gravar.
            initialize(args.db)
            result = ingest(args.db, joblib.load(args.model), rows)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(2, f"Erro: {exc}\n")


if __name__ == "__main__":
    main()

