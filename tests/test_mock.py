import dataclasses
from unittest import mock

import pytest
import boto3
import botocore

import dynamizer
from dynamizer import errors
from dynamizer import mock as dynamizer_mock


@dataclasses.dataclass(frozen=True)
class DemoClass(dynamizer.DynamiteModel):
    """A demo class for dynamite."""

    foobar: str

    @property
    def hash_key(self) -> str:
        """Get the hash key."""
        return f"hash-key/{self.foobar}"

    @property
    def range_key(self) -> str:
        """Get the range key."""
        return "/range-key"

    def _gs1(self) -> str:
        """Get the gs1 value."""
        return f"{self.foobar}/hash-key"

    def _gs2(self) -> str:
        """Get the gs2 value."""
        return "/static"

    @classmethod
    def load(cls, foobar: str):
        """Save the record."""
        client = boto3.client("dynamodb", region_name="us-east-1")
        return cls._base_load(
            client, "my-table-name", f"hash-key/{foobar}", "/range-key"
        )

    def save(self):
        """Save the record."""
        client = boto3.client("dynamodb", region_name="us-east-1")
        return self._base_save(client, "my-table-name")


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


@patch_aws_credentials()
def test_from_yaml():
    """Should be able to mock the dynamodb environment."""
    dynamo_spec = {
        "region": "us-east-1",
        "table_name": "my-table-name",
        "secondary_indexes": [
            {"name": "gs1-gs2", "hash_key": "gs1", "range_key": "gs2"},
        ],
        "objects": {
            "DemoClass": [
                {"foobar": {"S": "my-string"}, "_serial": {"N": "1234"}},
            ],
        },
    }

    with dynamizer_mock.from_yaml(dynamo_spec):
        obj = DemoClass.load("my-string")
        assert obj is not None

        obj.save()
        with pytest.raises(errors.ConcurrentUpdateError):
            obj.save()

        not_obj = DemoClass.load("not-valid")
        assert not_obj is None

        new_obj = DemoClass("new-string")
        new_obj.save()
        loaded = DemoClass.load("new-string")
        assert loaded is not None
        resaved = loaded.save()
        assert len({new_obj._serial, loaded._serial, resaved._serial}) == 3
