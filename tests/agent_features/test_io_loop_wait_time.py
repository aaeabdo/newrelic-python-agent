import asyncio
import time
from newrelic.api.background_task import background_task
from testing_support.fixtures import validate_transaction_metrics


@background_task(name="block")
@asyncio.coroutine
def block_loop(ready, done):
    yield from ready.wait()
    time.sleep(0.1)
    done.set()


_wait_metrics_scoped = (
    ("IoLoop/Wait/OtherTransaction/Function/block", 1),
)
_wait_metrics_rollup = (
    ("IoLoop/Wait/all", 1),
    ("IoLoop/Wait/allOther", 1),
)


@background_task(name="wait")
@asyncio.coroutine
def wait_for_loop(ready, done):
    ready.set()
    yield from done.wait()


@validate_transaction_metrics(
    "wait",
    scoped_metrics=_wait_metrics_scoped,
    rollup_metrics=_wait_metrics_rollup,
    background_task=True,
)
def test_record_io_loop_wait():
    import asyncio

    ready, done = (asyncio.Event(), asyncio.Event())
    future = asyncio.gather(
        wait_for_loop(ready, done),
        block_loop(ready, done),
    )
    asyncio.get_event_loop().run_until_complete(future)
