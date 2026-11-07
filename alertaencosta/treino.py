from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

from alertaencosta import avaliacao, config, modelos, versoes
from alertaencosta.atributos import SerieHoraria, faixa_72h, tabela_vistorias
from alertaencosta.ingestao_chuva import ler_metadados, ler_serie
from alertaencosta.limpeza import limpar_chuva
from alertaencosta.relatorio import montar_relatorio
from alertaencosta.rotulos import ResultadoCarga, carregar_lotes, sha256_arquivo


@dataclass(frozen=True)
class Entradas:
    carga: ResultadoCarga
    series: dict[str, SerieHoraria]
    descartes_chuva: dict[str, int]
    meta_chuva: dict
    versao_dados: str


@dataclass(frozen=True)
class ConjuntoModelagem:
    tabela: pd.DataFrame
    excluidas: pd.DataFrame


def versao_dos_dados(arquivo_lotes: Path, meta_chuva: dict) -> str:
    resumo = sha256_arquivo(arquivo_lotes) + meta_chuva["sha256"]
    return "dados-" + hashlib.sha256(resumo.encode()).hexdigest()[:12]


def preparar_entradas(arquivo_lotes: Path = config.ARQUIVO_LOTES,
                      arquivo_serie: Path = config.ARQUIVO_SERIE,
                      arquivo_meta: Path = config.ARQUIVO_META_CHUVA,
                      hoje: date | None = None) -> Entradas:
    carga = carregar_lotes(arquivo_lotes, hoje)
    meta = ler_metadados(arquivo_meta)
    if sha256_arquivo(arquivo_serie) != meta["sha256"]:
        raise RuntimeError("série de chuva diferente da registrada em metadados.json")
    serie = ler_serie(arquivo_serie)
    agora = pd.Timestamp.now(tz="UTC")
    limpeza = limpar_chuva(serie, meta["maximos_mm"], agora)
    inicio, fim = serie["data_hora_utc"].min(), serie["data_hora_utc"].max()
    series = {
        codigo: SerieHoraria.de_tabela(grupo, inicio, fim)
        for codigo, grupo in limpeza.tabela.groupby("estacao")
    }
    return Entradas(carga, series, limpeza.descartes, meta, versao_dos_dados(arquivo_lotes, meta))


def montar_conjunto(entradas: Entradas) -> ConjuntoModelagem:
    vistorias = entradas.carga.tabela
    data = vistorias["data"].dt.date
    no_periodo = vistorias[(data >= config.INICIO_PERIODO) & (data <= config.FIM_PERIODO)]
    tabela = tabela_vistorias(no_periodo, entradas.series)
    sem_janela = tabela[~tabela["chuva_valida"]]
    excluidas = pd.concat([
        entradas.carga.descartados.loc[
            entradas.carga.descartados["data"].dt.year.between(
                config.INICIO_PERIODO.year, config.FIM_PERIODO.year),
            ["cod_vistoria", "regional", "motivo"]],
        sem_janela[["cod_vistoria", "regional"]].assign(motivo="janela_de_chuva_incompleta"),
    ], ignore_index=True)
    return ConjuntoModelagem(tabela[tabela["chuva_valida"]].reset_index(drop=True), excluidas)


def contagens_por_faixa(tabela: pd.DataFrame) -> dict[str, list[int]]:
    faixas = tabela["chuva_72h"].map(faixa_72h)
    n_faixas = len(config.FAIXAS_72H_MM)
    return {
        r: [int(((tabela["regional"] == r) & (faixas == i)).sum()) for i in range(n_faixas)]
        for r in config.REGIONAIS
    }


def escolher_modelo(metricas: dict, falhas_m06: dict) -> str:
    aprovados = [t for t in ("logistica", "arvore")
                 if avaliacao.supera_baseline(metricas[t], metricas["baseline"]) and not falhas_m06[t]]
    if {"logistica", "arvore"} <= set(aprovados):
        arv, log = metricas["arvore"], metricas["logistica"]
        margem = arv["auc"] >= log["auc"] + config.MARGEM_ARVORE_AUC and arv["brier"] < log["brier"]
        return "arvore" if margem else "logistica"
    return aprovados[0] if aprovados else "baseline"


