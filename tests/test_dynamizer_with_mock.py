import dataclasses
import datetime

import boto3

import dynamizer
from dynamizer import mock as dynamizer_mock
from tests import _utils


@dataclasses.dataclass(frozen=True)
class DemoClass(dynamizer.DynamiteModel):
    """A demo class for dynamite."""

    @property
    def hash_key(self) -> str:
        """Get the hash key."""
        return f"/hash-key"

    @property
    def range_key(self) -> str:
        """Get the range key."""
        return "/range-key"

    @classmethod
    def load(cls):
        """Save the record."""
        client = boto3.client("dynamodb", region_name="us-east-1")
        return cls._base_load(client, "my-table-name", f"/hash-key", "/range-key")

    def save(self, serial: int = None):
        """Save the record."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        to_save = dataclasses.replace(self, updated_at=now_utc)
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.update_item(
            **to_save._base_update_args("my-table-name", new_serial=serial)
        )
        return dataclasses.replace(to_save, _serial=serial)


DYNAMO_SPEC = {
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


@_utils.patch_aws_credentials()
@dynamizer_mock.from_yaml(DYNAMO_SPEC)
def test_defined_serial_value():
    """Should be able to define the serial value."""
    demo = DemoClass()

    save_result = demo.save(serial=1234)
    load_result = demo.load()

    assert save_result._serial == 1234
    assert load_result == save_result
