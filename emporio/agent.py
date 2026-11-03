from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal

from openai import OpenAI
from pydantic import BaseModel


from emporio.data_loader import Store
from emporio.policies import all_policies_text, get_policy
from emporio.prompts import build_system_prompt
from emporio.tools import (
    escalate_to_human,
    get_order_status,
    get_product,
    search_products,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5
TIMEZONE = ZoneInfo("America/Campo_Grande")

MONEY_RE = re.compile(
    r"R\$\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?"
    r"|(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?\s*reais",
    re.IGNORECASE,
)
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

FALLBACK_EMPTY = (
    "Não consegui gerar uma resposta neste momento. "
    "Tente novamente ou solicite atendimento humano."
)
FALLBACK_MONEY = (
    "Não consegui confirmar os valores com segurança. "
    "Posso encaminhar sua solicitação para um atendente."
)
FALLBACK_LOOP = (
    "Não consegui concluir sua solicitação neste momento. "
    "Posso encaminhá-la para um atendente."
)
TOOL_FAILURE_NOTE = (
    "The tool failed. Do not present any information as confirmed. "
    "Tell the customer you could not complete this lookup and offer a human agent."
)


class AgentResponse(BaseModel):
    content: str
    escalated: bool = False


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search available products in the store catalog.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": ["string", "null"]},
                    "min_price": {"type": ["number", "null"]},
                    "max_price": {"type": ["number", "null"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product",
            "description": "Get detailed information about a product by name.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Check an order after verifying its ID and registered email or phone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "email_or_phone": {"type": "string"},
                },
                "required": ["order_id", "email_or_phone"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_policy",
            "description": "Consult a store policy by topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "enum": [
                            "payment", "returns", "shipping", "promotions",
                            "warranty", "hours", "privacy", "scope", "contact",
                        ],
                    },
                },
                "required": ["topic"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Forward a complaint, unresolved policy doubt, or explicit request for a human.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["complaint", "policy_doubt", "customer_request"],
                    },
                    "summary": {"type": "string"},
                    "contact": {"type": ["string", "null"]},
                },
                "required": ["kind", "summary"],
                "additionalProperties": False,
            },
        },
    },
]

MONEY_KEYS = {
    "price_brl", "promo_price", "pix_price", "installment_value", "original",
}

def _json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


