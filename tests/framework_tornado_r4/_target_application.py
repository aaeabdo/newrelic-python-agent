import sys
import tornado.ioloop
import tornado.web
import tornado.gen
import tornado.httpclient
import tornado.curl_httpclient
import time


def dummy(*args, **kwargs):
    pass


class BadGetStatusHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("Hello, world")

    def get_status(self, *args, **kwargs):
        raise ValueError("OOPS")


class ProcessCatHeadersHandler(tornado.web.RequestHandler):
    def __init__(self, application, request, response_code=200, **kwargs):
        super(ProcessCatHeadersHandler, self).__init__(application, request,
                **kwargs)
        self.response_code = response_code

    def get(self, client_cross_process_id, txn_header, flush=None):
        import newrelic.api.transaction as _transaction
        txn = _transaction.current_transaction()
        if txn:
            txn._process_incoming_cat_headers(client_cross_process_id,
                    txn_header)

        if self.response_code != 200:
            self.set_status(self.response_code)
            return

        self.write("Hello, world")

        if flush == 'flush':
            # Force a flush prior to calling finish
            # This causes the headers to get written immediately. The tests
            # which hit this endpoint will check that the response has been
            # properly processed even though we send the headers here.
            self.flush()

            # change the headers to garbage
            self.set_header('Content-Type', 'garbage')


class EchoHeaderHandler(tornado.web.RequestHandler):
    def get(self):
        response = str(self.request.headers).encode('utf-8')
        self.write(response)


class AsyncExternalHandler(tornado.web.RequestHandler):
    @tornado.gen.coroutine
    def get(self, port, req_type, client_cls, count=1):
        count = int(count)
        if client_cls == 'AsyncHTTPClient':
            client = tornado.httpclient.AsyncHTTPClient()
        elif client_cls == 'CurlAsyncHTTPClient':
            client = tornado.curl_httpclient.CurlAsyncHTTPClient()
        elif client_cls == 'HTTPClient':
            client = tornado.httpclient.HTTPClient()
        else:
            raise ValueError("Received unknown client type: %s" % client_cls)

        uri = 'http://localhost:%s/echo-headers' % port
        if req_type == 'class':
            req = tornado.httpclient.HTTPRequest(uri)
        elif req_type == 'uri':
            req = uri
        else:
            raise ValueError("Received unknown request type: %s" % req_type)

        if client_cls == 'HTTPClient':
            for _ in range(count):
                response = client.fetch(req)
        else:
            futures = [client.fetch(req) for _ in range(count)]
            responses = yield tornado.gen.multi(futures)
            response = responses[0]
        self.write(response.body)


class InvalidExternalMethod(tornado.web.RequestHandler):
    @tornado.gen.coroutine
    def get(self, client_cls):
        if client_cls == 'AsyncHTTPClient':
            client = tornado.httpclient.AsyncHTTPClient()
        elif client_cls == 'CurlAsyncHTTPClient':
            client = tornado.curl_httpclient.CurlAsyncHTTPClient()
        elif client_cls == 'HTTPClient':
            client = tornado.httpclient.HTTPClient()
        else:
            raise ValueError("Received unknown client type: %s" % client_cls)

        port = self.request.server_connection.stream.socket.getsockname()[1]
        uri = 'http://localhost:%s' % port
        req = tornado.httpclient.HTTPRequest(uri, method='COOKIES')
        try:
            yield client.fetch(req)
        except KeyError:
            raise tornado.web.HTTPError(503)

        # we should never reach here
        self.write('Failed')


class InvalidExternalKwarg(tornado.web.RequestHandler):
    @tornado.gen.coroutine
    def get(self, client_cls):
        if client_cls == 'AsyncHTTPClient':
            client = tornado.httpclient.AsyncHTTPClient()
        elif client_cls == 'CurlAsyncHTTPClient':
            client = tornado.curl_httpclient.CurlAsyncHTTPClient()
        elif client_cls == 'HTTPClient':
            client = tornado.httpclient.HTTPClient()
        else:
            raise ValueError("Received unknown client type: %s" % client_cls)

        port = self.request.server_connection.stream.socket.getsockname()[1]
        uri = 'http://localhost:%s' % port

        try:
            yield client.fetch(uri, boop='1234')
        except TypeError:
            raise tornado.web.HTTPError(503)

        # we should never reach here
        self.write('Failed')


