from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

import pandas as pd

from alertaencosta import config

COLUNAS = ["estacao", "data_hora_utc", "precipitacao_mm"]
TEMPO_LIMITE_S = 30

BuscarJson = Callable[[str], dict]


class ErroColeta(RuntimeError):
    pass


@dataclass(frozen=True)
class Leituras:
    tabela: pd.DataFrame
    fonte: str


class FonteChuva(Protocol):
    nome: str

    def leituras(self, estacao: str, inicio: pd.Timestamp, fim: pd.Timestamp) -> Leituras:
        ...


def buscar_json_http(url: str) -> dict:
    pedido = urllib.request.Request(url, headers={"User-Agent": "alertaencosta-bh"})
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE_S) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        raise ErroColeta(f"HTTP {erro.code} em {urllib.parse.urlsplit(url).netloc}") from erro
    except (urllib.error.URLError, TimeoutError, OSError) as erro:
        raise ErroColeta(f"erro de rede: {erro}") from erro
    except json.JSONDecodeError as erro:
        raise ErroColeta("resposta não é JSON") from erro


def tabela_vazia() -> pd.DataFrame:
    return pd.DataFrame({
        "estacao": pd.Series(dtype=str),
        "data_hora_utc": pd.Series(dtype="datetime64[ns, UTC]"),
        "precipitacao_mm": pd.Series(dtype=float),
    })


def resposta_para_tabela(estacao: str, resposta: dict) -> pd.DataFrame:
    if resposta.get("error"):
        raise ErroColeta(f"Open-Meteo: {resposta.get('reason', 'erro sem motivo')}")
    if resposta.get("utc_offset_seconds", 0) != 0:
        raise ErroColeta("resposta fora de UTC")
    horario = resposta.get("hourly") or {}
    tempos, valores = horario.get("time"), horario.get("precipitation")
    if tempos is None or valores is None or len(tempos) != len(valores):
        raise ErroColeta("resposta sem série horária de precipitação")
    try:
        tabela = pd.DataFrame({
            "estacao": estacao,
            "data_hora_utc": pd.to_datetime(tempos, utc=True),
            "precipitacao_mm": pd.to_numeric(pd.Series(valores, dtype=object), errors="coerce"),
        })
    except (ValueError, TypeError) as erro:
        raise ErroColeta(f"resposta com horário inválido: {erro}") from erro
    return (tabela.drop_duplicates("data_hora_utc", keep="last")
                  .sort_values("data_hora_utc")
                  .reset_index(drop=True)[COLUNAS])


def _parametros_base(ponto: config.Ponto) -> dict[str, str]:
    return {
        "latitude": f"{ponto.latitude}",
        "longitude": f"{ponto.longitude}",
        "hourly": "precipitation",
        "models": config.MODELO_METEOROLOGICO,
        "timezone": "GMT",
    }


def _recortar(tabela: pd.DataFrame, inicio: pd.Timestamp, fim: pd.Timestamp) -> pd.DataFrame:
    dentro = (tabela["data_hora_utc"] >= inicio) & (tabela["data_hora_utc"] <= fim)
    return tabela[dentro].reset_index(drop=True)


@dataclass
class OpenMeteoHistorico:
    buscar_json: BuscarJson = buscar_json_http
    nome: str = "Open-Meteo Historical Weather API (ECMWF IFS)"
    chamadas: int = field(default=0)

    def leituras(self, estacao: str, inicio: pd.Timestamp, fim: pd.Timestamp) -> Leituras:
        ponto = config.PONTOS[estacao]
        parametros = {
            **_parametros_base(ponto),
            "start_date": inicio.date().isoformat(),
            "end_date": fim.date().isoformat(),
        }
        url = f"{config.URL_HISTORICO}?{urllib.parse.urlencode(parametros)}"
        self.chamadas += 1
        tabela = resposta_para_tabela(estacao, self.buscar_json(url))
        return Leituras(_recortar(tabela, inicio, fim), self.nome)


@dataclass
class OpenMeteoRecente:
    agora: pd.Timestamp
    buscar_json: BuscarJson = buscar_json_http
    nome: str = "Open-Meteo Forecast API, horas passadas (ECMWF IFS)"
    chamadas: int = field(default=0)

    def leituras(self, estacao: str, inicio: pd.Timestamp, fim: pd.Timestamp) -> Leituras:
        ponto = config.PONTOS[estacao]
        parametros = {
            **_parametros_base(ponto),
            "past_days": str(config.DIAS_PASSADOS_RECENTE),
            "forecast_days": "1",
        }
        url = f"{config.URL_RECENTE}?{urllib.parse.urlencode(parametros)}"
        self.chamadas += 1
        tabela = resposta_para_tabela(estacao, self.buscar_json(url))
        limite = min(fim, self.agora)
        return Leituras(_recortar(tabela, inicio, limite), self.nome)


def inicio_do_dia_utc(dia: date) -> pd.Timestamp:
    return pd.Timestamp(dia, tz="UTC")
