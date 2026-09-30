"""AI dependencies for FastAPI dependency injection."""

import logging

from langchain_openai import ChatOpenAI

from config.settings import Settings

settings = Settings.load()
logger = logging.getLogger(__name__)


def get_llm() -> ChatOpenAI:
    """Get LLM instance for dependency injection.

    Returns:
        ChatOpenAI: Configured LLM instance.

    """
    logger.info('Initializing LLM. Model: %s', settings.llm_settings.MODEL_NAME)
    return ChatOpenAI(  # type: ignore
        api_key=settings.llm_settings.OPENAI_API_KEY,  # type: ignore
        model=settings.llm_settings.MODEL_NAME,
        temperature=settings.llm_settings.TEMPERATURE,
        max_tokens=settings.llm_settings.MAX_TOKENS,
        # Every request through this client sends PHI (fax/medical
        # document images) for extraction. store=False opts out of
        # OpenAI's per-call logging/retention regardless of the org's
        # own default, since nothing here should be retained on their
        # side beyond serving the response.
        store=False,
    )
