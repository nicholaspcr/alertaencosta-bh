from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ResultadoLimpeza:
    tabela: pd.DataFrame
    descartes: dict[str, int]


def limpar_chuva(
    tabela: pd.DataFrame, maximos_mm: Mapping[str, float], agora: pd.Timestamp
) -> ResultadoLimpeza:
    maximo = tabela["estacao"].map(maximos_mm).astype(float)
    valor = tabela["precipitacao_mm"]
    sem_valor = valor.isna()
    negativa = valor < 0
    acima = valor > maximo
    futura = tabela["data_hora_utc"] > agora
    invalida = sem_valor | negativa | acima | futura

    descartes = {
        "sem_valor": int(sem_valor.sum()),
        "negativa": int((negativa & ~sem_valor).sum()),
        "acima_maximo": int((acima & ~sem_valor).sum()),
        "data_futura": int((futura & ~sem_valor).sum()),
    }
    limpa = (tabela[~invalida]
             .drop_duplicates(["estacao", "data_hora_utc"], keep="last")
             .sort_values(["estacao", "data_hora_utc"])
             .reset_index(drop=True))
    return ResultadoLimpeza(limpa, descartes)


def maximos_historicos(tabela: pd.DataFrame) -> dict[str, float]:
    validos = tabela[tabela["precipitacao_mm"] >= 0]
    return {est: float(v) for est, v in validos.groupby("estacao")["precipitacao_mm"].max().items()}
