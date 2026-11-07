from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from alertaencosta import config
from alertaencosta.fonte_chuva import ErroColeta, FonteChuva, OpenMeteoHistorico
from alertaencosta.limpeza import maximos_historicos
from alertaencosta.rotulos import sha256_arquivo

MARGEM_DIAS = 31


def periodo_ingestao() -> tuple[pd.Timestamp, pd.Timestamp]:
    inicio = pd.Timestamp(config.INICIO_PERIODO - timedelta(days=MARGEM_DIAS), tz="UTC")
    fim = pd.Timestamp(config.FIM_PERIODO, tz="UTC") + pd.Timedelta(days=1)
    return inicio, fim


def baixar_serie(fonte: FonteChuva, inicio: pd.Timestamp, fim: pd.Timestamp) -> pd.DataFrame:
    partes = [fonte.leituras(codigo, inicio, fim).tabela for codigo in config.PONTOS]
    return pd.concat(partes, ignore_index=True)


def gravar_serie(serie: pd.DataFrame, fonte_nome: str, destino: Path, meta: Path) -> dict:
    destino.parent.mkdir(parents=True, exist_ok=True)
    saida = serie.assign(data_hora_utc=serie["data_hora_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    saida.to_csv(destino, index=False, float_format="%.2f")
    metadados = {
        "fonte": fonte_nome,
        "modelo_meteorologico": config.MODELO_METEOROLOGICO,
        "pontos": {c: {"nome": p.nome, "latitude": p.latitude, "longitude": p.longitude}
                   for c, p in config.PONTOS.items()},
        "inicio_utc": serie["data_hora_utc"].min().isoformat(),
        "fim_utc": serie["data_hora_utc"].max().isoformat(),
        "horas_sem_valor": {e: int(g["precipitacao_mm"].isna().sum())
                            for e, g in serie.groupby("estacao")},
        "maximos_mm": maximos_historicos(serie),
        "sha256": sha256_arquivo(destino),
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "atribuicao": config.ATRIBUICAO_OPEN_METEO,
    }
    meta.write_text(json.dumps(metadados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadados


def ler_serie(caminho: Path = config.ARQUIVO_SERIE) -> pd.DataFrame:
    serie = pd.read_csv(caminho, dtype={"estacao": str})
    return serie.assign(data_hora_utc=pd.to_datetime(serie["data_hora_utc"], utc=True))


def ler_metadados(caminho: Path = config.ARQUIVO_META_CHUVA) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def main() -> int:
    fonte = OpenMeteoHistorico()
    inicio, fim = periodo_ingestao()
    try:
        serie = baixar_serie(fonte, inicio, fim)
    except ErroColeta as erro:
        print(f"Falha na ingestão histórica: {erro}", file=sys.stderr)
        return 1
    meta = gravar_serie(serie, fonte.nome, config.ARQUIVO_SERIE, config.ARQUIVO_META_CHUVA)
    print(json.dumps({"linhas": len(serie), "chamadas": fonte.chamadas,
                      "horas_sem_valor": meta["horas_sem_valor"],
                      "maximos_mm": meta["maximos_mm"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
