"""Every registered HTTP error uses the shared view or safe JSON."""
import pytest
from werkzeug.exceptions import default_exceptions, TooManyRequests


@pytest.fixture
def error_client(app):
    @app.get('/_test/error/<int:code>')
    @app.get('/api/_test/error/<int:code>')
    def raise_error(code):
        raise default_exceptions[code](description='internal details must stay private')

    @app.get('/_test/retry')
    def retry():
        raise TooManyRequests(retry_after=60)

    @app.get('/_test/unexpected')
    def unexpected():
        raise RuntimeError('internal details must stay private')

    app.config['PROPAGATE_EXCEPTIONS'] = False
    return app.test_client()


@pytest.mark.parametrize('code', sorted(default_exceptions))
def test_all_http_error_pages_use_shared_style(error_client, code):
    response = error_client.get(f'/_test/error/{code}')
    assert response.status_code == code
    html = response.get_data(as_text=True)
    assert 'nf3-card' in html
    assert f'{code} ' in html
    assert 'Back to Home' in html
    assert 'internal details must stay private' not in html
    assert response.headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('code', sorted(default_exceptions))
def test_all_api_http_errors_are_json(error_client, code):
    response = error_client.get(f'/api/_test/error/{code}')
    assert response.status_code == code
    assert response.json['error']
    assert 'internal details must stay private' not in response.json['error']


def test_rate_limit_preserves_retry_after(error_client):
    response = error_client.get('/_test/retry')
    assert response.status_code == 429
    assert response.headers['Retry-After'] == '60'


def test_unexpected_exception_uses_safe_500_page(error_client):
    response = error_client.get('/_test/unexpected')
    assert response.status_code == 500
    html = response.get_data(as_text=True)
    assert 'nf3-card' in html and '500 Internal Server Error' in html
    assert 'internal details must stay private' not in html
