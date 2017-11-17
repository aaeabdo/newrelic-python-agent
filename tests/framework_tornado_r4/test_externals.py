import threading
from wsgiref.simple_server import make_server

import pytest
from testing_support.fixtures import (validate_transaction_metrics,
        override_application_settings)

from testing_support.mock_external_http_server import (
        MockExternalHTTPHResponseHeadersServer)


ENCODING_KEY = '1234567890123456789012345678901234567890'


@pytest.mark.parametrize('client_class',
        ['AsyncHTTPClient', 'CurlAsyncHTTPClient', 'HTTPClient'])
@pytest.mark.parametrize('cat_enabled', [True, False])
@pytest.mark.parametrize('request_type', ['uri', 'class'])
@pytest.mark.parametrize('num_requests', [1, 2])
def test_httpclient(app, cat_enabled, request_type, client_class,
        num_requests):

    if cat_enabled or ('Async' not in client_class):
        external = MockExternalHTTPHResponseHeadersServer()
        port = external.port
        uri = '/async-client/%s/%s/%s/%s' % (port, request_type, client_class,
                num_requests)
    else:
        port = app.get_http_port()
        uri = '/async-client/%s/%s/%s/%s' % (port, request_type, client_class,
                num_requests)

    expected_metrics = [
        ('External/localhost:%s/tornado.httpclient/GET' % port, num_requests)
    ]

    @override_application_settings(
            {'cross_application_tracer.enabled': cat_enabled})
    @validate_transaction_metrics(
        '_target_application:AsyncExternalHandler.get',
        rollup_metrics=expected_metrics,
        scoped_metrics=expected_metrics
    )
    def _test():
        if cat_enabled or ('Async' not in client_class):
            with external:
                response = app.fetch(uri)
        else:
            response = app.fetch(uri)

        assert response.code == 200

        if cat_enabled:
            # Check that we sent CAT headers
            required_headers = (b'X-NewRelic-ID', b'X-NewRelic-Transaction')
            forgone_headers = (b'X-NewRelic-App-Data',)

            sent_headers = response.body

            for header in required_headers:
                assert header in sent_headers, (header, sent_headers)

            for header in forgone_headers:
                assert header not in sent_headers, (header, sent_headers)
        else:
            sent_headers = response.body
            if hasattr(sent_headers, 'decode'):
                sent_headers = sent_headers.decode('utf-8')

            # new relic shouldn't add anything to the outgoing
            assert 'x-newrelic' not in sent_headers, sent_headers

    _test()


@pytest.mark.parametrize('client_class',
        ['AsyncHTTPClient', 'CurlAsyncHTTPClient', 'HTTPClient'])
@pytest.mark.parametrize('cat_enabled', [True, False])
@pytest.mark.parametrize('request_type', ['uri', 'class'])
def test_client_cat_response_processing(app, cat_enabled, request_type,
        client_class):
    _custom_settings = {
        'cross_process_id': '1#1',
        'encoding_key': ENCODING_KEY,
        'trusted_account_ids': [1],
        'cross_application_tracer.enabled': cat_enabled,
        'transaction_tracer.transaction_threshold': 0.0,
    }

    def _response_app(environ, start_response):
        status = '200 OK'
        # payload
        # (
        #     u'1#1', u'WebTransaction/Function/app:beep',
        #     0, 1.23, -1,
        #     'dd4a810b7cb7f937',
        #     False,
        # )
        response_headers = [('X-NewRelic-App-Data',
                'ahACFwQUGxpuVVNmQVVbRVZbTVleXBxyQFhUTFBfXx1SREUMV'
                'V1cQBMeAxgEGAULFR0AHhFQUQJWAAgAUwVQVgJQDgsOEh1UUlhGU2o='), ]
        start_response(status, response_headers)
        return [b'BEEEEEP']

    # always serve on a consistent port
    port = app.get_http_port()
    wsgi_port = port + 1
    uri = '/async-client/%s/%s/%s' % (wsgi_port, request_type, client_class)
    server = make_server('127.0.0.1', wsgi_port, _response_app)

    expected_metrics = [
        ('ExternalTransaction/localhost:%s/1#1/WebTransaction/'
                'Function/app:beep' % wsgi_port, 1 if cat_enabled else None),
    ]

    @validate_transaction_metrics(
        '_target_application:AsyncExternalHandler.get',
        rollup_metrics=expected_metrics,
        scoped_metrics=expected_metrics
    )
    @override_application_settings(_custom_settings)
    def _test():
        response = app.fetch(uri)
        assert response.code == 200

    server_thread = threading.Thread(target=server.handle_request)
    server_thread.start()
    _test()
    server_thread.join(0.1)


@pytest.mark.parametrize('client_class',
        ['AsyncHTTPClient', 'CurlAsyncHTTPClient', 'HTTPClient'])
@validate_transaction_metrics('_target_application:InvalidExternalMethod.get')
def test_httpclient_invalid_method(app, client_class):
    uri = '/client-invalid-method/%s' % client_class
    response = app.fetch(uri)
    assert response.code == 503


@pytest.mark.parametrize('client_class',
        ['AsyncHTTPClient', 'CurlAsyncHTTPClient', 'HTTPClient'])
@validate_transaction_metrics('_target_application:InvalidExternalKwarg.get')
def test_httpclient_invalid_kwarg(app, client_class):
    uri = '/client-invalid-kwarg/%s' % client_class
    response = app.fetch(uri)
    assert response.code == 503
