"""CLI: python -m oddsagent {serve,suggest,sports}"""
from __future__ import annotations

import argparse
import sys

from .config import load_settings
from .llm import LLM
from .provider import OddsProvider, ProviderError
from .service import suggest


def _print_result(result: dict) -> None:
    print(f"{result['events_analyzed']} meciuri analizate · {result['generated_at']}")
    quota = result.get("quota") or {}
    if quota.get("remaining"):
        print(f"Credite API rămase: {quota['remaining']}")
    for note in result["notes"]:
        print("•", note)
    for index, combo in enumerate(result["combos"], 1):
        print(
            f"\n#{index} {combo['book_title']} · cota {combo['odds']:.2f} · "
            f"prob. ~{combo['probability'] * 100:.0f}% · EV {combo['ev'] * 100:+.1f}%"
        )
        for leg in combo["legs"]:
            print(f"   {leg['match']} ({leg['league']}, {leg['start']})")
            print(f"      {leg['pick']} @ {leg['odds']:.2f}  (prob. ~{leg['fair_probability'] * 100:.0f}%)")
    if result.get("explanation"):
        print("\nExplicație:\n" + result["explanation"])
    print("\n" + result["disclaimer"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="oddsagent")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="pornește API-ul și pagina web")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    run = sub.add_parser("suggest", help="generează bilete în terminal")
    run.add_argument("--target", type=float, default=2.0)
    run.add_argument("--max-legs", type=int, default=5, choices=range(2, 6))
    run.add_argument("--hours", type=int, default=48)
    run.add_argument("--min-prob", type=float, default=0.5)
    run.add_argument("--rank-by", choices=["ev", "prob"], default="ev")
    run.add_argument("--no-explain", action="store_true")

    sub.add_parser("sports", help="listează cheile de sport disponibile la furnizor")

    args = parser.parse_args(argv)
    settings = load_settings()

    if args.command == "serve":
        import uvicorn

        from .api import create_app

        uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level="info")
        return 0

    provider = OddsProvider(settings)
    try:
        if args.command == "sports":
            for sport in provider.list_sports():
                if sport.get("group") == "Soccer":
                    print(f"{sport['key']:40} {sport.get('title', '')}")
            return 0
        result = suggest(
            settings,
            provider,
            LLM(settings),
            target=args.target,
            max_legs=args.max_legs,
            hours=args.hours,
            min_prob=args.min_prob,
            rank_by=args.rank_by,
            explain=not args.no_explain,
        )
    except ProviderError as error:
        print(f"Eroare: {error}", file=sys.stderr)
        return 1
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
