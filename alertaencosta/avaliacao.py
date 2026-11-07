from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from alertaencosta import config
from alertaencosta.atributos import atributos_calendario, com_logs
from alertaencosta.modelos import probabilidade, regressao_logistica


class ErroVazamento(AssertionError):
    pass


@dataclass(frozen=True)
class Divisao:
    treino: pd.DataFrame
    teste: pd.DataFrame


def dividir(tabela: pd.DataFrame) -> Divisao:
    ano = tabela["data"].dt.year
    return Divisao(tabela[ano.isin(config.ANOS_TREINO)].reset_index(drop=True),
                   tabela[ano == config.ANO_TESTE].reset_index(drop=True))


def checar_vazamento(divisao: Divisao) -> None:
    todas = pd.concat([divisao.treino, divisao.teste])
    fim_local = todas["fim_janela_utc"].dt.tz_convert(config.FUSO_BH)
    mesmo_dia = fim_local.dt.date == todas["data"].dt.date
    if not (mesmo_dia & (fim_local.dt.hour == 0) & (fim_local.dt.minute == 0)).all():
        raise ErroVazamento("janela de chuva não termina às 23h59 da véspera da vistoria")
    if divisao.treino["data"].max() >= divisao.teste["data"].min():
        raise ErroVazamento("treino tem data igual ou posterior ao início do teste")
    if set(divisao.treino["id_vistoria"]) & set(divisao.teste["id_vistoria"]):
        raise ErroVazamento("a mesma vistoria está no treino e no teste")


def metricas(y, p) -> dict[str, float]:
    y = np.asarray(y)
    auc = roc_auc_score(y, p) if len(set(y)) > 1 else float("nan")
    return {"auc": float(auc), "brier": float(brier_score_loss(y, p)), "n": int(len(y))}


def escolher_C(treino: pd.DataFrame) -> tuple[float, dict[float, float]]:
    ano = treino["data"].dt.year
    resultados = {}
    for C in config.GRADE_C:
        briers = []
        for anos_ajuste, ano_validacao in config.VALIDACAO_JANELA_CRESCENTE:
            ajuste, validacao = treino[ano.isin(anos_ajuste)], treino[ano == ano_validacao]
            if ajuste.empty or validacao.empty or ajuste["rotulo"].nunique() < 2:
                continue
            modelo = regressao_logistica(C).fit(ajuste, ajuste["rotulo"])
            briers.append(brier_score_loss(validacao["rotulo"], probabilidade(modelo, validacao)))
        resultados[C] = float(np.mean(briers)) if briers else float("inf")
    return min(resultados, key=resultados.get), resultados


def supera_baseline(candidato: dict, baseline: dict) -> bool:
    return candidato["auc"] > baseline["auc"] and candidato["brier"] < baseline["brier"]


def por_regional(teste: pd.DataFrame, p: np.ndarray, p_base: np.ndarray) -> pd.DataFrame:
    linhas = []
    for regional in config.REGIONAIS:
        filtro = (teste["regional"] == regional).to_numpy()
        if not filtro.any():
            continue
        y = teste.loc[filtro, "rotulo"]
        linhas.append({
            "regional": regional,
            "n": int(filtro.sum()),
            "taxa_observada": float(y.mean()),
            "brier": float(brier_score_loss(y, p[filtro])),
            "brier_baseline": float(brier_score_loss(y, p_base[filtro])),
        })
    tabela = pd.DataFrame(linhas)
    return tabela.assign(pior_que_baseline=tabela["brier"] > tabela["brier_baseline"])


def calibracao(y, p, faixas: int = 5) -> pd.DataFrame:
    dados = pd.DataFrame({"y": np.asarray(y), "p": p})
    dados["faixa"] = pd.qcut(dados["p"].rank(method="first"), faixas, labels=False)
    return (dados.groupby("faixa")
                 .agg(n=("y", "size"), previsto=("p", "mean"), observado=("y", "mean"))
                 .reset_index())


def por_estacao_do_ano(teste: pd.DataFrame, p: np.ndarray) -> dict[str, dict]:
    chuvoso = teste["data"].dt.month.isin([10, 11, 12, 1, 2, 3]).to_numpy()
    return {
        "chuvoso": metricas(teste.loc[chuvoso, "rotulo"], p[chuvoso]),
        "seco": metricas(teste.loc[~chuvoso, "rotulo"], p[~chuvoso]),
    }


def grade_de_chuva() -> pd.DataFrame:
    base = np.array([0, 1, 2, 5, 10, 20, 40, 60, 80, 120, 160])
    return pd.DataFrame({
        "chuva_24h": base,
        "chuva_72h": base * 1.5,
        "chuva_7d": base * 2.0,
        "chuva_30d": base * 3.0,
        "dias_chuva": np.minimum(base // 10, 7),
    })


def monotonia(modelo) -> list[tuple[str, int]]:
    grade = grade_de_chuva()
    falhas = []
    for regional in config.REGIONAIS:
        for mes in range(1, 13):
            calendario = atributos_calendario(regional, mes)
            X = com_logs(grade.assign(**calendario))
            p = probabilidade(modelo, X)
            if np.any(np.diff(p) < -1e-12):
                falhas.append((regional, mes))
    return falhas
