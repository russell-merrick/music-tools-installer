"""Read a product catalog from a local file or a URL."""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_ID = re.compile(r"^[a-z][a-z0-9-]{0,40}$")


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    version: str
    url: str
    sha256: str
    port: int | None = None
    python: str | None = None
    entry: str | None = None


def load_catalog(source: str) -> list[Product]:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=30) as response:
            data = json.load(response)
    else:
        data = json.loads(Path(source).read_text(encoding="utf-8"))
    return parse_catalog(data)


def parse_catalog(data: object) -> list[Product]:
    if not isinstance(data, dict) or not isinstance(data.get("products"), list):
        raise ValueError("catalog must be an object with a products list")
    products: list[Product] = []
    seen: set[str] = set()
    for item in data["products"]:
        product = parse_product(item)
        if product.id in seen:
            raise ValueError(f"duplicate product id: {product.id}")
        seen.add(product.id)
        products.append(product)
    return products


def parse_product(item: object) -> Product:
    if not isinstance(item, dict):
        raise ValueError("each product must be an object")
    product_id = _required_str(item, "id")
    if not _ID.fullmatch(product_id):
        raise ValueError(f"invalid product id: {product_id}")
    version = _required_str(item, "version")
    port = item.get("port")
    if port is not None and (not isinstance(port, int) or isinstance(port, bool)):
        raise ValueError(f"{product_id}: port must be an integer")
    return Product(
        id=product_id,
        name=_required_str(item, "name"),
        version=version,
        url=_optional_str(item, "url"),
        sha256=_optional_str(item, "sha256").lower(),
        port=port,
        python=_optional_str(item, "python") or None,
        entry=_optional_str(item, "entry") or None,
    )


def version_newer(left: str, right: str) -> bool:
    """True when left is a newer dotted numeric version than right."""
    return _version_key(left) > _version_key(right)


def _version_key(value: str) -> tuple[int, ...]:
    parts = value.split(".")
    if not parts or not all(part.isdigit() for part in parts):
        raise ValueError(f"version must be dotted numbers: {value}")
    return tuple(int(part) for part in parts)


def _required_str(item: dict, key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"product {key} is required")
    return value.strip()


def _optional_str(item: dict, key: str) -> str:
    value = item.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"product {key} must be a string")
    return value.strip()
