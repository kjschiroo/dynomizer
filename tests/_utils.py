from unittest import mock


def patch_aws_credentials():
    """Mocked AWS Credentials to make sure we don't accidentally make any changes."""
    return mock.patch(
        "os.environ",
        {
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_SECURITY_TOKEN": "testing",
            "AWS_SESSION_TOKEN": "testing",
            "AWS_DEFAULT_REGION": "us-east-1",
        },
    )
