from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import joblib

from alertaencosta import config


class ErroVersao(RuntimeError):
    pass


@dataclass(frozen=True)
class Versao:
    id: str
    modelo: object
    replicas: list
    info: dict


def novo_id(hoje: date, pasta: Path = config.DIR_MODELOS) -> str:
    base = f"modelo-{hoje:%Y.%m.%d}"
    candidato, sufixo = base, 2
    while (pasta / candidato).exists():
        candidato, sufixo = f"{base}-{sufixo}", sufixo + 1
    return candidato


def salvar(id_versao: str, modelo, replicas: list, info: dict, relatorio: str,
           pasta: Path = config.DIR_MODELOS) -> Path:
    destino = pasta / id_versao
    destino.mkdir(parents=True, exist_ok=False)
    joblib.dump(modelo, destino / "modelo.joblib")
    joblib.dump(replicas, destino / "replicas.joblib")
    (destino / "versao.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destino / "relatorio.md").write_text(relatorio, encoding="utf-8")
    return destino


def carregar(id_versao: str, pasta: Path = config.DIR_MODELOS) -> Versao:
    origem = pasta / id_versao
    arquivos = [origem / n for n in ("modelo.joblib", "replicas.joblib", "versao.json")]
    if not all(a.exists() for a in arquivos):
        raise ErroVersao(f"versão {id_versao} inexistente ou incompleta em {pasta}")
    return Versao(
        id=id_versao,
        modelo=joblib.load(arquivos[0]),
        replicas=joblib.load(arquivos[1]),
        info=json.loads(arquivos[2].read_text(encoding="utf-8")),
    )


def id_vigente(arquivo: Path = config.ARQUIVO_VIGENTE) -> str | None:
    if not arquivo.exists():
        return None
    return arquivo.read_text(encoding="utf-8").strip() or None


def carregar_vigente(pasta: Path = config.DIR_MODELOS) -> Versao:
    id_versao = id_vigente(pasta / "VIGENTE")
    if id_versao is None:
        raise ErroVersao("nenhuma versão vigente; rode o treino e publique uma versão")
    return carregar(id_versao, pasta)


def ler_historico(pasta: Path = config.DIR_MODELOS) -> list[dict]:
    arquivo = pasta / "historico.json"
    if not arquivo.exists():
        return []
    return json.loads(arquivo.read_text(encoding="utf-8"))


def publicar(id_versao: str, pasta: Path = config.DIR_MODELOS,
             agora: datetime | None = None) -> list[dict]:
    versao = carregar(id_versao, pasta)
    agora = agora or datetime.now(timezone.utc)
    entrada = {
        "versao": id_versao,
        "publicada_em": agora.isoformat(timespec="seconds"),
        "tipo": versao.info["tipo"],
        "baseline_em_uso": versao.info["baseline_em_uso"],
        "versao_dados": versao.info["versao_dados"],
        "auc_teste": versao.info["metricas_teste"][versao.info["tipo"]]["auc"],
        "brier_teste": versao.info["metricas_teste"][versao.info["tipo"]]["brier"],
    }
    historico = [*ler_historico(pasta), entrada]
    (pasta / "historico.json").write_text(
        json.dumps(historico, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (pasta / "VIGENTE").write_text(id_versao + "\n", encoding="utf-8")
    return historico