class Agent:
    def __init__(
        self,
        store: Store,
        policies: dict[str, str],
        policy_mode: str = "tool",
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        max_history_messages: int = 12,
    ):
        self.store = store
        self.policies = policies
        self.policy_mode = policy_mode
        self.model = model or os.getenv("LLM_MODEL", "qwen3:4b")
        self.max_history_messages = max_history_messages
        self.model = model or os.getenv("LLM_MODEL", "qwen3:4b-instruct")

        self.client = OpenAI(
            base_url=base_url or os.getenv(
                "LLM_BASE_URL", "http://localhost:11434/v1"
            ),
            api_key=api_key or os.getenv("LLM_API_KEY", "ollama"),
        )

        self.system_prompt = build_system_prompt(
            policies=policies,
            policy_mode=policy_mode,
        )

        self.history: list[dict] = []

    def reset(self):
        self.history.clear()

    # ---------- tools ----------

    def _tool_call(self, name: str, arguments: dict) -> dict:
        if name == "search_products":
            return search_products(self.store, **arguments)

        if name == "get_product":
            return get_product(self.store, **arguments)

        if name == "get_order_status":
            return get_order_status(self.store, **arguments)

        if name == "get_policy":
            topic = arguments["topic"]
            if self.policy_mode == "inline":
                content = self.policies.get(topic)
                if not content:
                    return {"error": "policy_not_found", "topic": topic}
                return {"success": True, "topic": topic, "content": content}
            return get_policy(topic, self.policies, now=datetime.now(TIMEZONE))

        if name == "escalate_to_human":
            return escalate_to_human(**arguments)

        return {"error": "unknown_tool", "tool": name}

    def _run_tool_call(self, call) -> dict:
        name = call.function.name
        try:
            arguments = json.loads(call.function.arguments or "{}")
            if not isinstance(arguments, dict):
                raise TypeError("tool arguments must be a JSON object")
            return self._tool_call(name, arguments)
        except Exception:
            logger.exception("Tool call failed: %s", name)
            return {
                "error": "tool_execution_failed",
                "tool": name,
                "instruction": TOOL_FAILURE_NOTE,
            }

    # ---------- history ----------

    def _messages(self) -> list[dict]:
        return [
            {"role": "system", "content": self.system_prompt},
            *self.history[-self.max_history_messages:],
        ]

    def _trim_history(self):
        self.history = self.history[-self.max_history_messages:]
        while self.history and self.history[0]["role"] != "user":
            self.history.pop(0)

    # ---------- money validation ----------

    @staticmethod
    def _money_values(text: str) -> list[float]:
        values = []
        for match in MONEY_RE.finditer(text):
            whole = match.group(1) or match.group(3)
            cents = match.group(2) or match.group(4) or "0"
            number = f"{whole.replace('.', '')}.{cents.ljust(2, '0')}"
            values.append(round(float(number), 2))
        return values

    @staticmethod
    def _allowed_money(messages: list[dict]) -> set[float]:
        allowed: set[float] = set()

        def walk(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key.endswith("_brl") or key in MONEY_KEYS:
                        if isinstance(item, (int, float)) and not isinstance(item, bool):
                            allowed.add(round(float(item), 2))
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
            elif isinstance(value, str):
                allowed.update(Agent._money_values(value))

        for message in messages:
            role = message.get("role")

            if role == "assistant":
                # Previous final answers were already validated.
                allowed.update(
                    Agent._money_values(message.get("content") or "")
                )
                continue

            if role != "tool":
                continue

            try:
                payload = json.loads(message.get("content") or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            walk(payload)

        return allowed

    def _validate_money(self, response: str, messages: list[dict]) -> bool:
        allowed = self._allowed_money(messages)
        if self.policy_mode == "inline":
            allowed.update(self._money_values(all_policies_text(self.policies)))
        return all(
            amount in allowed for amount in self._money_values(response)
        )

    # ---------- model ----------

    def _call_model(self, messages: list[dict], allow_tools: bool = True):
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        if allow_tools:
            kwargs["tools"] = TOOL_SCHEMAS
            kwargs["tool_choice"] = "auto"
        return self.client.chat.completions.create(**kwargs)

    @staticmethod
    def _clean(text: str | None) -> str:
        return THINK_RE.sub("", text or "").strip()

    # ---------- main loop ----------

    def respond(self, user_message: str) -> AgentResponse:
        self.history.append({"role": "user", "content": user_message})
        try:
            return self._respond()
        except Exception:
            # Do not leave a dangling user message if the model call failed.
            if self.history and self.history[-1]["role"] == "user":
                self.history.pop()
            raise

    def _respond(self) -> AgentResponse:
        messages = self._messages()
        escalated = False

        # One extra pass so the 5th tool round still gets a final answer.
        for iteration in range(MAX_TOOL_ITERATIONS + 1):
            allow_tools = iteration < MAX_TOOL_ITERATIONS
            completion = self._call_model(messages, allow_tools=allow_tools)
            message = completion.choices[0].message

            if not allow_tools and message.tool_calls:
                return self._finish(FALLBACK_LOOP, escalated)

            if allow_tools and message.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in message.tool_calls
                    ],
                })

                for call in message.tool_calls:
                    result = self._run_tool_call(call)
                    if (
                        call.function.name == "escalate_to_human"
                        and "error" not in result
                    ):
                        escalated = True
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(
                            result, ensure_ascii=False, default=_json_default
                        ),
                    })
                continue

            text = self._clean(message.content) or FALLBACK_EMPTY

            if not self._validate_money(text, messages):
                retry = self._call_model(
                    messages + [{
                        "role": "user",
                        "content": (
                            "[system notice] Your previous response contained "
                            "an unsupported monetary amount. Rewrite it using "
                            "only monetary values explicitly present in tool "
                            "results. If no safe answer is possible, say you "
                            "cannot confirm the value."
                        ),
                    }],
                    allow_tools=False,
                )
                text = self._clean(retry.choices[0].message.content)

                if not text or not self._validate_money(text, messages):
                    text = FALLBACK_MONEY

            return self._finish(text, escalated)

        return self._finish(FALLBACK_LOOP, escalated)

    def _finish(self, text: str, escalated: bool) -> AgentResponse:
        self.history.append({"role": "assistant", "content": text})
        self._trim_history()
        return AgentResponse(content=text, escalated=escalated)