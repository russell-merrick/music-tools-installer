"""Command line for the music tools installer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from music_tools_installer import __version__
from music_tools_installer.catalog import load_catalog, version_newer
from music_tools_installer.installer import (
    default_data_dir,
    install_product,
    load_installed,
    remove_product,
    run_product,
    status_line,
    stop_product,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="music-tools-installer")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--catalog",
        default="catalog.json",
        help="catalog file or https URL (default: catalog.json)",
    )
    parser.add_argument("--data", type=Path, help="data directory (default: %LOCALAPPDATA%\\music-tools-installer)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="show catalog versions against what is installed")
    sub.add_parser("check", help="exit 1 when an installed app has a newer release")

    install = sub.add_parser("install", help="download one app and swap it into place")
    install.add_argument("id")
    install.add_argument("--force", action="store_true", help="reinstall even if the version is not newer")

    remove = sub.add_parser("remove", help="stop one app and delete its files")
    remove.add_argument("id")

    run = sub.add_parser("run", help="start one installed app")
    run.add_argument("id")

    stop = sub.add_parser("stop", help="stop one app")
    stop.add_argument("id")

    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1


def _run(args: argparse.Namespace) -> int:
    data_dir = args.data if args.data is not None else default_data_dir()
    if args.cmd == "stop":
        print(stop_product(args.id, data_dir))
        return 0
    if args.cmd == "remove":
        print(remove_product(args.id, data_dir))
        return 0

    products = load_catalog(args.catalog)
    by_id = {product.id: product for product in products}
    installed = load_installed(data_dir)

    if args.cmd == "list":
        for product in products:
            print(status_line(product, installed))
        return 0
    if args.cmd == "check":
        behind = [
            product
            for product in products
            if product.id in installed and version_newer(product.version, str(installed[product.id].get("version", "")))
        ]
        for product in products:
            print(status_line(product, installed))
        return 1 if behind else 0
    if args.cmd == "install":
        product = _require(by_id, args.id)
        print(install_product(product, data_dir, force=args.force))
        return 0
    if args.cmd == "run":
        product = _require(by_id, args.id)
        print(run_product(product, data_dir))
        return 0
    raise ValueError(f"unknown command: {args.cmd}")


def _require(by_id: dict, product_id: str):
    product = by_id.get(product_id)
    if product is None:
        known = ", ".join(by_id) or "(none)"
        raise ValueError(f"unknown product: {product_id} (catalog has {known})")
    return product


if __name__ == "__main__":
    raise SystemExit(main())
