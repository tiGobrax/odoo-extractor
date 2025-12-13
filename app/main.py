import os
import sys
from loguru import logger


def main() -> None:
    """
    Entrypoint único da aplicação.

    Decide o modo de execução com base na variável MODE:
    - MODE=service → sobe API (FastAPI)
    - MODE=job     → executa full extract (Cloud Run Job)
    """

    mode = os.getenv("MODE", "service").lower()

    logger.info(f"🔧 Inicializando aplicação em MODE={mode}")

    if mode == "service":
        logger.info("🌐 Iniciando API (FastAPI)")
        import uvicorn
        from app.api.app import app

        port = int(os.getenv("PORT", "8080"))

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
        )

    elif mode == "job":
        logger.info("🏗️ Iniciando FULL EXTRACT job")
        from app.jobs.full_extract_job import main as job_main

        job_main()

    else:
        logger.error(f"❌ MODE inválido: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
