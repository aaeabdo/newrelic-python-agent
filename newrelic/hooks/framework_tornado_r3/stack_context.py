import sys

from newrelic.agent import (wrap_function_wrapper, FunctionTrace,
    callable_name)
from six.moves import range
from .util import (record_exception, retrieve_current_transaction,
        replace_current_transaction)

def _nr_wrapper_stack_context_wrap_(wrapped, instance, args, kwargs):

    def _fxn_arg_extractor(fn, *args, **kwargs):
        # fn is the name of the callable argument in stack_context.wrap
        return fn

    fxn = _fxn_arg_extractor(*args, **kwargs)

    if fxn is None:
        return wrapped(*args, **kwargs)

    transaction_aware_fxn = _create_transaction_aware_fxn(fxn, args, kwargs)

    # If transaction_aware_fxn is None then it is either not being called in
    # the context of a transaction or it is already wrapped.
    # Either way we do not need to wrap this function.
    if not transaction_aware_fxn:
        return wrapped(*args, **kwargs)

    transaction = retrieve_current_transaction()

    # We replace the function we call in the callback with the transaction aware
    # version of the function.
    if len(args) > 0:
        args = list(args)
        args[0] = transaction_aware_fxn
    else:
        # Keyword argument name for the callable function is 'fn'.
        kwargs['fn'] = transaction_aware_fxn

    try:
        stack_context_wrapped_fxn = wrapped(*args, **kwargs)
        # Since our context aware function is wrapped by the stack context
        # wrapper function we label the newly wrapped function with our
        # transaction to keep track of it.
        stack_context_wrapped_fxn._nr_transaction = transaction
        return stack_context_wrapped_fxn
    except:  # Catch all.
        record_exception(transaction, sys.exc_info())
        raise

def _create_transaction_aware_fxn(fxn, args, kwargs):
    # Returns a version of fxn that will switch context to the appropriate
    # transaction and then restore the previous transaction on exit.
    # If fxn is already transaction aware or if there is no transaction
    # associated with fxn, this will return None.

    # If fxn already has the stored transaction we don't want to rewrap it
    # since this is also cause Tornado's stack_context.wrap to rewrap it.
    # That Tornado method will also return the input fxn immediately if
    # previously wrapped.

    if hasattr(fxn, '_nr_transaction'):
        return None

    # We want to get the transaction associated with this path of execution
    # whether or not we are actively recording information about it.
    transaction = retrieve_current_transaction()

    # A transaction will be None for fxns scheduled on the ioloop not
    # associated with a transaction.
    if transaction is None:
        return None

    def _transaction_aware_fxn(*fxn_args, **fxn_kwargs):
        old_transaction = replace_current_transaction(transaction)
        name = callable_name(fxn)
        with FunctionTrace(transaction, name=name):
            ret = fxn(*fxn_args, **fxn_kwargs)
        replace_current_transaction(old_transaction)
        return ret

    return _transaction_aware_fxn

# This allows us to capture all exceptions that get swallowed by the ioloop.
# If we instrument the exception handler directly this will cause us to call
# record exception twice. However, this is ok because we in
# transaction.record_exception we filter repeats.
def _nr_wrapper_ExceptionStackContext__init__(wrapped, instance, args, kwargs):

    assert instance is not None

    result = wrapped(*args, **kwargs)

    # instance is now an initiated ExceptionStackContext object.
    instance.exception_handler = _wrap_exception_handler(instance.exception_handler)

    return result

def _wrap_exception_handler(exception_handler):

    # QUESTION: Should I be using functools.wraps or some wrapt equivalent?
    def _wrapped_exception_handler(type, value, traceback):
        is_exception_swallowed = exception_handler(type, value, traceback)

        if is_exception_swallowed:
            transaction = retrieve_current_transaction()
            if transaction is not None:
                record_exception(transaction, (type, value, traceback))

        return is_exception_swallowed

    return _wrapped_exception_handler

def instrument_tornado_stack_context(module):
    wrap_function_wrapper(module, 'wrap', _nr_wrapper_stack_context_wrap_)
    wrap_function_wrapper(module, 'ExceptionStackContext.__init__',
            _nr_wrapper_ExceptionStackContext__init__)
