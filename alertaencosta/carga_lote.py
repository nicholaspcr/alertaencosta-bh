from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

from alertaencosta import config
from alertaencosta.rotulos import EspecificacaoLote, ErroLote, ler_lote, sha256_arquivo


def adicionar_lote(origem: Path, ordem_colunas: tuple[str, ...] | None = None,
                   arquivo_lotes: Path = config.ARQUIVO_LOTES, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    manifesto = json.loads(arquivo_lotes.read_text(encoding="utf-8"))
    nome = origem.name
    if any(item["arquivo"] == nome for item in manifesto["lotes"]):
        raise ErroLote(f"{nome}: já existe um lote com esse nome no manifesto")
    espec = EspecificacaoLote(arquivo=nome, sha256=sha256_arquivo(origem), ordem_colunas=ordem_colunas)
    resultado = ler_lote(origem, espec, hoje)
    entrada = {"arquivo": nome, "sha256": espec.sha256,
               "nota": f"carregado em {hoje:%d/%m/%Y}; {len(resultado.tabela)} vistorias válidas"}
    if ordem_colunas:
        entrada["ordem_colunas"] = list(ordem_colunas)
    novo_manifesto = {**manifesto, "lotes": [*manifesto["lotes"], entrada]}
    shutil.copyfile(origem, arquivo_lotes.parent / nome)
    arquivo_lotes.write_text(json.dumps(novo_manifesto, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return entrada


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida e registra um novo lote de vistorias.")
    parser.add_argument("arquivo", type=Path)
    parser.add_argument("--ordem-colunas", default=None,
                        help="ordem real das colunas, se o cabeçalho estiver trocado")
    args = parser.parse_args(argv)
    ordem = tuple(args.ordem_colunas.split(",")) if args.ordem_colunas else None
    try:
        entrada = adicionar_lote(args.arquivo, ordem)
    except (ErroLote, OSError) as erro:
        print(f"Lote rejeitado: {erro}. A base vigente não foi alterada.", file=sys.stderr)
        return 1
    print(f"Lote aceito: {entrada}. Agora rode o retreino: make treino")
    return 0


if __name__ == "__main__":
    sys.exit(main())
