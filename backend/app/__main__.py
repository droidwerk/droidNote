import sys

# Módulos carregados só quando alguém usa a função (documentos do chat, fusos do
# calendário, upload). O PyInstaller pode deixá-los de fora sem ninguém notar:
# o build roda `droidnote-backend.exe --selfcheck` antes de empacotar o instalador.
SELFCHECK_MODULES = (
    "multipart",
    "dateutil.rrule",
    "tzdata",
    "openpyxl",
    "pypdf",
    "docx2txt",
    "langchain_text_splitters",
    "langchain_community.document_loaders.pdf",
    "langchain_community.document_loaders.word_document",
    "langchain_community.document_loaders.csv_loader",
    "langchain_community.document_loaders.text",
)


def selfcheck() -> int:
    import importlib
    from zoneinfo import ZoneInfo

    missing = []
    for name in SELFCHECK_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - qualquer falha de import conta
            missing.append(f"{name}: {exc}")
    try:
        ZoneInfo("America/Sao_Paulo")
    except Exception as exc:  # noqa: BLE001
        missing.append(f"zoneinfo: {exc}")
    try:
        import app.main  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        missing.append(f"app.main: {exc}")
    if missing:
        print("SELFCHECK_FAIL\n" + "\n".join(missing), flush=True)
        return 1
    print("SELFCHECK_OK", flush=True)
    return 0


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        sys.exit(selfcheck())
    from app.main import run

    run()
