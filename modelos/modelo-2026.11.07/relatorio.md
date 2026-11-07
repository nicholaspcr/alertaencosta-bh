# Relatório de validação — modelo-2026.11.07

> **Status: PENDENTE DE REVISÃO HUMANA (etapa 7).** A versão só vai ao ar com `python -m alertaencosta.publicar modelo-2026.11.07` depois da leitura deste relatório.

## Dados
- Versão dos dados: `dados-e89b27388420`; série de chuva: Open-Meteo Historical Weather API (ECMWF IFS).
- Treino: 5877 vistorias (2021-01-04 a 2024-12-30); teste: 1342 (2025-01-02 a 2025-12-30).
- Descartes na limpeza da chuva: {'sem_valor': 0, 'negativa': 0, 'acima_maximo': 0, 'data_futura': 0}.

### Descartes na carga das vistorias (todos os anos)
| motivo | count |
|---|---|
| nivel_vazio | 10241 |
| regional_vazia | 2859 |
| vistoria_repetida | 195 |
| data_futura | 5 |
| data_invalida | 1 |

### Viés de exclusão por regional (2021–2025)
| regional | validas | excluidas | taxa_exclusao |
|---|---|---|---|
| (sem regional) | 0 | 634 | 1.000 |
| BARREIRO | 730 | 76 | 0.094 |
| CENTRO-SUL | 1339 | 109 | 0.075 |
| LESTE | 1177 | 85 | 0.067 |
| NORDESTE | 759 | 52 | 0.064 |
| NOROESTE | 350 | 31 | 0.081 |
| NORTE | 1319 | 108 | 0.076 |
| OESTE | 673 | 67 | 0.091 |
| PAMPULHA | 348 | 33 | 0.087 |
| VENDA NOVA | 524 | 43 | 0.076 |

### Prevalência do rótulo (Alto ou Muito alto) por semestre
| semestre | n | prevalencia |
|---|---|---|
| 2021-S1 | 928 | 0.279 |
| 2021-S2 | 307 | 0.143 |
| 2022-S1 | 1480 | 0.327 |
| 2022-S2 | 789 | 0.309 |
| 2023-S1 | 1122 | 0.263 |
| 2023-S2 | 5 | 0.600 |
| 2024-S1 | 633 | 0.175 |
| 2024-S2 | 613 | 0.214 |
| 2025-S1 | 787 | 0.170 |
| 2025-S2 | 555 | 0.249 |

## Escolha da regularização (validação em janela crescente, Brier médio)
| C | Brier |
|---|---|
| 0.01 | 0.1772 |
| 0.1 | 0.1774 |
| 1.0 | 0.1775 |
| 10.0 | 0.1775 |

C escolhido: 0.01

## M-01 e M-06: candidatos no teste de 2025
| modelo | AUC | Brier | M-01 supera baseline | M-06 falhas |
|---|---|---|---|---|
| baseline | 0.5280 | 0.1711 | — | 0 |
| logistica | 0.5231 | 0.1683 | não | 0 |
| arvore | 0.4980 | 0.1660 | não | 108 |

**Modelo escolhido: baseline** — nenhum candidato passou; o baseline será publicado e declarado na página.

## M-02: comparação com a versão vigente
Primeira versão: não há versão vigente.

## M-03 (informativo): calibração em cinco faixas
| faixa | n | previsto | observado |
|---|---|---|---|
| 0 | 269 | 0.146 | 0.152 |
| 1 | 268 | 0.216 | 0.239 |
| 2 | 268 | 0.272 | 0.228 |
| 3 | 268 | 0.331 | 0.175 |
| 4 | 269 | 0.385 | 0.219 |

