from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alertaencosta import config, modelos, versoes
from alertaencosta.atributos import SerieHoraria, faixa_72h, rotulo_faixa, tabela_atual
from alertaencosta.fonte_chuva import ErroColeta, FonteChuva, OpenMeteoRecente
from alertaencosta.limpeza import limpar_chuva

DIAS_JANELA_COLETA = config.DIAS_PASSADOS_RECENTE


@dataclass(frozen=True)
class Coleta:
    tabela: pd.DataFrame
    fonte: str
    chamadas: int


def coletar(fonte: FonteChuva, agora: pd.Timestamp) -> Coleta:
    inicio = agora - pd.Timedelta(days=DIAS_JANELA_COLETA)
    partes = [fonte.leituras(codigo, inicio, agora).tabela for codigo in config.PONTOS]
    return Coleta(pd.concat(partes, ignore_index=True), fonte.nome, getattr(fonte, "chamadas", 0))


def _iso(instante: pd.Timestamp | None) -> str | None:
    return None if instante is None else instante.isoformat().replace("+00:00", "Z")


def _acima_do_maximo_recente(bruta: pd.DataFrame, maximos: dict, agora: pd.Timestamp) -> dict[str, int]:
    recente = bruta[bruta["data_hora_utc"] > agora - pd.Timedelta(hours=72)]
    acima = recente["precipitacao_mm"] > recente["estacao"].map(maximos)
    return {p: int(acima[recente["estacao"] == p].sum()) for p in config.PONTOS}


def _acumulado(linha: pd.Series, nome: str, confiavel: bool) -> float | None:
    if not confiavel or linha[f"ausentes_{nome}"] > 0:
        return None
    return round(float(linha[nome]), 1)


def motivos_insuficiencia(linha: pd.Series, idade_h: float | None, acima_max: int,
                          vistorias_faixa: int) -> list[str]:
    motivos = []
    if idade_h is None or idade_h > config.IDADE_MAXIMA_HORAS:
        motivos.append(f"a última leitura de chuva tem mais de {config.IDADE_MAXIMA_HORAS} horas")
    if not linha["chuva_valida"]:
        motivos.append("faltam horas demais na série de chuva recente")
    if acima_max > 0:
        motivos.append("houve leitura de chuva acima do máximo histórico do ponto")
    if vistorias_faixa < config.MIN_VISTORIAS_FAIXA:
        motivos.append(f"há menos de {config.MIN_VISTORIAS_FAIXA} vistorias nesta regional "
                       "com chuva parecida")
    return motivos


def estimar(versao: versoes.Versao, coleta: Coleta, agora: pd.Timestamp) -> dict:
    info = versao.info
    maximos = info["maximos_chuva_mm"]
    limpeza = limpar_chuva(coleta.tabela, maximos, agora)
    acima = _acima_do_maximo_recente(coleta.tabela, maximos, agora)
    inicio = (agora - pd.Timedelta(days=DIAS_JANELA_COLETA)).floor("h")
    fim_grade = agora.floor("h")

    series, ultimas = {}, {}
    for ponto in config.PONTOS:
        do_ponto = limpeza.tabela[limpeza.tabela["estacao"] == ponto]
        series[ponto] = SerieHoraria.de_tabela(do_ponto, inicio, fim_grade)
        ultimas[ponto] = do_ponto["data_hora_utc"].max() if not do_ponto.empty else None
    fins = {p: (u if u is not None else fim_grade) for p, u in ultimas.items()}
    atual = tabela_atual(series, fins, agora)

    probs = modelos.probabilidade(versao.modelo, atual)
    baixos, altos = modelos.intervalo(versao.replicas, atual)
    limites = tuple(info["limiares"])

    regionais = []
    for i, linha in atual.iterrows():
        ponto = config.REGIONAL_PONTO[linha["regional"]]
        idade = None if ultimas[ponto] is None else (agora - ultimas[ponto]) / pd.Timedelta(hours=1)
        faixa = faixa_72h(linha["chuva_72h"])
        n_faixa = info["contagens_faixa_72h"][linha["regional"]][faixa]
        motivos = motivos_insuficiencia(linha, idade, acima[ponto], n_faixa)
        calculado = not motivos
        chuva_confiavel = ultimas[ponto] is not None and acima[ponto] == 0
        regionais.append({
            "regional": linha["regional"],
            "estado": "calculado" if calculado else "dados_insuficientes",
            "motivos": motivos,
            "nivel": modelos.nivel(probs[i], limites) if calculado else None,
            "probabilidade": round(float(probs[i]), 4) if calculado else None,
            "intervalo_95": [round(float(baixos[i]), 4), round(float(altos[i]), 4)] if calculado else None,
            "chuva_24h_mm": _acumulado(linha, "chuva_24h", chuva_confiavel),
            "chuva_72h_mm": _acumulado(linha, "chuva_72h", chuva_confiavel),
            "faixa_72h": rotulo_faixa(faixa),
            "vistorias_na_faixa": n_faixa,
            "ponto_chuva": f"{config.PONTOS[ponto].nome} ({ponto})",
            "ultima_leitura": _iso(ultimas[ponto]),
        })

    return {
        "gerado_em": _iso(agora.floor("s")),
        "versao_modelo": versao.id,
        "tipo_modelo": info["tipo"],
        "baseline_em_uso": info["baseline_em_uso"],
        "versao_dados": info["versao_dados"],
        "fonte_chuva": coleta.fonte,
        "atribuicao": config.ATRIBUICAO_OPEN_METEO,
        "aviso": config.AVISO,
        "idade_maxima_horas": config.IDADE_MAXIMA_HORAS,
        "limiares": list(limites),
        "ultima_leitura": {p: _iso(u) for p, u in ultimas.items()},
        "regionais": regionais,
        "_registro": {"leituras": {p: int((limpeza.tabela["estacao"] == p).sum()) for p in config.PONTOS},
                      "descartes": limpeza.descartes, "chamadas_open_meteo": coleta.chamadas},
    }


def gravar(estimativas: dict, saida: Path) -> None:
    publicado = {k: v for k, v in estimativas.items() if not k.startswith("_")}
    saida.parent.mkdir(parents=True, exist_ok=True)
    temporario = saida.with_suffix(".tmp")
    temporario.write_text(json.dumps(publicado, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    temporario.replace(saida)


def registrar(evento: dict) -> None:
    print(json.dumps(evento, ensure_ascii=False))


def executar(saida: Path, agora: pd.Timestamp, fonte: FonteChuva | None = None,
             carregar=versoes.carregar_vigente) -> int:
    base = {"execucao": _iso(agora.floor("s"))}
    try:
        versao = carregar()
        fonte = fonte or OpenMeteoRecente(agora=agora)
        coleta = coletar(fonte, agora)
        estimativas = estimar(versao, coleta, agora)
    except (ErroColeta, versoes.ErroVersao) as erro:
        registrar({**base, "sucesso": False, "erro": str(erro)})
        return 1
    gravar(estimativas, saida)
    registrar({**base, "sucesso": True, "versao_modelo": versao.id,
               "ultima_leitura": estimativas["ultima_leitura"], **estimativas["_registro"]})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ciclo B: coleta a chuva e gera estimativas.json.")
    parser.add_argument("--saida", type=Path, default=config.DIR_SITE / "estimativas.json")
    args = parser.parse_args(argv)
    return executar(args.saida, pd.Timestamp.now(tz="UTC"))


if __name__ == "__main__":
    sys.exit(main())
