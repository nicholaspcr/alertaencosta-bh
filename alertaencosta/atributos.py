from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from alertaencosta import config

COLUNAS_LOG = [f"log_{nome}" for nome in config.JANELAS_HORAS]
COLUNAS_REGIONAL = [f"reg_{r}" for r in config.REGIONAIS]
COLUNAS_MODELO = [*COLUNAS_LOG, "dias_chuva", "mes_sin", "mes_cos", *COLUNAS_REGIONAL]


@dataclass(frozen=True)
class SerieHoraria:
    inicio: pd.Timestamp
    valores: np.ndarray
    soma_acumulada: np.ndarray
    lidas_acumuladas: np.ndarray

    @classmethod
    def de_tabela(cls, tabela: pd.DataFrame, inicio: pd.Timestamp, fim: pd.Timestamp) -> SerieHoraria:
        grade = pd.date_range(inicio, fim, freq="h", tz="UTC")
        serie = tabela.set_index("data_hora_utc")["precipitacao_mm"].reindex(grade)
        valores = serie.to_numpy(dtype=float)
        lidas = ~np.isnan(valores)
        soma = np.concatenate([[0.0], np.cumsum(np.where(lidas, valores, 0.0))])
        contagem = np.concatenate([[0], np.cumsum(lidas)])
        return cls(grade[0], valores, soma, contagem)

    def _indice(self, instante: pd.Timestamp) -> int:
        horas = (instante - self.inicio) // pd.Timedelta(hours=1) + 1
        return int(min(max(horas, 0), len(self.valores)))

    def janela(self, fim: pd.Timestamp, horas: int) -> tuple[float, int]:
        b = self._indice(fim)
        a = self._indice(fim - pd.Timedelta(hours=horas))
        lidas = int(self.lidas_acumuladas[b] - self.lidas_acumuladas[a])
        return float(self.soma_acumulada[b] - self.soma_acumulada[a]), horas - lidas


def janela_valida(horas_ausentes: int, horas: int) -> bool:
    return horas_ausentes <= config.MAX_FRACAO_AUSENTE * horas


def dias_consecutivos_com_chuva(serie: SerieHoraria, fim: pd.Timestamp) -> int:
    dias = 0
    for i in range(config.DIAS_CHUVA_MAXIMO):
        soma, ausentes = serie.janela(fim - pd.Timedelta(hours=24 * i), 24)
        if not janela_valida(ausentes, 24) or soma < config.DIAS_CHUVA_LIMIAR_MM:
            break
        dias += 1
    return dias


def atributos_chuva(serie: SerieHoraria, fim: pd.Timestamp) -> dict[str, float | int | bool]:
    linha: dict[str, float | int | bool] = {}
    valido = True
    for nome, horas in config.JANELAS_HORAS.items():
        soma, ausentes = serie.janela(fim, horas)
        linha[nome] = soma
        linha[f"ausentes_{nome}"] = ausentes
        if horas >= 72:
            valido = valido and janela_valida(ausentes, horas)
    linha["dias_chuva"] = dias_consecutivos_com_chuva(serie, fim)
    linha["chuva_valida"] = valido
    return linha


def atributos_calendario(regional: str, mes: int) -> dict[str, float | int | str]:
    angulo = 2 * np.pi * (mes - 1) / 12
    return {
        "regional": regional,
        "mes": mes,
        "mes_sin": float(np.sin(angulo)),
        "mes_cos": float(np.cos(angulo)),
        **{f"reg_{r}": int(r == regional) for r in config.REGIONAIS},
    }


def com_logs(tabela: pd.DataFrame) -> pd.DataFrame:
    return tabela.assign(**{f"log_{n}": np.log1p(tabela[n]) for n in config.JANELAS_HORAS})


def fim_da_janela_vistoria(dia: date) -> pd.Timestamp:
    return pd.Timestamp(dia).tz_localize(config.FUSO_BH).tz_convert("UTC")


def tabela_vistorias(vistorias: pd.DataFrame, series: dict[str, SerieHoraria]) -> pd.DataFrame:
    linhas = []
    for v in vistorias.itertuples(index=False):
        fim = fim_da_janela_vistoria(v.data.date())
        serie = series[config.REGIONAL_PONTO[v.regional]]
        linhas.append({
            "id_vistoria": v.id_vistoria,
            "cod_vistoria": v.cod_vistoria,
            "data": v.data,
            "rotulo": v.rotulo,
            "fim_janela_utc": fim,
            **atributos_calendario(v.regional, v.data.month),
            **atributos_chuva(serie, fim),
        })
    return com_logs(pd.DataFrame(linhas))


def tabela_atual(series: dict[str, SerieHoraria], fins: dict[str, pd.Timestamp],
                 agora: pd.Timestamp) -> pd.DataFrame:
    mes = agora.tz_convert(config.FUSO_BH).month
    linhas = []
    for r in config.REGIONAIS:
        ponto = config.REGIONAL_PONTO[r]
        linhas.append({**atributos_calendario(r, mes), **atributos_chuva(series[ponto], fins[ponto])})
    return com_logs(pd.DataFrame(linhas))


def faixa_72h(chuva_mm: float) -> int:
    return int(np.searchsorted(config.FAIXAS_72H_MM, chuva_mm, side="right") - 1)


def rotulo_faixa(indice: int) -> str:
    limites = config.FAIXAS_72H_MM
    if indice + 1 < len(limites):
        return f"{limites[indice]:g} a {limites[indice + 1]:g} mm"
    return f"{limites[indice]:g} mm ou mais"
