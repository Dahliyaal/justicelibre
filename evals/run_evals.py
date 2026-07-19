"""Harnais d'évaluation du serveur MCP JusticeLibre.

Méthodologie de l'article Anthropic « Writing effective tools for agents » :
des tâches juridiques réalistes multi-appels (evals/tasks.py), une boucle
agentique branchée sur le serveur MCP réel, des vérificateurs
programmatiques, et des métriques au-delà de la précision (nombre
d'appels de tools, tokens consommés, erreurs, durée) — les transcripts
complets sont conservés dans le JSON de sortie pour analyse.

Par défaut le harnais évalue le endpoint public (justicelibre.org/mcp) :
aucune base locale requise. Nécessite `pip install anthropic mcp` et une
clé API Anthropic (ANTHROPIC_API_KEY ou profil `ant auth login`).

Usage :
    python3 evals/run_evals.py                       # tout, endpoint public
    python3 evals/run_evals.py --dry-run             # sans appel LLM
    python3 evals/run_evals.py --tasks cedh-lookup,loi-timeline
    python3 evals/run_evals.py --endpoint http://127.0.0.1:8765/mcp
    python3 evals/run_evals.py --model claude-sonnet-5 --output out.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tasks import TASKS  # noqa: E402

DEFAULT_ENDPOINT = "https://justicelibre.org/mcp"
DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_MAX_TURNS = 8
MAX_TOKENS = 16000
# Un texte intégral d'arrêt peut dépasser 100k caractères : on tronque les
# résultats de tools pour protéger le contexte de l'agent (en le disant).
TOOL_RESULT_MAX_CHARS = 30000

SYSTEM_PROMPT = (
    "Tu es un assistant de recherche juridique. Tu réponds en français en "
    "t'appuyant EXCLUSIVEMENT sur les tools JusticeLibre fournis — jamais "
    "sur ta mémoire pour les faits juridiques (textes, dates, numéros). "
    "Cite les identifiants retournés par les tools quand ils existent."
)


# ─── Vérificateurs ───────────────────────────────────────────────────

def _norm(s: str) -> str:
    """minuscules + sans accents, pour des vérificateurs tolérants
    (l'article Anthropic met en garde contre les verifiers trop stricts)."""
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def verify(task: dict, final_text: str, tools_called: list[str]) -> tuple[bool, list[str]]:
    """Retourne (passed, détail des critères échoués)."""
    failures: list[str] = []
    text = _norm(final_text or "")
    v = task.get("verify", {})
    for sub in v.get("all_substrings", []):
        if _norm(sub) not in text:
            failures.append(f"substring attendue absente : {sub!r}")
    any_subs = v.get("any_substrings", [])
    if any_subs and not any(_norm(s) in text for s in any_subs):
        failures.append(f"aucune des substrings attendues : {any_subs!r}")
    if v.get("regex") and not re.search(v["regex"], final_text or "", re.IGNORECASE):
        failures.append(f"regex sans match : {v['regex']!r}")
    expected = task.get("expect_tool_any", [])
    if expected and not any(t in tools_called for t in expected):
        failures.append(f"aucun des tools attendus appelé : {expected!r} (appelés : {sorted(set(tools_called))!r})")
    return (not failures, failures)


# ─── Boucle agentique ────────────────────────────────────────────────

def _mcp_result_to_text(result: Any) -> tuple[str, bool]:
    """Aplatit un résultat MCP en texte pour le tool_result Anthropic."""
    text = "".join(c.text for c in result.content if getattr(c, "text", None))
    if not text.strip():
        text = "(réponse vide)"
    if len(text) > TOOL_RESULT_MAX_CHARS:
        text = text[:TOOL_RESULT_MAX_CHARS] + (
            "\n[... tronqué par le harnais d'évaluation : utiliser des "
            "requêtes plus ciblées ou la pagination ...]"
        )
    return text, bool(getattr(result, "isError", False))


async def run_task(client, session, anthropic_tools, task: dict, model: str, verbose: bool) -> dict:
    """Exécute une tâche : boucle jusqu'à end_turn ou max_turns."""
    max_turns = task.get("max_turns", DEFAULT_MAX_TURNS)
    messages: list[dict] = [{"role": "user", "content": task["prompt"]}]
    usage = {"input_tokens": 0, "output_tokens": 0,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    tools_called: list[str] = []
    tool_errors = 0
    transcript: list[dict] = []
    final_text = ""
    stop_reason = "max_turns_reached"
    started = time.monotonic()

    for _turn in range(max_turns):
        response = await client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            thinking={"type": "adaptive"},
            tools=anthropic_tools,
            messages=messages,
        )
        for k in usage:
            usage[k] += getattr(response.usage, k, 0) or 0

        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_uses:
            final_text = "\n".join(b.text for b in response.content if b.type == "text")
            stop_reason = response.stop_reason
            break

        # Renvoyer le contenu assistant intact (thinking inclus), puis TOUS
        # les tool_results dans UN SEUL message user (règle appels parallèles).
        messages.append({"role": "assistant", "content": response.content})
        results = await asyncio.gather(
            *(session.call_tool(tu.name, arguments=tu.input) for tu in tool_uses)
        )
        tool_results = []
        for tu, res in zip(tool_uses, results):
            tools_called.append(tu.name)
            text, is_error = _mcp_result_to_text(res)
            tool_errors += int(is_error)
            transcript.append({"tool": tu.name, "input": tu.input,
                               "is_error": is_error, "result_excerpt": text[:600]})
            if verbose:
                print(f"      ⚙ {tu.name}({json.dumps(tu.input, ensure_ascii=False)[:120]})"
                      f"{' [ERREUR]' if is_error else ''}")
            tool_results.append({"type": "tool_result", "tool_use_id": tu.id,
                                 "content": text, "is_error": is_error})
        messages.append({"role": "user", "content": tool_results})

    passed, failures = verify(task, final_text, tools_called)
    return {
        "id": task["id"],
        "passed": passed,
        "failures": failures,
        "stop_reason": stop_reason,
        "turns": len([m for m in messages if m["role"] == "assistant"]) + 1,
        "tool_calls": len(tools_called),
        "tools_called": tools_called,
        "tool_errors": tool_errors,
        "usage": usage,
        "duration_s": round(time.monotonic() - started, 1),
        "final_answer": final_text,
        "transcript": transcript,
    }


# ─── Dry-run (sans LLM) ──────────────────────────────────────────────

async def dry_run(session, anthropic_tools, tasks: list[dict]) -> int:
    """Valide la connectivité MCP, le schéma des tâches et les tools
    attendus, sans consommer de tokens."""
    names = {t["name"] for t in anthropic_tools}
    print(f"  ✓ endpoint MCP joignable — {len(names)} tools exposés")
    errors = 0
    seen_ids: set[str] = set()
    for task in tasks:
        problems = []
        if task["id"] in seen_ids:
            problems.append("id dupliqué")
        seen_ids.add(task["id"])
        if not task.get("prompt", "").strip():
            problems.append("prompt vide")
        if not task.get("verify"):
            problems.append("aucun vérificateur")
        missing = [t for t in task.get("expect_tool_any", []) if t not in names]
        if missing:
            problems.append(f"tools attendus absents du serveur : {missing}")
        # Auto-test du vérificateur : il doit échouer sur une réponse vide
        ok_empty, _ = verify(task, "", [])
        if ok_empty:
            problems.append("le vérificateur accepte une réponse vide")
        if problems:
            errors += 1
            print(f"  ✗ {task['id']}: " + " ; ".join(problems))
        else:
            print(f"  ✓ {task['id']}")
    print(f"\nDry-run : {len(tasks) - errors}/{len(tasks)} tâches valides.")
    return 1 if errors else 0


# ─── Main ────────────────────────────────────────────────────────────

async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--tasks", default="", help="ids séparés par des virgules")
    parser.add_argument("--output", default="evals/results.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="valide MCP + tâches sans appel LLM")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    tasks = TASKS
    if args.tasks:
        wanted = {t.strip() for t in args.tasks.split(",") if t.strip()}
        unknown = wanted - {t["id"] for t in TASKS}
        if unknown:
            print(f"Tâches inconnues : {sorted(unknown)}", file=sys.stderr)
            return 2
        tasks = [t for t in TASKS if t["id"] in wanted]

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(args.endpoint) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            # Ordre déterministe : la liste des tools est en tête du prompt,
            # un ordre stable préserve le cache entre les tâches.
            anthropic_tools = sorted(
                ({"name": t.name, "description": t.description or "",
                  "input_schema": t.inputSchema} for t in listed.tools),
                key=lambda t: t["name"],
            )

            if args.dry_run:
                return await dry_run(session, anthropic_tools, tasks)

            import anthropic
            client = anthropic.AsyncAnthropic()

            results = []
            print(f"Éval : {len(tasks)} tâches — modèle {args.model} — {args.endpoint}\n")
            for i, task in enumerate(tasks, 1):
                print(f"[{i}/{len(tasks)}] {task['id']} …")
                try:
                    r = await run_task(client, session, anthropic_tools,
                                       task, args.model, args.verbose)
                except anthropic.RateLimitError:
                    print("      rate-limit — pause 60 s puis reprise")
                    await asyncio.sleep(60)
                    r = await run_task(client, session, anthropic_tools,
                                       task, args.model, args.verbose)
                except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                    r = {"id": task["id"], "passed": False,
                         "failures": [f"erreur API : {e}"], "stop_reason": "api_error",
                         "turns": 0, "tool_calls": 0, "tools_called": [],
                         "tool_errors": 0, "usage": {}, "duration_s": 0.0,
                         "final_answer": "", "transcript": []}
                mark = "✓" if r["passed"] else "✗"
                print(f"    {mark} {r['tool_calls']} appels, "
                      f"{r['usage'].get('output_tokens', 0)} tokens out, "
                      f"{r['duration_s']}s"
                      + ("" if r["passed"] else f" — {'; '.join(r['failures'])}"))
                results.append(r)

    # ── Synthèse ──
    passed = sum(1 for r in results if r["passed"])
    tot_in = sum(r["usage"].get("input_tokens", 0) + r["usage"].get("cache_read_input_tokens", 0)
                 + r["usage"].get("cache_creation_input_tokens", 0) for r in results)
    tot_out = sum(r["usage"].get("output_tokens", 0) for r in results)
    tot_calls = sum(r["tool_calls"] for r in results)
    tot_errors = sum(r["tool_errors"] for r in results)
    print(f"\n{'─' * 60}")
    print(f"Réussite : {passed}/{len(results)} "
          f"({100 * passed / max(len(results), 1):.0f} %)")
    print(f"Appels de tools : {tot_calls} (dont {tot_errors} en erreur)")
    print(f"Tokens : {tot_in} in (cache inclus) / {tot_out} out")

    report = {
        "endpoint": args.endpoint,
        "model": args.model,
        "passed": passed,
        "total": len(results),
        "results": results,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Rapport détaillé (transcripts inclus) : {out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
