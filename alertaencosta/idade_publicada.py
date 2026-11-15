from __future__ import annotations

import argparse
import sys

import pandas as pd

from alertaencosta.fonte_chuva import BuscarJson, ErroColeta, buscar_json_http


def conferir(url: str, max_horas: float, agora: pd.Timestamp,
             buscar: BuscarJson = buscar_json_http) -> int:
    try:
        gerado_em = pd.Timestamp(buscar(url)["gerado_em"])
    except (ErroColeta, KeyError, ValueError) as erro:
        print(f"::error::Não foi possível ler a página publicada: {erro}")
        return 1
    idade = (agora - gerado_em) / pd.Timedelta(hours=1)
    if idade > max_horas:
        print(f"::error::A página publicada tem {idade:.0f} horas (limite {max_horas:g} horas).")
        return 1
    print(f"A página publicada tem {idade:.0f} horas; a próxima execução tenta de novo.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Falha se a página publicada estiver velha demais.")
    parser.add_argument("url")
    parser.add_argument("--max-horas", type=float, default=24)
    args = parser.parse_args(argv)
    return conferir(args.url, args.max_horas, pd.Timestamp.now(tz="UTC"))


if __name__ == "__main__":
    sys.exit(main())
