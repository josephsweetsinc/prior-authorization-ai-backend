"""Tests for config.settings."""

from config.settings import DatabaseSettings, _normalize_db_url_for_asyncpg


class TestNormalizeDbUrlForAsyncpg:
    """Test suite for _normalize_db_url_for_asyncpg()."""

    def test_translates_sslmode_to_ssl(self):
        """Test that sslmode is translated to the ssl asyncpg accepts."""
        url = (
            'postgresql+asyncpg://user:pw@host/db'
            '?sslmode=require&channel_binding=require'
        )

        result = _normalize_db_url_for_asyncpg(url)

        assert 'sslmode' not in result
        assert 'channel_binding' not in result
        assert 'ssl=require' in result

    def test_url_without_query_string_is_unchanged(self):
        """Test that a plain URL with no query string passes through."""
        url = 'postgresql+asyncpg://user:pw@host/db'

        assert _normalize_db_url_for_asyncpg(url) == url

    def test_existing_ssl_param_is_not_overridden(self):
        """Test that an already-correct ssl param takes precedence."""
        url = 'postgresql+asyncpg://user:pw@host/db?sslmode=require&ssl=disable'

        result = _normalize_db_url_for_asyncpg(url)

        assert 'ssl=disable' in result
        assert 'sslmode' not in result

    def test_unrelated_query_params_are_preserved(self):
        """Test that other query params survive normalization."""
        url = 'postgresql+asyncpg://user:pw@host/db?sslmode=require&foo=bar'

        result = _normalize_db_url_for_asyncpg(url)

        assert 'foo=bar' in result
        assert 'sslmode' not in result


class TestDatabaseSettingsUrl:
    """Test suite for DatabaseSettings.url()."""

    def test_provided_url_is_normalized(self):
        """Test that a configured URL is normalized for asyncpg."""
        settings = DatabaseSettings(
            URL='postgresql+asyncpg://user:pw@host/db?sslmode=require',
        )

        assert settings.url() == (
            'postgresql+asyncpg://user:pw@host/db?ssl=require'
        )

    def test_builds_url_from_parts_with_ssl(self):
        """Test the individual-parameters fallback path."""
        settings = DatabaseSettings(
            URL=None,
            USER='user',
            PASSWORD='pw',
            HOST='host',
            PORT='5432',
            DB_NAME='db',
            SSL=True,
        )

        assert settings.url() == (
            'postgresql+asyncpg://user:pw@host:5432/db?ssl=require'
        )

    def test_builds_url_from_parts_without_ssl(self):
        """Test the individual-parameters path with SSL disabled."""
        settings = DatabaseSettings(
            URL=None,
            USER='user',
            PASSWORD='pw',
            HOST='host',
            PORT='5432',
            DB_NAME='db',
            SSL=False,
        )

        assert settings.url() == 'postgresql+asyncpg://user:pw@host:5432/db'
