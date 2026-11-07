from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from alertaencosta import config

COLUNAS = ("cod_vistoria", "regional", "data", "nivel_risco")

ALIASES_CABECALHO: dict[str, str] = {
    "COD_VISTORIA": "cod_vistoria",
    "REGIONAL": "regional",
    "DATA_EXECUCAO_VISTORIA": "data",
    "DATA_EEXECUCAO": "data",
    "NIVEL_RISCO": "nivel_risco",
    "NIVEL RISCO GEOLOGICO": "nivel_risco",
}

FRACAO_MINIMA_DATAS = 0.5


class ErroLote(ValueError):
    pass


@dataclass(frozen=True)
class EspecificacaoLote:
    arquivo: str
    sha256: str
    ordem_colunas: tuple[str, ...] | None = None
    niveis_extras: Mapping[str, str] = field(default_factory=dict)
    nota: str = ""


@dataclass(frozen=True)
class ResultadoCarga:
    tabela: pd.DataFrame
    descartados: pd.DataFrame


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.replace("﻿", "").split())


def sha256_arquivo(caminho: Path) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def _nomear_colunas(cabecalho: list[str], espec: EspecificacaoLote) -> list[str]:
    if espec.ordem_colunas is not None:
        if sorted(espec.ordem_colunas) != sorted(COLUNAS) or len(cabecalho) != 4:
            raise ErroLote(f"{espec.arquivo}: ordem_colunas inválida no manifesto")
        return list(espec.ordem_colunas)
    nomes = []
    for bruto in cabecalho:
        chave = normalizar(bruto).upper()
        if chave not in ALIASES_CABECALHO:
            raise ErroLote(f"{espec.arquivo}: coluna desconhecida '{bruto.strip()}'")
        nomes.append(ALIASES_CABECALHO[chave])
    faltando = set(COLUNAS) - set(nomes)
    if faltando or len(nomes) != len(set(nomes)):
        raise ErroLote(f"{espec.arquivo}: colunas esperadas ausentes: {sorted(faltando)}")
    return nomes


def _converter_datas(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie.str.slice(0, 10), format="%d/%m/%Y", errors="coerce")


def _normalizar_niveis(serie: pd.Series, espec: EspecificacaoLote) -> pd.Series:
    extras = {normalizar(k).lower(): v for k, v in espec.niveis_extras.items()}
    conhecidos = {**config.NIVEIS_RISCO, **extras}
    chaves = serie.map(lambda v: normalizar(v).lower())
    desconhecidos = sorted(set(chaves) - set(conhecidos) - {""})
    if desconhecidos:
        raise ErroLote(f"{espec.arquivo}: nível de risco desconhecido: {desconhecidos}")
    return chaves.map(lambda c: conhecidos.get(c, ""))


def _normalizar_regionais(serie: pd.Series, espec: EspecificacaoLote) -> pd.Series:
    regionais = serie.map(lambda v: normalizar(v).upper())
    fora = sorted(set(regionais) - set(config.REGIONAIS) - {""})
    if fora:
        raise ErroLote(f"{espec.arquivo}: regional fora da lista: {fora}")
    return regionais


def ler_lote(caminho: Path, espec: EspecificacaoLote, hoje: date) -> ResultadoCarga:
    try:
        bruto = pd.read_csv(caminho, sep=";", dtype=str, encoding="utf-8-sig",
                            keep_default_na=False)
    except (OSError, UnicodeDecodeError, pd.errors.ParserError) as erro:
        raise ErroLote(f"{espec.arquivo}: não foi possível ler o arquivo ({erro})") from erro
    if bruto.shape[1] != 4:
        raise ErroLote(f"{espec.arquivo}: esperado 4 colunas, encontrado {bruto.shape[1]}")

    tabela = bruto.set_axis(_nomear_colunas(list(bruto.columns), espec), axis=1)
    tabela = tabela.apply(lambda col: col.str.strip())

    datas = _converter_datas(tabela["data"])
    preenchidas = tabela["data"] != ""
    if preenchidas.any() and datas[preenchidas].notna().mean() < FRACAO_MINIMA_DATAS:
        raise ErroLote(f"{espec.arquivo}: a coluna de data não contém datas; "
                       "confira a ordem das colunas")

    tabela = tabela.assign(
        regional=_normalizar_regionais(tabela["regional"], espec),
        nivel_risco=_normalizar_niveis(tabela["nivel_risco"], espec),
        data=datas,
        lote=espec.arquivo,
    )

    motivo = pd.Series("", index=tabela.index)
    motivo = motivo.mask(tabela["data"] > pd.Timestamp(hoje), "data_futura")
    motivo = motivo.mask(tabela["data"].isna(), "data_invalida")
    motivo = motivo.mask(tabela["nivel_risco"] == "", "nivel_vazio")
    motivo = motivo.mask(tabela["regional"] == "", "regional_vazia")
    motivo = motivo.mask(tabela["cod_vistoria"] == "", "codigo_vazio")

    validas = tabela[motivo == ""]
    validas = validas.assign(
        rotulo=validas["nivel_risco"].isin(config.NIVEIS_ROTULO_1).astype(int),
        id_vistoria=validas["cod_vistoria"] + "|" + validas["regional"] + "|"
        + validas["data"].dt.strftime("%Y-%m-%d"),
    )
    descartados = tabela.loc[motivo != "", ["cod_vistoria", "regional", "data", "lote"]]
    descartados = descartados.assign(motivo=motivo[motivo != ""])
    return ResultadoCarga(validas.reset_index(drop=True), descartados.reset_index(drop=True))


def ler_manifesto(arquivo: Path = config.ARQUIVO_LOTES) -> list[EspecificacaoLote]:
    dados = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    return [
        EspecificacaoLote(
            arquivo=item["arquivo"],
            sha256=item["sha256"],
            ordem_colunas=tuple(item["ordem_colunas"]) if item.get("ordem_colunas") else None,
            niveis_extras=item.get("niveis_extras", {}),
            nota=item.get("nota", ""),
        )
        for item in dados["lotes"]
    ]


def carregar_lotes(
    arquivo_lotes: Path = config.ARQUIVO_LOTES, hoje: date | None = None
) -> ResultadoCarga:
    hoje = hoje or date.today()
    pasta = Path(arquivo_lotes).parent
    resultados = []
    for ordem, espec in enumerate(ler_manifesto(arquivo_lotes)):
        caminho = pasta / espec.arquivo
        if sha256_arquivo(caminho) != espec.sha256:
            raise ErroLote(f"{espec.arquivo}: hash diferente do registrado no manifesto")
        lido = ler_lote(caminho, espec, hoje)
        resultados.append(ResultadoCarga(lido.tabela.assign(ordem_lote=ordem), lido.descartados))

    todas = pd.concat([r.tabela for r in resultados], ignore_index=True)
    ordenadas = todas.sort_values(["ordem_lote", "data"], kind="stable")
    duplicadas = ordenadas.duplicated("id_vistoria", keep="last")
    repetidas = ordenadas.loc[duplicadas, ["cod_vistoria", "regional", "data", "lote"]]
    descartados = pd.concat(
        [*(r.descartados for r in resultados), repetidas.assign(motivo="vistoria_repetida")],
        ignore_index=True,
    )
    unicas = ordenadas[~duplicadas].drop(columns="ordem_lote")
    return ResultadoCarga(unicas.reset_index(drop=True), descartados)
