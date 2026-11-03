import json
from types import SimpleNamespace

import pytest

from emporio.agent import (
    FALLBACK_LOOP,
    FALLBACK_MONEY,
    MAX_TOOL_ITERATIONS,
    FALLBACK_EMPTY,
    Agent,
)


def tool_call(call_id, name, args):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def reply(content=None, calls=None):
    message = SimpleNamespace(content=content, tool_calls=calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.replies.pop(0)


def build_agent(replies, monkeypatch, tool_results=None):
    agent = Agent.__new__(Agent)
    agent.store = None
    agent.policies = {}
    agent.policy_mode = "tool"
    agent.model = "fake"
    agent.max_history_messages = 12
    agent.system_prompt = "system"
    agent.history = []
    agent.client = FakeClient(replies)

    results = tool_results or {}

    def fake_tool(name, arguments):
        value = results.get(name, {"ok": True})
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(agent, "_tool_call", fake_tool)
    return agent


def test_simple_tool_cycle(monkeypatch):
    agent = build_agent(
        [
            reply(calls=[tool_call("1", "get_product", {"name": "x"})]),
            reply("O preço é R$ 100,00."),
        ],
        monkeypatch,
        {"get_product": {"price_brl": 100.0}},
    )

    result = agent.respond("quanto custa?")

    assert result.content == "O preço é R$ 100,00."
    assert not result.escalated
    assert agent.history[-1]["role"] == "assistant"


def test_two_tool_calls_in_same_reply(monkeypatch):
    agent = build_agent(
        [
            reply(calls=[
                tool_call("1", "get_product", {"name": "a"}),
                tool_call("2", "get_product", {"name": "b"}),
            ]),
            reply("Ok."),
        ],
        monkeypatch,
    )

    agent.respond("compare")

    second_call_messages = agent.client.calls[1]["messages"]
    tool_msgs = [m for m in second_call_messages if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["1", "2"]


def test_tool_failure_is_reported_to_model(monkeypatch):
    agent = build_agent(
        [
            reply(calls=[tool_call("1", "get_product", {"name": "a"})]),
            reply("Não consegui consultar."),
        ],
        monkeypatch,
        {"get_product": RuntimeError("boom")},
    )

    agent.respond("x")

    tool_msg = [
        m for m in agent.client.calls[1]["messages"] if m["role"] == "tool"
    ][0]
    payload = json.loads(tool_msg["content"])
    assert payload["error"] == "tool_execution_failed"


def test_invalid_json_arguments_do_not_crash(monkeypatch):
    bad = SimpleNamespace(
        id="1",
        function=SimpleNamespace(name="get_product", arguments="{not json"),
    )
    agent = build_agent(
        [reply(calls=[bad]), reply("Desculpe.")], monkeypatch
    )

    assert agent.respond("x").content == "Desculpe."


def test_escalation_sets_flag(monkeypatch):
    agent = build_agent(
        [
            reply(calls=[tool_call("1", "escalate_to_human", {
                "kind": "complaint", "summary": "s"})]),
            reply("Protocolo abc, retorno em 24 horas úteis."),
        ],
        monkeypatch,
        {"escalate_to_human": {"ticket_id": "abc",
                               "expected_return": "24 horas úteis"}},
    )

    assert agent.respond("quero reclamar").escalated is True


def test_failed_escalation_does_not_set_flag(monkeypatch):
    agent = build_agent(
        [
            reply(calls=[tool_call("1", "escalate_to_human", {
                "kind": "complaint", "summary": "s"})]),
            reply("Não consegui encaminhar."),
        ],
        monkeypatch,
        {"escalate_to_human": ValueError("kind inválido")},
    )

    assert agent.respond("x").escalated is False


def test_fifth_tool_round_still_gets_final_answer(monkeypatch):
    rounds = [
        reply(calls=[tool_call(str(i), "get_product", {"name": "a"})])
        for i in range(MAX_TOOL_ITERATIONS)
    ]
    agent = build_agent(rounds + [reply("Resposta final.")], monkeypatch)

    assert agent.respond("x").content == "Resposta final."
    assert "tools" not in agent.client.calls[-1]


def test_runaway_tool_loop_falls_back(monkeypatch):
    rounds = [
        reply(calls=[tool_call(str(i), "get_product", {"name": "a"})])
        for i in range(MAX_TOOL_ITERATIONS + 1)
    ]
    agent = build_agent(rounds, monkeypatch)

    assert agent.respond("x").content == FALLBACK_LOOP


def test_unsupported_amount_retries_then_falls_back(monkeypatch):
    agent = build_agent(
        [reply("Custa R$ 999,00."), reply("Custa R$ 888,00.")],
        monkeypatch,
    )

    assert agent.respond("quanto?").content == FALLBACK_MONEY


def test_unsupported_amount_recovers_on_retry(monkeypatch):
    agent = build_agent(
        [reply("Custa R$ 999,00."), reply("Não consigo confirmar o valor.")],
        monkeypatch,
    )

    assert agent.respond("quanto?").content == "Não consigo confirmar o valor."


def test_model_error_does_not_leave_dangling_user_message(monkeypatch):
    agent = build_agent([], monkeypatch)  # pop from empty list raises

    with pytest.raises(IndexError):
        agent.respond("x")

    assert agent.history == []


def test_history_starts_with_user_and_is_bounded(monkeypatch):
    agent = build_agent([reply("ok")] * 10, monkeypatch)
    agent.max_history_messages = 4

    for i in range(10):
        agent.respond(f"msg {i}")

    assert len(agent.history) <= 4
    assert agent.history[0]["role"] == "user"

def test_empty_final_answer_uses_empty_fallback(monkeypatch):
    agent = build_agent([reply("")], monkeypatch)

    assert agent.respond("x").content == FALLBACK_EMPTY