import logging
import traceback

from newrelic.agent import callable_name, wrap_function_wrapper
from . import retrieve_request_transaction

_logger = logging.getLogger(__name__)

def _nr_wrapper_RequestHandler_on_finish_(wrapped, instance, args, kwargs):

    assert instance is not None

    request = instance.request

    if request is None:
        _logger.error('Runtime instrumentation error. Calling on_finish on '
                'a RequestHandler when no request is present. Please '
                'report this issue to New Relic support.\n%s',
                ''.join(traceback.format_stack()[:-1]))
        return wrapped(*args, **kwargs)

    transaction = retrieve_request_transaction(request)

    if transaction is None:
        _logger.error('Runtime instrumentation error. Calling on_finish on '
                'a RequestHandler when no transaction is present. Please '
                'report this issue to New Relic support.\n%s',
                ''.join(traceback.format_stack()[:-1]))
        return wrapped(*args, **kwargs)

    transaction._is_request_finished = True

    return wrapped(*args, **kwargs)

def _nr_wrapper_RequestHandler__execute_(wrapped, instance, args, kwargs):
    handler = instance
    request = handler.request

    # Check to see if we are being called within the context of any sort
    # of transaction. If we aren't, then we don't bother doing anything and
    # just call the wrapped function.

    transaction = retrieve_request_transaction(request)

    if transaction is None:
        return wrapped(*args, **kwargs)

    # If the method isn't one of the supported ones, then we expect the
    # wrapped method to raise an exception for HTTPError(405). Name the
    # transaction after the wrapped method first so it is used if that
    # occurs.

    name = callable_name(wrapped)
    transaction.set_transaction_name(name)

    if request.method not in handler.SUPPORTED_METHODS:
        return wrapped(*args, **kwargs)

    # Otherwise we name the transaction after the handler function that
    # should end up being executed for the request.

    name = callable_name(getattr(handler, request.method.lower()))
    transaction.set_transaction_name(name)

    return wrapped(*args, **kwargs)

def instrument_tornado_web(module):
    wrap_function_wrapper(module, 'RequestHandler.on_finish',
            _nr_wrapper_RequestHandler_on_finish_)
    wrap_function_wrapper(module, 'RequestHandler._execute',
            _nr_wrapper_RequestHandler__execute_)
