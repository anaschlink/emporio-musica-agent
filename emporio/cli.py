from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from emporio.agent import Agent
from emporio.data_loader import load_store
from emporio.policies import load_policies

SESSIONS_DIR = Path(__file__).resolve().parent.parent / "sessions"
TIMEZONE = ZoneInfo("America/Campo_Grande")


def _append(path: Path, role: str, content: str, **extra) -> None:
    record = {
        "ts": datetime.now(TIMEZONE).isoformat(),
        "role": role,
        "content": content,
        **extra,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_history(path: Path, limit: int) -> list[dict]:
    if not path.exists():
        return []
    history = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("role") in {"user", "assistant"}:
                history.append({"role": rec["role"], "content": rec["content"]})
    history = history[-limit:]
    while history and history[0]["role"] != "user":
        history.pop(0)
    return history


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Atendente virtual da Empório da Música")
    parser.add_argument("--session", default="default", help="nome da sessão (histórico em sessions/<nome>.jsonl)")
    parser.add_argument("--model", default=None, help="modelo (padrão: LLM_MODEL do .env)")
    parser.add_argument(
        "--policy-mode",
        choices=["tool", "inline"],
        default=os.getenv("POLICY_MODE", "tool") or "tool",
    )
    args = parser.parse_args()

    SESSIONS_DIR.mkdir(exist_ok=True)
    session_path = SESSIONS_DIR / f"{args.session}.jsonl"

    store = load_store()
    policies = load_policies()
    agent = Agent(store, policies, policy_mode=args.policy_mode, model=args.model)
    agent.history = _load_history(session_path, agent.max_history_messages)

    print("Empório da Música - atendimento virtual. Digite /quit para sair.")
    if agent.history:
        print(f"(sessão '{args.session}' retomada com {len(agent.history)} mensagens)")

    while True:
        try:
            user_input = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in {"/quit", "/exit"}:
            break

        try:
            result = agent.respond(user_input)
        except Exception as exc:
            print(
                "\n[erro] Não consegui falar com o modelo. "
                "Verifique se o Ollama está rodando (ollama ps) e se o modelo foi baixado."
            )
            print(f"[detalhe] {type(exc).__name__}: {exc}")
            continue

        _append(session_path, "user", user_input)
        _append(session_path, "assistant", result.content, escalated=result.escalated)
        print(f"\nAtendente: {result.content}")


if __name__ == "__main__":
    main()