def comparar_vigente(teste: pd.DataFrame, pasta: Path) -> dict | None:
    try:
        vigente = versoes.carregar_vigente(pasta)
    except versoes.ErroVersao:
        return None
    p = modelos.probabilidade(vigente.modelo, teste)
    return {"versao": vigente.id, **avaliacao.metricas(teste["rotulo"], p)}


def treinar(entradas: Entradas, pasta_modelos: Path = config.DIR_MODELOS,
            n_bootstrap: int = config.N_BOOTSTRAP, hoje: date | None = None) -> tuple[str, dict]:
    inicio_relogio = time.perf_counter()
    conjunto = montar_conjunto(entradas)
    divisao = avaliacao.dividir(conjunto.tabela)
    avaliacao.checar_vazamento(divisao)
    treino, teste = divisao.treino, divisao.teste

    C, validacao_C = avaliacao.escolher_C(treino)
    candidatos = {
        "baseline": modelos.BaselineSazonal().fit(treino, treino["rotulo"]),
        "logistica": modelos.regressao_logistica(C).fit(treino, treino["rotulo"]),
        "arvore": modelos.arvore_rasa().fit(treino, treino["rotulo"]),
    }
    p_teste = {t: modelos.probabilidade(m, teste) for t, m in candidatos.items()}
    metricas = {t: avaliacao.metricas(teste["rotulo"], p) for t, p in p_teste.items()}
    falhas_m06 = {t: avaliacao.monotonia(m) for t, m in candidatos.items()}
    tipo = escolher_modelo(metricas, falhas_m06)
    escolhido = candidatos[tipo]

    replicas = modelos.bootstrap(escolhido, treino, treino["rotulo"], n=n_bootstrap)
    limites = modelos.limiares(modelos.probabilidade(escolhido, treino))
    id_versao = versoes.novo_id(hoje or date.today(), pasta_modelos)

    info = {
        "id": id_versao,
        "tipo": tipo,
        "baseline_em_uso": tipo == "baseline",
        "versao_dados": entradas.versao_dados,
        "C_logistica": C,
        "validacao_C_brier": {str(k): v for k, v in validacao_C.items()},
        "metricas_teste": metricas,
        "aprovacao": {
            t: {"m01_supera_baseline": t == "baseline" or avaliacao.supera_baseline(metricas[t], metricas["baseline"]),
                "m06_falhas": [list(f) for f in falhas_m06[t]]}
            for t in candidatos
        },
        "comparacao_vigente": comparar_vigente(teste, pasta_modelos),
        "limiares": list(limites),
        "explicacao": modelos.explicacao(tipo, escolhido),
        "contagens_faixa_72h": contagens_por_faixa(conjunto.tabela),
        "faixas_72h_mm": list(config.FAIXAS_72H_MM),
        "maximos_chuva_mm": entradas.meta_chuva["maximos_mm"],
        "regional_ponto": config.REGIONAL_PONTO,
        "n_treino": len(treino), "n_teste": len(teste),
        "periodo_treino": [str(treino["data"].min().date()), str(treino["data"].max().date())],
        "periodo_teste": [str(teste["data"].min().date()), str(teste["data"].max().date())],
        "semente": config.SEMENTE,
        "n_bootstrap": n_bootstrap,
        "bibliotecas": {"python": platform.python_version(), "numpy": np.__version__,
                        "pandas": pd.__version__, "scikit-learn": sklearn.__version__},
    }
    info["tempo_treino_s"] = round(time.perf_counter() - inicio_relogio, 1)
    relatorio = montar_relatorio(info, conjunto, divisao, p_teste, entradas)
    versoes.salvar(id_versao, escolhido, replicas, info, relatorio, pasta_modelos)
    return id_versao, info


def main() -> int:
    entradas = preparar_entradas()
    id_versao, info = treinar(entradas)
    print(json.dumps({"versao": id_versao, "tipo": info["tipo"],
                      "metricas_teste": info["metricas_teste"],
                      "tempo_treino_s": info["tempo_treino_s"]}, ensure_ascii=False, indent=2))
    print(f"Leia modelos/{id_versao}/relatorio.md e, se aprovar, rode: "
          f"python -m alertaencosta.publicar {id_versao}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
