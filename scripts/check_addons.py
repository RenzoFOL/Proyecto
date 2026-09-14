from __future__ import annotations

import ast
import pathlib
import py_compile
import sys

from lxml import etree


ROOT = pathlib.Path(__file__).resolve().parents[1]
ADDONS = ROOT / "addons"
ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


for manifest_path in sorted(ADDONS.glob("*/__manifest__.py")):
    module = manifest_path.parent
    try:
        manifest = ast.literal_eval(manifest_path.read_text(encoding="utf-8"))
    except Exception as error:
        fail(f"{manifest_path}: manifest inválido: {error}")
        continue

    if not str(manifest.get("version", "")).startswith("19.0."):
        fail(f"{manifest_path}: la versión no es Odoo 19")
    if manifest.get("license") != "LGPL-3":
        fail(f"{manifest_path}: licencia inesperada")
    if not (module / "__init__.py").exists():
        fail(f"{module}: falta __init__.py")

    for relative_path in manifest.get("data", []):
        target = module / relative_path
        if not target.exists():
            fail(f"{manifest_path}: falta {relative_path}")

    for bundle_files in manifest.get("assets", {}).values():
        for asset in bundle_files:
            prefix = module.name + "/"
            target = ADDONS / asset if asset.startswith(prefix) else module / asset
            if not target.exists():
                fail(f"{manifest_path}: falta asset {asset}")


for python_path in sorted(ADDONS.rglob("*.py")):
    try:
        py_compile.compile(str(python_path), doraise=True)
    except py_compile.PyCompileError as error:
        fail(str(error))


safe_parser = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
    huge_tree=False,
)
for xml_path in sorted(ADDONS.rglob("*.xml")):
    try:
        etree.parse(str(xml_path), parser=safe_parser)
    except etree.XMLSyntaxError as error:
        fail(f"{xml_path}: {error}")


if ERRORS:
    print("\n".join(f"ERROR: {message}" for message in ERRORS), file=sys.stderr)
    raise SystemExit(1)

modules = sorted(path.parent.name for path in ADDONS.glob("*/__manifest__.py"))
print("Módulos verificados:", ", ".join(modules))
