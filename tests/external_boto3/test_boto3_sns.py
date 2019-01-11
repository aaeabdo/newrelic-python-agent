import sys
import boto3
import moto

from newrelic.api.background_task import background_task
from testing_support.fixtures import validate_transaction_metrics

MOTO_VERSION = tuple(int(v) for v in moto.__version__.split('.'))

# patch earlier versions of moto to support py37
if sys.version_info >= (3, 7) and MOTO_VERSION <= (1, 3, 1):
    import re
    moto.packages.responses.responses.re._pattern_type = re.Pattern

AWS_ACCESS_KEY_ID = 'AAAAAAAAAAAACCESSKEY'
AWS_SECRET_ACCESS_KEY = 'AAAAAASECRETKEY'
AWS_REGION_NAME = 'us-east-1'
SNS_URL = 'sns-us-east-1.amazonaws.com'
EXCHANGE = 'arn:aws:sns:us-east-1:123456789012:some-topic'
sns_metrics = [('MessageBroker/boto3/SNSTopic/Publish/Named/%s' % EXCHANGE, 1)]


@validate_transaction_metrics('test_boto3_sns:test_publish_to_sns',
        scoped_metrics=sns_metrics, rollup_metrics=sns_metrics,
        background_task=True)
@background_task()
@moto.mock_sns
def test_publish_to_sns():
    conn = boto3.client('sns',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION_NAME)

    conn.create_topic(Name='some-topic')
    response = conn.list_topics()
    topic_arn = response["Topics"][0]['TopicArn']

    published_message = conn.publish(TopicArn=topic_arn, Message='my msg')
    assert 'MessageId' in published_message
