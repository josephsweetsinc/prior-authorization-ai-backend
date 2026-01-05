"""Application settings and configuration management.

This module provides Pydantic-based settings classes for managing
application configuration from environment variables and .env files.
"""

import os
from functools import cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
"""Base directory of the project."""

env_mode = os.getenv('ENV', 'dev')
"""Current environment mode (dev, prod, etc.)."""

env_file = BASE_DIR / '.env'
"""Path to environment-specific .env file."""


class TokenSettings(BaseSettings):
    """Settings for JWT token generation and validation.

    All settings are prefixed with 'TOKEN_' in environment variables.

    Attributes:
        SECRET_KEY: Secret key for signing JWT tokens.
        ALGORITHM: Algorithm used for token signing (default: HS256).
        ACCESS_TOKEN_EXPIRE_MINUTES: Access token expiration time in minutes.
        REFRESH_TOKEN_EXPIRE_DAYS: Refresh token expiration time in days.

    """

    model_config = SettingsConfigDict(
        env_prefix='TOKEN_', env_file=env_file, extra='ignore'
    )

    SECRET_KEY: str = ''
    ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30


class DatabaseSettings(BaseSettings):
    """Settings for database connection.

    All settings are prefixed with 'DB_' in environment variables.
    Supports both full URL and individual connection parameters.

    Attributes:
        URL: Full database URL (optional, takes precedence if provided).
        USER: Database username.
        PASSWORD: Database password.
        HOST: Database host.
        PORT: Database port.
        DB_NAME: Database name.
        SSL: Whether to use SSL connection.

    """

    model_config = SettingsConfigDict(
        env_prefix='DB_', env_file=env_file, extra='ignore'
    )

    URL: str | None = None

    USER: str | None = None
    PASSWORD: str | None = None
    HOST: str | None = None
    PORT: str | None = None
    DB_NAME: str | None = None
    SSL: bool | None = None

    def _ssl(self) -> str:
        """Get SSL query parameter for database URL.

        Returns:
            SSL query parameter string if SSL is enabled, or empty string.

        """
        return '?sslmode=require' if self.SSL else ''

    def url(self) -> str:
        """Generate database connection URL.

        If URL is provided directly, returns it. Otherwise, constructs
        the URL from individual connection parameters.

        Returns:
            Database connection URL string.

        """
        if self.URL:
            return self.URL
        return f'postgresql+asyncpg://{self.USER}:{self.PASSWORD}@{self.HOST}:{self.PORT}/{self.DB_NAME}{self._ssl}'


class LoggingSettings(BaseSettings):
    """Settings for application logging.

    All settings are prefixed with 'LOGGING_' in environment variables.

    """

    model_config = SettingsConfigDict(
        env_prefix='LOGGING_', env_file=env_file, extra='ignore'
    )


class AwsSettings(BaseSettings):
    """Settings for AWS services (S3, etc.).

    All settings are prefixed with 'AWS_' in environment variables.
    In production, ACCESS_KEY_ID and SECRET_ACCESS_KEY may be None
    if using IAM roles.

    Attributes:
        ACCESS_KEY_ID: AWS access key ID (optional in production).
        SECRET_ACCESS_KEY: AWS secret access key (optional in production).
        REGION: AWS region (default: us-east-1).
        BUCKET_NAME: Name of the S3 bucket for file storage.

    """

    model_config = SettingsConfigDict(
        env_prefix='AWS_', env_file=env_file, extra='ignore'
    )

    ACCESS_KEY_ID: str | None = None
    SECRET_ACCESS_KEY: str | None = None
    REGION: str = 'us-east-1'
    BUCKET_NAME: str


class EmailSettings(BaseSettings):
    """Settings for email sending.

    All settings are prefixed with 'EMAIL_' in environment variables.

    Attributes:
        ADMIN_EMAIL: Admin email address for sending emails.
        SMTP_HOST: SMTP server host (optional, defaults to localhost).
        SMTP_PORT: SMTP server port (optional, defaults to 587).
        SMTP_USER: SMTP username (optional).
        SMTP_PASSWORD: SMTP password (optional).
        USE_TLS: Whether to use TLS (optional, defaults to True).

    """

    model_config = SettingsConfigDict(
        env_prefix='EMAIL_', env_file=env_file, extra='ignore'
    )

    ADMIN_EMAIL: str = ''
    SMTP_HOST: str = 'localhost'
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    USE_TLS: bool = True


class LLMSettings(BaseSettings):
    """Settings for LLM (Large Language Model) integration.

    All settings are prefixed with 'LLM_' in environment variables.

    Attributes:
        OPENAI_API_KEY: OpenAI API key for GPT models.
        MODEL_NAME: Name of the model to use (default: gpt-4.1).
        TEMPERATURE: Temperature for model responses (0.0 - 1.0).
        MAX_TOKENS: Maximum tokens for response.
        PDF_RENDER_DPI: DPI for rendering PDF pages to images.

    """

    model_config = SettingsConfigDict(
        env_prefix='LLM_', env_file=env_file, extra='ignore'
    )

    OPENAI_API_KEY: str = ''
    MODEL_NAME: str = 'gpt-4o-mini'
    TEMPERATURE: float = 0.0
    MAX_TOKENS: int = 4096
    PDF_RENDER_DPI: int = 150
    PDF_MAX_PAGES: int = 15


class Settings(BaseSettings):
    """Main application settings class.

    Aggregates all nested settings classes and provides top-level
    application configuration. Settings are loaded from environment
    variables and .env files based on the ENV variable.

    Attributes:
        API_TITLE: Title of the API (used in OpenAPI docs).
        API_VERSION: API version string (used in URL prefixes).
        ENV: Current environment (dev, prod, etc.).
        LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR).
        DEBUG: Whether debug mode is enabled.
        token_settings: Nested token configuration.
        database_settings: Nested database configuration.
        logging_settings: Nested logging configuration.
        aws_settings: Nested AWS configuration.
        email_settings: Nested email configuration.

    """

    model_config = SettingsConfigDict(
        env_file=env_file,
        env_file_encoding='utf-8',
        extra='ignore',
    )
    # Api version
    API_TITLE: str = 'Paai API'
    API_VERSION: str = 'v1'

    # Log level
    ENV: str = env_mode
    LOG_LEVEL: str = 'INFO'
    DEBUG: bool = False

    # Nested settings
    token_settings: TokenSettings = Field(default_factory=TokenSettings)
    database_settings: DatabaseSettings = Field(
        default_factory=DatabaseSettings
    )
    logging_settings: LoggingSettings = Field(default_factory=LoggingSettings)
    aws_settings: AwsSettings = Field(default_factory=AwsSettings)  # type: ignore
    email_settings: EmailSettings = Field(default_factory=EmailSettings)
    llm_settings: LLMSettings = Field(default_factory=LLMSettings)

    @classmethod
    @cache
    def load(cls) -> 'Settings':
        """Load and return a cached Settings instance.

        Uses functools.cache to ensure only one instance is created
        per process, improving performance and consistency.

        Returns:
            Settings: Cached Settings instance.

        """
        return cls()
