"""Offline installer for the reviewed Leyka add-ons; never edits the Odoo database."""
import argparse
import json
import shutil
import stat
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

MODULES = ("leyka_local_core", "leyka_pos_exchange", "leyka_cfdi_purchase")


def bundled_archive():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "Leyka_Local_Suite_Odoo19.zip"


def unpack_checked(archive, destination):
    seen = set()
    with zipfile.ZipFile(archive) as package:
        infos = package.infolist()
        if sum(info.file_size for info in infos) > 100 * 1024 * 1024:
            raise ValueError("El paquete supera el tamaño permitido.")
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            if (path.is_absolute() or not path.parts or ".." in path.parts
                    or "\\" in name or ":" in name or path.parts[0] not in MODULES
                    or stat.S_ISLNK(info.external_attr >> 16)):
                raise ValueError("Ruta no permitida en el paquete: " + name)
            if info.is_dir():
                continue
            if name.casefold() in seen:
                raise ValueError("Archivo duplicado en el paquete: " + name)
            seen.add(name.casefold())
            output = destination.joinpath(*path.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            with package.open(info) as source, output.open("wb") as target:
                shutil.copyfileobj(source, target)
    for module in MODULES:
        if not (destination / module / "__manifest__.py").is_file():
            raise ValueError("Paquete incompleto: " + module)


def install(archive, addons_directory):
    target = Path(addons_directory).resolve(strict=True)
    if not target.is_dir():
        raise ValueError("Selecciona la carpeta de addons de Odoo 19.")
    for module in MODULES:
        existing = target / module
        if existing.is_symlink() or (existing.exists() and not existing.is_dir()):
            raise ValueError("Destino no válido: " + str(existing))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = target.parent / "Leyka_respaldo" / stamp
    moved_old, installed = [], []
    with tempfile.TemporaryDirectory(prefix="leyka_stage_", dir=target.parent) as temporary:
        stage = Path(temporary)
        unpack_checked(archive, stage)
        backup.mkdir(parents=True, exist_ok=False)
        try:
            for module in MODULES:
                current = target / module
                if current.exists():
                    shutil.move(str(current), str(backup / module))
                    moved_old.append(module)
                shutil.move(str(stage / module), str(current))
                installed.append(module)
        except Exception:
            for module in reversed(installed):
                shutil.rmtree(target / module)
            for module in reversed(moved_old):
                shutil.move(str(backup / module), str(target / module))
            raise
        (backup / "instalacion.json").write_text(
            json.dumps({"destino": str(target), "modulos": MODULES,
                        "respaldo_de": moved_old}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return backup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "addons"
            target.mkdir()
            install(bundled_archive(), target)
            assert all((target / module / "__manifest__.py").exists() for module in MODULES)
        return

    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Leyka · Instalar módulos para Odoo 19 Community")
    root.geometry("700x410")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Leyka · Tienda local", font=("Segoe UI", 20, "bold")).pack(anchor="w")
    ttk.Label(frame, wraplength=640, text=(
        "Instala los módulos de cambios y vales, titulares y compras XML. "
        "Selecciona una carpeta incluida en addons_path de tu Odoo 19 Community. "
        "Conservaremos un respaldo de las versiones anteriores de estos tres módulos."
    )).pack(anchor="w", pady=(12, 18))
    location = tk.StringVar()
    ttk.Entry(frame, textvariable=location, width=84).pack(fill="x")
    ttk.Button(frame, text="Seleccionar carpeta addons…", command=lambda: location.set(
        filedialog.askdirectory(title="Carpeta addons de Odoo 19") or location.get()
    )).pack(anchor="w", pady=8)
    stopped = tk.BooleanVar()
    ttk.Checkbutton(frame, text="He respaldado mi base de datos y detenido Odoo para actualizar los archivos.",
                    variable=stopped).pack(anchor="w", pady=8)
    status = tk.StringVar(value="Después: reinicia Odoo y actualiza o instala los módulos desde Aplicaciones.")
    ttk.Label(frame, textvariable=status, wraplength=640).pack(anchor="w", pady=12)

    def perform():
        if not location.get() or not stopped.get():
            messagebox.showinfo("Antes de instalar", "Selecciona la carpeta y confirma el respaldo y cierre de Odoo.")
            return
        try:
            backup = install(bundled_archive(), location.get())
        except Exception as error:
            messagebox.showerror("Instalación incompleta", str(error))
            return
        status.set("Archivos instalados. Respaldo: " + str(backup))
        messagebox.showinfo("Archivos instalados", (
            "Reinicia el servicio Odoo. En modo desarrollador, actualiza la lista de aplicaciones.\n\n"
            "Instala/actualiza en este orden: Leyka Base Local, Leyka POS Cambios y Vales, Leyka Compras CFDI.\n\n"
            "Esta versión requiere pruebas en una copia de tu base antes de usarla en caja."
        ))

    ttk.Button(frame, text="Instalar archivos", command=perform).pack(anchor="e")
    root.mainloop()


if __name__ == "__main__":
    main()
