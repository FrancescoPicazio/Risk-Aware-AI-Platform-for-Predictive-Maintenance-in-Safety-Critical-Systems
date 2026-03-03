import logging


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    logger.info("[MONITORING & DRIFT DETECTION CONTAINER ONLINE]")

    try:
        while True:
            logger.info("Monitoring & Drift Detection: executing monitoring tasks...")
    except KeyboardInterrupt:
        logger.info("Monitoring & Drift stopped")