## M-04: desempenho por regional
| regional | n | taxa_observada | brier | brier_baseline | pior_que_baseline |
|---|---|---|---|---|---|
| BARREIRO | 130 | 0.254 | 0.196 | 0.196 | False |
| CENTRO-SUL | 218 | 0.284 | 0.211 | 0.211 | False |
| LESTE | 183 | 0.246 | 0.191 | 0.191 | False |
| NORDESTE | 178 | 0.174 | 0.165 | 0.165 | False |
| NOROESTE | 73 | 0.041 | 0.063 | 0.063 | False |
| NORTE | 220 | 0.145 | 0.168 | 0.168 | False |
| OESTE | 135 | 0.104 | 0.095 | 0.095 | False |
| PAMPULHA | 49 | 0.347 | 0.241 | 0.241 | False |
| VENDA NOVA | 156 | 0.224 | 0.178 | 0.178 | False |

Maior diferença de Brier entre regionais: 0.1784.

## M-05 (informativo): período chuvoso (out–mar) e seco (abr–set)
| período | auc | brier | n |
|---|---|---|---|
| chuvoso | 0.5687 | 0.1655 | 901 |
| seco | 0.4463 | 0.1826 | 441 |

## M-07: interpretabilidade (taxa por regional)
| variável | valor |
|---|---|
| NORTE | 0.3220 |
| BARREIRO | 0.3199 |
| NORDESTE | 0.3184 |
| LESTE | 0.3080 |
| PAMPULHA | 0.2769 |
| VENDA NOVA | 0.2457 |
| CENTRO-SUL | 0.2098 |
| NOROESTE | 0.1965 |
| OESTE | 0.1350 |

## M-08 a M-10
- M-08: semente 20261206; bibliotecas {'python': '3.13.17', 'numpy': '2.2.6', 'pandas': '2.2.3', 'scikit-learn': '1.6.1'}. Reprodução coberta por `make testes`.
- M-09: treino completo, com 200 réplicas de bootstrap, em 3.2 s.
- M-10: limiares de nível (P75, P95) = 0.3409, 0.4089.

## Revisão humana
- [x] Relatório lido por: Nicholas  Data: Cristofaro
- [x] Regional com exclusão muito acima das demais foi discutida.
- Decisões e justificativas:
  1. **Publicar o baseline sazonal como primeira versão.** Nenhum candidato passou na M-01. A regressão logística teve Brier menor (0,168 contra 0,171), mas AUC menor (0,523 contra 0,528). A árvore teve o menor Brier (0,166), mas AUC abaixo do acaso (0,498) e 108 falhas na M-06. Pela regra de aceite (RNF09), o baseline é publicado e a página declara que a chuva aparece só como informação.
  2. **O sinal é fraco, inclusive no baseline.** AUC de 0,528 no teste de 2025 fica perto do acaso. No período seco (M-05), a AUC é 0,446. A página e a "Como funciona" não devem sugerir mais precisão do que isso; a frase de nível compara com o histórico e não promete acerto.
  3. **Calibração (M-03): o modelo superestima nas faixas altas.** Nas duas faixas mais altas, o previsto foi 0,331 e 0,385, e o observado foi 0,175 e 0,219. A prevalência caiu de cerca de 0,31 em 2022 para 0,17–0,25 em 2024–2025, e o baseline aprende as taxas de 2021–2024. Consequência: "elevado" pode aparecer mais vezes do que o dado de 2025 justifica. Erro do lado conservador; registrado como limitação e revisto no próximo lote.
  4. **Viés de exclusão:** as taxas por regional ficam entre 6,4% e 9,4%, sem regional muito acima das demais. As 634 vistorias sem regional não podem ser atribuídas a nenhuma regional e ficam fora.
  5. **Lacuna em 2023-S2:** só 5 vistorias válidas no segundo semestre de 2023 (níveis em branco no lote da URBEL). O treino não tem esse período; registrado em `docs/decisoes.md`.
  6. **M-04:** nenhuma regional pior que o baseline (o modelo é o próprio baseline). Pampulha tem o maior Brier (0,241), com só 49 vistorias no teste.
  7. **O conjunto de teste de 2025 foi usado uma única vez.** Nenhuma escolha de modelo ou de atributo foi alterada depois de ver o resultado. Qualquer mudança futura de atributos fica registrada no relatório da versão seguinte.
  8. **Próxima revisão:** no próximo lote semestral da URBEL (primeira verificação prospectiva) ou depois da comparação com o INMET (D-09), o que vier primeiro.
