import json

from emporio.agent import Agent


def tool_message(payload):
    return {
        "role": "tool",
        "content": json.dumps(payload),
    }


def make_agent(policy_mode="tool", policies=None):
    agent = Agent.__new__(Agent)
    agent.policy_mode = policy_mode
    agent.policies = policies or {}
    return agent


def test_validates_amount_returned_by_tool():
    messages = [tool_message({"price_brl": 1299.90})]
    agent = make_agent()

    assert agent._validate_money("O preço é R$ 1.299,90.", messages)


def test_rejects_unsupported_amount():
    messages = [tool_message({"price_brl": 1299.90})]
    agent = make_agent()

    assert not agent._validate_money("O preço é R$ 1.499,90.", messages)


def test_accepts_multiple_supported_amounts():
    messages = [
        tool_message({
            "price_brl": 1000.0,
            "pix_price": 950.0,
            "installment_value": 100.0,
        })
    ]
    agent = make_agent()

    assert agent._validate_money(
        "R$ 1.000,00 ou R$ 950,00 no PIX.",
        messages,
    )


def test_does_not_validate_numbers_without_currency_symbol():
    messages = [tool_message({"price_brl": 1000.0})]
    agent = make_agent()

    assert agent._validate_money("São 10 parcelas.", messages)


def test_validates_amounts_written_as_reais():
    messages = [tool_message({"price_brl": 1000.0})]
    agent = make_agent()

    assert agent._validate_money("Custa 1.000 reais.", messages)
    assert not agent._validate_money("São 10 parcelas de 100 reais.", messages)