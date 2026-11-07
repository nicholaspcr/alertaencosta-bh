from __future__ import annotations

import numpy as np
import pandas as pd

from alertaencosta import avaliacao, config


def _tabela_md(df: pd.DataFrame, casas: int = 3) -> str:
    def formatar(v):
        if isinstance(v, (float, np.floating)):
            return f"{v:.{casas}f}"
        return str(v)
    cabecalho = "| " + " | ".join(map(str, df.columns)) + " |"
    separador = "|" + "|".join("---" for _ in df.columns) + "|"
    linhas = ["| " + " | ".join(formatar(v) for v in linha) + " |" for linha in df.itertuples(index=False)]
    return "\n".join([cabecalho, separador, *linhas])


def _exclusao_por_regional(conjunto) -> pd.DataFrame:
    validas = conjunto.tabela.groupby("regional").size()
    excluidas = conjunto.excluidas.assign(
        regional=conjunto.excluidas["regional"].replace("", "(sem regional)")
    ).groupby("regional").size()
    tabela = pd.DataFrame({"validas": validas, "excluidas": excluidas}).fillna(0).astype(int)
    total = tabela["validas"] + tabela["excluidas"]
    return tabela.assign(taxa_exclusao=tabela["excluidas"] / total).reset_index(names="regional")


def _prevalencia(tabela: pd.DataFrame) -> pd.DataFrame:
    semestre = tabela["data"].dt.year.astype(str) + "-S" + ((tabela["data"].dt.month > 6) + 1).astype(str)
    return (tabela.assign(semestre=semestre).groupby("semestre")["rotulo"]
                  .agg(n="size", prevalencia="mean").reset_index())


def montar_relatorio(info: dict, conjunto, divisao, p_teste: dict, entradas) -> str:
    teste = divisao.teste
    tipo = info["tipo"]
    m = info["metricas_teste"]
    linhas_metricas = pd.DataFrame([
        {"modelo": t, "AUC": v["auc"], "Brier": v["brier"],
         "M-01 supera baseline": "—" if t == "baseline" else
             ("sim" if avaliacao.supera_baseline(v, m["baseline"]) else "não"),
         "M-06 falhas": len(info["aprovacao"][t]["m06_falhas"])}
        for t, v in m.items()
    ])
    regionais = avaliacao.por_regional(teste, p_teste[tipo], p_teste["baseline"])
    calib = avaliacao.calibracao(teste["rotulo"], p_teste[tipo])
    estacoes = avaliacao.por_estacao_do_ano(teste, p_teste[tipo])
    exclusao = _exclusao_por_regional(conjunto)
    descartes = entradas.carga.descartados["motivo"].value_counts().rename_axis("motivo").reset_index()
    vigente = info["comparacao_vigente"]
    explic = info["explicacao"]
    explic_tabela = pd.DataFrame(
        sorted(explic["valores"].items(), key=lambda kv: -abs(kv[1])), columns=["variável", "valor"])

    partes = [
        f"# Relatório de validação — {info['id']}",
        "",
        "> **Status: PENDENTE DE REVISÃO HUMANA (etapa 7).** A versão só vai ao ar com "
        f"`python -m alertaencosta.publicar {info['id']}` depois da leitura deste relatório.",
        "",
        "## Dados",
        f"- Versão dos dados: `{info['versao_dados']}`; série de chuva: {entradas.meta_chuva['fonte']}.",
        f"- Treino: {info['n_treino']} vistorias ({info['periodo_treino'][0]} a {info['periodo_treino'][1]}); "
        f"teste: {info['n_teste']} ({info['periodo_teste'][0]} a {info['periodo_teste'][1]}).",
        f"- Descartes na limpeza da chuva: {entradas.descartes_chuva}.",
        "",
        "### Descartes na carga das vistorias (todos os anos)",
        _tabela_md(descartes),
        "",
        "### Viés de exclusão por regional (2021–2025)",
        _tabela_md(exclusao),
        "",
        "### Prevalência do rótulo (Alto ou Muito alto) por semestre",
        _tabela_md(_prevalencia(conjunto.tabela)),
        "",
        "## Escolha da regularização (validação em janela crescente, Brier médio)",
        _tabela_md(pd.DataFrame(info["validacao_C_brier"].items(), columns=["C", "Brier"]), 4),
        f"\nC escolhido: {info['C_logistica']}",
        "",
        "## M-01 e M-06: candidatos no teste de 2025",
        _tabela_md(linhas_metricas, 4),
        "",
        f"**Modelo escolhido: {tipo}**" + (" — nenhum candidato passou; o baseline será publicado e declarado na página."
                                            if info["baseline_em_uso"] else ""),
        "",
        "## M-02: comparação com a versão vigente",
        "Primeira versão: não há versão vigente." if vigente is None else
        f"Vigente `{vigente['versao']}`: AUC {vigente['auc']:.4f}, Brier {vigente['brier']:.4f}. "
        "Piora de AUC ou Brier precisa de justificativa escrita abaixo.",
        "",
        "## M-03 (informativo): calibração em cinco faixas",
        _tabela_md(calib),
        "",
        "## M-04: desempenho por regional",
        _tabela_md(regionais),
        f"\nMaior diferença de Brier entre regionais: {regionais['brier'].max() - regionais['brier'].min():.4f}.",
        "",
        "## M-05 (informativo): período chuvoso (out–mar) e seco (abr–set)",
        _tabela_md(pd.DataFrame([{"período": k, **v} for k, v in estacoes.items()]), 4),
        "",
        f"## M-07: interpretabilidade ({explic['tipo']})",
        _tabela_md(explic_tabela, 4),
        "",
        "## M-08 a M-10",
        f"- M-08: semente {info['semente']}; bibliotecas {info['bibliotecas']}. Reprodução coberta por `make testes`.",
        f"- M-09: treino completo, com {info['n_bootstrap']} réplicas de bootstrap, em {info['tempo_treino_s']} s.",
        f"- M-10: limiares de nível (P{config.PERCENTIS_NIVEL[0]}, P{config.PERCENTIS_NIVEL[1]}) = "
        f"{info['limiares'][0]:.4f}, {info['limiares'][1]:.4f}.",
        "",
        "## Revisão humana",
        "- [ ] Relatório lido por: ______  Data: ______",
        "- [ ] Regional com exclusão muito acima das demais foi discutida.",
        "- Decisões e justificativas:",
        "",
    ]
    return "\n".join(partes)
