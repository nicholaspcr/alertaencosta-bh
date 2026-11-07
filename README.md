# AlertaEncosta BH

Página Web pública que mostra, para cada uma das nove regionais de Belo Horizonte, a probabilidade de uma vistoria de risco geológico da URBEL ser classificada como *Alto* ou *Muito alto*, dada a chuva recente. **Não é alerta oficial nem laudo técnico.** Em emergência, ligue para a Defesa Civil: 199.

Projeto acadêmico da disciplina Tópicos em Computação I (PUC Minas). Equipe: Breno de Oliveira Brandão e Nicholas Pereira Cristofaro. O código segue a Arquitetura (10/10/2026), a Lista de Requisitos v2 e o Plano de Testes (25/10/2026).

## Como funciona

| Ciclo | Etapas | Comando | Onde roda |
|---|---|---|---|
| A, treino (semestral, manual) | 1 a 7 | `make treino`, depois `make publicar VERSAO=...` | notebook do time |
| B, operação (a cada 3 h) | 8 a 11 | `python -m alertaencosta.estimar` | GitHub Actions |
| Página | 12 | `site/` | GitHub Pages |

- **Rótulos:** vistorias da URBEL no Portal de Dados Abertos da PBH, em `dados/urbel/`, registradas com hash em `dados/urbel/lotes.json`.
- **Chuva:** Open-Meteo, modelo ECMWF IFS, nos pontos das estações A521 (Pampulha) e F501 (Cercadinho). A série histórica fica em `dados/chuva/`; a leitura recente é feita a cada execução, sem chave de acesso.
- **Modelos:** baseline sazonal, regressão logística L2 e árvore rasa. Uma versão só é escolhida se superar o baseline em AUC e Brier no teste de 2025 (RNF09). Se nenhuma superar, o baseline é publicado e a página declara isso.
- **Versões:** cada versão fica em `modelos/<id>/` (modelo, réplicas de bootstrap, `versao.json` e `relatorio.md`). `modelos/VIGENTE` guarda a versão em uso.

## Instalação

```sh
make instalar      # Python 3.13, dependências com versão fixa
make testes        # testes sem rede, com dados sintéticos e respostas gravadas
```

## Procedimentos

**Novo lote de vistorias (RF08).** Baixe o CSV do portal da PBH pelo navegador e rode `make lote ARQUIVO=caminho.csv`. Um arquivo com coluna ausente ou desconhecida, nível de risco desconhecido ou regional fora da lista é rejeitado, e a base vigente não muda. Se o cabeçalho vier trocado, informe a ordem real: `python -m alertaencosta.carga_lote arquivo.csv --ordem-colunas cod_vistoria,data,regional,nivel_risco`.

**Retreino (RF09).** `make treino` gera `modelos/<id>/relatorio.md`. Leia o relatório (etapa 7), registre a revisão no fim dele e, se aprovar, rode `make publicar VERSAO=<id>`. Faça commit de `modelos/` e `site/como-funciona.json` e dispare o workflow `estimativas`.

**Reversão (RNF10).** `make publicar VERSAO=<id-anterior>`, commit e disparo do workflow.

**Recarga manual da chuva (RF07).** Se a execução agendada falhar, dispare o workflow `estimativas` pela aba Actions (`workflow_dispatch`). Para conferir localmente: `make estimar` e `make site`.

**Série histórica de chuva.** `make ingestao` baixa de novo a série de 2020-12 a 2025 e grava o hash em `dados/chuva/metadados.json`. Rode antes de um retreino com período novo.

## Publicação no GitHub Pages

1. Crie o repositório público no GitHub e envie este código.
2. Em *Settings → Pages*, escolha *Source: GitHub Actions*.
3. Publique uma versão (`make publicar VERSAO=...`), faça commit e dispare o workflow `estimativas`.

O workflow roda a cada 3 horas. O GitHub desativa agendamentos depois de 60 dias sem atividade em repositório público: confira o histórico de execuções toda semana. Se o agendamento parar, a página passa sozinha a "dados insuficientes" depois de 48 horas.

## Dados e licenças

- Vistorias: URBEL, Portal de Dados Abertos da PBH.
- Dados meteorológicos: [Open-Meteo.com](https://open-meteo.com) (CC BY 4.0), uso não comercial, cerca de 16 chamadas por dia.

As decisões de projeto e seus motivos estão em [`docs/decisoes.md`](docs/decisoes.md).
