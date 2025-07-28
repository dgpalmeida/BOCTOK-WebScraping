from cx_Freeze import setup, Executable
import sys

base = None

if sys.platform == 'win32':
    base = "Win32GUI"


executables = [
    Executable(
        "WebScraping.py",
        base=base,
        icon="meu_icone.ico",
        target_name="Boctok.exe"
    )
]

build_exe_options = {
    "packages": ["os", "sys", "tkinter", "selenium", "bs4", "pandas", "numpy", "csv", "time", "getpass", "winsound", "html", "waitress", "flask_httpauth", "flask", "requests", "collections", "json"],
    "include_files": [
        'backend.py',
        'usuarios.csv',
        'tabela_extraida.html',
        'centrais.csv',
        'meu_icone.ico'
    ],
    "excludes": [],
    "include_msvcr": True
}

setup(
    name="WebScraping",
    version="2.0",
    description="WebsCraping para JFL",
    options={"build_exe": build_exe_options},
    executables=executables,
)