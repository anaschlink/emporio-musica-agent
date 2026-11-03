# Example 2 — Active promotions

**Model:** qwen3:4b-instruct  
**Scenario:** Customer asks whether there are active promotions on acoustic guitars. Uses the dedicated `search_promotions` tool, which returns all active promotions without the six-result cap of the regular catalog search.

**Customer**

Há alguma promoção ativa para violões? Informe os modelos, preços originais e preços promocionais.

**Assistant**

Sim, há duas promoções ativas para violões no momento:

1. **Crafter HT-100 Folk Aço Natural**
   - Preço original: R$ 2.399,00
   - Preço promocional: R$ 1.967,18 (desconto de 18%)
   - Disponível em até 12 parcelas de R$ 163,93 (sem juros)

2. **Taylor 110e Dreadnought Natural**
   - Preço original: R$ 5.999,00
   - Preço promocional: R$ 5.519,08 (desconto de 8%)
   - Disponível em até 12 parcelas de R$ 459,92 (sem juros)

Observação: Até o momento, nenhum dos produtos oferece valor via PIX. As parcelas são calculadas com base nos preços promocionais e não incluem juros.

Se desejar, posso ajudar com outras informações sobre esses modelos ou sugerir outros produtos.

## Note

An earlier run of this scenario answered that no guitar promotions existed: `search_products` caps results at six, ordered by price, so the two most expensive promotional guitars were cut off. This example was produced after adding a dedicated `search_promotions` tool.
