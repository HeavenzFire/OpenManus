import asyncio

from app.agent.manus import Manus
from app.logger import logger


async def main():
    agent = Manus()
    try:
        prompt = input("Enter your prompt: ")
        if not prompt.strip():
            logger.warning("Empty prompt provided.")
            return

        logger.warning("Processing your request...")
        await agent.run(prompt)
        logger.info("Request processing completed.")
    except KeyboardInterrupt:
        logger.warning("Operation interrupted.")


def cli_main():
    """Synchronous entry point for the `openmanus` console script."""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
