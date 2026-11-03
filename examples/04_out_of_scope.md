# Example 4 — Out-of-scope request

**Model:** qwen3:4b-instruct  
**Scenario:** Customer asks for something unrelated to the store. The agent must decline politely and redirect to what it can help with.

**Customer**

Você pode me ajudar a escolher um bom filme para ver hoje à noite?

**Assistant**

Lamento, mas eu só posso ajudar com produtos, pedidos, pagamentos, devoluções e políticas do Empório da Música. Não posso recomendar filmes. Se quiser, posso te ajudar com algo relacionado aos nossos instrumentos musicais!

## Notes

- Correct behavior: declines in Portuguese, does not answer the out-of-scope request, and redirects to store topics.
- Known limitation: mixed questions (one out-of-scope part combined with another) are handled less reliably. In a test with "capital of France + math homework", the small 4B model answered the trivial general-knowledge part despite the scope rule in the system prompt, and only declined the math part. This example uses a purely out-of-scope question.
