import os
import sys
from loguru import logger


def main() -> None:
    """
    Entrypoint unico da aplicacao.

    Decide o modo de execucao com base na variavel MODE:
    - MODE=service -> sobe API (FastAPI)
    - MODE=job     -> executa extract via Cloud Run Job

    Em MODE=job, a variavel JOB_TYPE controla o fluxo:
    - JOB_TYPE=full (default)
    - JOB_TYPE=inc
    """

    mode = os.getenv("MODE", "service").lower()

    logger.info(f"Inicializando aplicacao em MODE={mode}")

    if mode == "service":
        logger.info("Iniciando API (FastAPI)")
        import uvicorn
        from app.api.app import app

        port = int(os.getenv("PORT", "8080"))

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
        )

    elif mode == "job":
        job_type = os.getenv("JOB_TYPE", "full").lower()
        logger.info(f"Iniciando JOB_TYPE={job_type}")

        if job_type == "full":
            from app.jobs.full_extract_job import main as job_main

            job_main()
        elif job_type == "inc":
            from app.jobs.incremental_job import main as job_main

            job_main()
        else:
            logger.error(f"JOB_TYPE invalido: {job_type}")
            sys.exit(1)

    else:
        logger.error(f"MODE invalido: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
