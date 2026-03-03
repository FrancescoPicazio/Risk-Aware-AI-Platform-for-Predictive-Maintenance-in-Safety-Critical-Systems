import logging


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    logger.info("[RISK & COST ASSESSMENT CONTAINER ONLINE]")

    try:
        while True:
            logger.info("Risk & Cost Assessment: executing risk and cost assessment tasks...")
    except KeyboardInterrupt:
        logger.info("Risk & Cost stopped")
