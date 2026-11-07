from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alertaencosta import config

RESPOSTAS = Path(__file__).parent / "respostas"


def resposta_gravada(nome: str) -> dict:
    return json.loads((RESPOSTAS / nome).read_text(encoding="utf-8"))


def serie(estacao: str, inicio: str, horas: int, valor: float = 0.0,
          ausentes: set[int] | None = None) -> pd.DataFrame:
    ausentes = ausentes or set()
    tempos = pd.date_range(inicio, periods=horas, freq="h", tz="UTC")
    linhas = [(estacao, t, valor) for i, t in enumerate(tempos) if i not in ausentes]
    return pd.DataFrame(linhas, columns=["estacao", "data_hora_utc", "precipitacao_mm"])


def escrever_csv_vistorias(caminho: Path, linhas: list[tuple], cabecalho: str =
                           "COD_VISTORIA;REGIONAL;DATA_EXECUCAO_VISTORIA;NIVEL_RISCO") -> Path:
    texto = "\n".join([cabecalho, *(";".join(map(str, l)) for l in linhas)]) + "\n"
    caminho.write_text(texto, encoding="utf-8")
    return caminho


@pytest.fixture(scope="session")
def ambiente_sintetico(tmp_path_factory) -> dict[str, Path]:
    from alertaencosta.ingestao_chuva import gravar_serie
    from alertaencosta.rotulos import sha256_arquivo

    tmp_path = tmp_path_factory.mktemp("ambiente")
    gerador = np.random.default_rng(7)
    inicio, fim = "2020-12-01", "2026-01-01"
    tempos = pd.date_range(inicio, fim, freq="h", tz="UTC")
    tabelas = []
    for ponto in config.PONTOS:
        chuvoso = gerador.random(len(tempos)) < 0.08
        valores = np.where(chuvoso, gerador.gamma(1.2, 2.5, len(tempos)), 0.0).round(1)
        tabelas.append(pd.DataFrame({"estacao": ponto, "data_hora_utc": tempos, "precipitacao_mm": valores}))
    chuva = pd.concat(tabelas, ignore_index=True)

    dir_urbel = tmp_path / "urbel"
    dir_chuva = tmp_path / "chuva"
    dir_urbel.mkdir()
    dir_chuva.mkdir()
    gravar_serie(chuva, "sintética", dir_chuva / "serie_horaria.csv", dir_chuva / "metadados.json")

    soma72 = {p: chuva[chuva.estacao == p].set_index("data_hora_utc")["precipitacao_mm"]
              .rolling(72).sum() for p in config.PONTOS}
    linhas, codigo = [], 1
    for dia in pd.date_range("2021-01-05", "2025-12-28", freq="D"):
        for regional in config.REGIONAIS:
            if gerador.random() > 0.35:
                continue
            fim_janela = pd.Timestamp(dia).tz_localize(config.FUSO_BH).tz_convert("UTC")
            c72 = soma72[config.REGIONAL_PONTO[regional]].asof(fim_janela)
            p = 1 / (1 + np.exp(-(-1.8 + 0.05 * c72)))
            nivel = "Alto" if gerador.random() < p else "Baixo"
            linhas.append((f"{codigo:011d}", regional, dia.strftime("%d/%m/%Y"), nivel))
            codigo += 1
    csv = escrever_csv_vistorias(dir_urbel / "vistorias.csv", linhas)
    manifesto = {"lotes": [{"arquivo": "vistorias.csv", "sha256": sha256_arquivo(csv)}]}
    (dir_urbel / "lotes.json").write_text(json.dumps(manifesto), encoding="utf-8")

    modelos_dir = tmp_path / "modelos"
    site_dir = tmp_path / "site"
    modelos_dir.mkdir()
    site_dir.mkdir()
    return {
        "lotes": dir_urbel / "lotes.json",
        "serie": dir_chuva / "serie_horaria.csv",
        "meta": dir_chuva / "metadados.json",
        "modelos": modelos_dir,
        "site": site_dir,
    }


@pytest.fixture(scope="session")
def versao_treinada(ambiente_sintetico):
    from alertaencosta import treino, versoes

    entradas = treino.preparar_entradas(ambiente_sintetico["lotes"], ambiente_sintetico["serie"],
                                        ambiente_sintetico["meta"])
    id_versao, info = treino.treinar(entradas, ambiente_sintetico["modelos"], n_bootstrap=10)
    return versoes.carregar(id_versao, ambiente_sintetico["modelos"]), entradas