class SimpleHandler(tornado.web.RequestHandler):
    def get(self, fast=False):
        if not fast:
            time.sleep(0.1)
        self.write("Hello, world")

    def log_exception(self, *args, **kwargs):
        pass

    post = get
    put = get
    delete = get
    patch = get


class OnFinishHandler(SimpleHandler):
    def on_finish(self):
        time.sleep(0.1)


class CoroThrowHandler(tornado.web.RequestHandler):
    @tornado.gen.coroutine
    def get(self, fast=False):
        if not fast:
            yield tornado.gen.sleep(0.1)
        try:
            yield self.boom()
        except ValueError:
            pass
        self.write("Hello, world")

    @tornado.gen.coroutine
    def boom(self):
        raise ValueError('BOOM!')


class CoroHandler(tornado.web.RequestHandler):
    @tornado.gen.coroutine
    def get(self, fast=False):
        if not fast:
            yield tornado.gen.sleep(0.1)
        self.write("Hello, world")


class FakeCoroHandler(tornado.web.RequestHandler):
    @tornado.gen.coroutine
    def get(self, fast=False):
        if not fast:
            time.sleep(0.1)
        self.write("Hello, world")


class WebAsyncHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    def get(self, fast=False):
        io_loop = tornado.ioloop.IOLoop.current()
        io_loop.add_callback(self.done, fast=fast)

    def done(self, fast):
        if not fast:
            time.sleep(0.1)
        self.write("Hello, world")
        self.finish()


class InitializeHandler(tornado.web.RequestHandler):
    def initialize(self, *args, **kwargs):
        time.sleep(0.1)

    def get(self, fast=False):
        self.write("Hello, world")


class HTMLInsertionHandler(tornado.web.RequestHandler):
    HTML = """<html>
    <head>
        <meta charset="utf-8">
        <title>My Website</title>
    </head>
    <body>
        Hello World! There is no New Relic Browser here :(
    </body>
    </html>
    """

    def get(self):
        self.finish(self.HTML)


def make_app():
    handlers = [
        (r'/simple(/.*)?', SimpleHandler),
        (r'/coro(/.*)?', CoroHandler),
        (r'/coro-throw(/.*)?', CoroThrowHandler),
        (r'/fake-coro(/.*)?', FakeCoroHandler),
        (r'/web-async(/.*)?', WebAsyncHandler),
        (r'/init(/.*)?', InitializeHandler),
        (r'/html-insertion', HTMLInsertionHandler),
        (r'/on-finish(/.*)?', OnFinishHandler),
        (r'/bad-get-status', BadGetStatusHandler),
        (r'/force-cat-response/(\S+)/(\S+)/(\S+)', ProcessCatHeadersHandler),
        (r'/304-cat-response/(\S+)/(\S+)', ProcessCatHeadersHandler,
                {'response_code': 304}),
        (r'/204-cat-response/(\S+)/(\S+)', ProcessCatHeadersHandler,
                {'response_code': 204}),
        (r'/async-client/(\d+)/(\S+)/(\S+)/(\d+)', AsyncExternalHandler),
        (r'/async-client/(\d+)/(\S+)/(\S+)$', AsyncExternalHandler),
        (r'/client-invalid-method/(\S+)', InvalidExternalMethod),
        (r'/client-invalid-kwarg/(\S+)', InvalidExternalKwarg),
        (r'/echo-headers', EchoHeaderHandler),
    ]
    if sys.version_info >= (3, 5):
        from _target_application_native import (NativeSimpleHandler,
                NativeWebAsyncHandler)
        handlers.extend([
            (r'/native-simple(/.*)?', NativeSimpleHandler),
            (r'/native-web-async(/.*)?', NativeWebAsyncHandler),
        ])
    return tornado.web.Application(handlers, log_function=dummy)


if __name__ == "__main__":
    app = make_app()
    app.listen(8888, address='127.0.0.1')
    tornado.ioloop.IOLoop.current().start()
