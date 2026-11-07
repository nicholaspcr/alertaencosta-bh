from __future__ import annotations

import json
import sys
from pathlib import Path

from alertaencosta import config, versoes


def dados_como_funciona(versao: versoes.Versao, historico: list[dict]) -> dict:
    info = versao.info
    return {
        "versao_modelo": versao.id,
        "tipo_modelo": info["tipo"],
        "baseline_em_uso": info["baseline_em_uso"],
        "versao_dados": info["versao_dados"],
        "metricas_teste": info["metricas_teste"],
        "periodo_treino": info["periodo_treino"],
        "periodo_teste": info["periodo_teste"],
        "limiares": info["limiares"],
        "explicacao": info["explicacao"],
        "regional_ponto": {r: f"{config.PONTOS[p].nome} ({p})" for r, p in info["regional_ponto"].items()},
        "faixas_72h_mm": info["faixas_72h_mm"],
        "historico": historico,
        "atribuicao": config.ATRIBUICAO_OPEN_METEO,
        "contato": config.CONTATO,
        "comparacao_inmet": _comparacao_inmet(),
    }


def _comparacao_inmet() -> str | None:
    arquivo = config.ARQUIVO_COMPARACAO_INMET
    return arquivo.read_text(encoding="utf-8").strip() if arquivo.exists() else None


def publicar(id_versao: str, pasta_modelos: Path = config.DIR_MODELOS,
             pasta_site: Path = config.DIR_SITE) -> Path:
    historico = versoes.publicar(id_versao, pasta_modelos)
    versao = versoes.carregar(id_versao, pasta_modelos)
    destino = pasta_site / "como-funciona.json"
    destino.write_text(json.dumps(dados_como_funciona(versao, historico), ensure_ascii=False, indent=1)
                       + "\n", encoding="utf-8")
    return destino


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("uso: python -m alertaencosta.publicar <id-da-versao>", file=sys.stderr)
        return 2
    try:
        destino = publicar(argv[0])
    except versoes.ErroVersao as erro:
        print(f"Publicação recusada: {erro}", file=sys.stderr)
        return 1
    print(f"Versão vigente: {argv[0]}. Gerado {destino.relative_to(config.RAIZ)}. "
          "Faça commit e dispare o workflow 'estimativas' para atualizar a página.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
