import dataclasses
import datetime
import json
import typing
from unittest import mock

import botocore.exceptions
import pytest

import dynamizer
from dynamizer import errors


@dataclasses.dataclass(frozen=True)
class DemoClass(dynamizer.DynamiteModel):
    """A demo class for dynamite."""

    foobar: str
    barfoo: typing.Optional[str] = None
    some_int: typing.Optional[int] = None
    some_list: typing.List[str] = dataclasses.field(default_factory=list)
    some_dict: typing.Dict[str, str] = dataclasses.field(default_factory=dict)

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
        return None


def test_optional_but_set_values():
    """Optional values that are set should be tolerated without error."""
    demo = DemoClass(
        "my-string", barfoo="my-other-string", some_int=1, some_dict={"foo": "bar"}
    )

    result = DemoClass.inflate(demo.deflate())

    assert demo == result


def test_demo_class_save_new():
    """New records should be able to be saved, resulting in a serial of 1."""
    demo = DemoClass("my-string")
    client = mock.MagicMock()

    result = demo._base_save(client, "my-table-name")

    assert result.created_at is not None
    assert result.updated_at is not None
    assert result._serial > 0


def test_demo_class_save_old():
    """Old records should be able to be saved, resulting in a serial increment."""
    demo = DemoClass("my-string", barfoo=None, _serial=1)
    client = mock.MagicMock()
    client.update_item.return_value = {
        "Attributes": {"_serial": {"N": "12345"}, "_sequence": {"N": "42"}}
    }

    result = demo._base_save(client, "my-table-name")

    assert result.created_at is not None
    assert result.updated_at is not None
    assert result._serial == 12345
    assert result._sequence == 42
    assert result.barfoo is None


def test_demo_class_delete():
    """Should be able to delete without error."""
    demo = DemoClass("my-string")
    client = mock.MagicMock()

    demo._base_delete(client, "my-table-name")

    client.delete_item.assert_called_once()


def test_demo_class_inflate():
    """We should be able to inflate a dynamodb record into a class instance."""
    record = {
        "foobar": {"S": "fizuzz"},
        "created_at": {"S": "2022-06-28T03:08:00+00:00"},
        "updated_at": {"S": "2023-06-28T03:08:00+00:00"},
        "some_list": {"S": "[]"},
        "some_dict": {"S": "{}"},
    }

    record = DemoClass.inflate(record)

    expected = DemoClass(
        "fizuzz",
        created_at=datetime.datetime(2022, 6, 28, 3, 8, tzinfo=datetime.timezone.utc),
        updated_at=datetime.datetime(2023, 6, 28, 3, 8, tzinfo=datetime.timezone.utc),
    )
    assert record == expected


def test_demo_class_base_load_with_item():
    """We should be able to use the default loader to pull a record."""
    client = mock.MagicMock()
    client.get_item.return_value = {
        "Item": {
            "foobar": {"S": "fizuzz"},
            "created_at": {"S": "2022-06-28T03:08:00+00:00"},
            "updated_at": {"S": "2023-06-28T03:08:00+00:00"},
            "some_list": {"S": "[]"},
            "some_dict": {"S": "{}"},
            "_sequence": {"N": "42"},
        }
    }

    record = DemoClass._base_load(client, "my-table-name", "hash-key", "range-key")

    expected = DemoClass(
        "fizuzz",
        created_at=datetime.datetime(2022, 6, 28, 3, 8, tzinfo=datetime.timezone.utc),
        updated_at=datetime.datetime(2023, 6, 28, 3, 8, tzinfo=datetime.timezone.utc),
    )
    assert record == expected
    assert record._sequence == 42


def test_demo_class_base_load_without_item():
    """We should be able to use the default loader to pull a record."""
    client = mock.MagicMock()
    client.get_item.return_value = {}

    record = DemoClass._base_load(client, "my-table-name", "hash-key", "range-key")

    assert record is None


@dataclasses.dataclass(frozen=True)
class InnerClass:
    """An inner class for testing."""

    foo: str
    bar: str


@dataclasses.dataclass(frozen=True)
class HierarchicalClass(dynamizer.DynamiteModel):
    """A hierarchical class for testing."""

    foo: str
    bar: typing.List[InnerClass]

    def _serialize_bar(self) -> typing.Dict[str, typing.Any]:
        """Serialize the bar value."""
        return json.dumps([dataclasses.asdict(b) for b in self.bar])

    @classmethod
    def _deserialize_bar(cls, value: typing.Dict[str, typing.Any]) -> typing.List:
        """Deserialize the bar value."""
        return [InnerClass(**b) for b in json.loads(value)]


def test_hierarchical_class():
    """We should be able to serialize and deserialize hierarchical classes."""
    inner = InnerClass(foo="foo", bar="bar")
    outer = HierarchicalClass(foo="foo", bar=[inner])

    result = HierarchicalClass.inflate(outer.deflate())

    assert result == outer


@dataclasses.dataclass(frozen=True)
class FunnyClass(dynamizer.DynamiteModel):
    """A class that has unsupported types and doesn't build its own support."""

    funky: mock.MagicMock


def test_unsupported_type_encoding_errors():
    """When we are given an unsupported type to encode we should throw an error."""
    obj = FunnyClass(mock.MagicMock())

    with pytest.raises(errors.UnsupportedTypeError):
        obj.deflate()


def test_unsupported_type_decoding_errors():
    """When we are given an unsupported type to encode we should throw an error."""
    dynamo_format = {"funky": {"S": "magic"}}

    with pytest.raises(errors.UnsupportedTypeError):
        FunnyClass.inflate(dynamo_format)


def test_base_save_reraises_client_errors():
    """When the client raises an error we should reraise it."""
    demo = DemoClass("my-string")
    client = mock.MagicMock()
    response = {"Error": {"Code": "UnhandledException"}}
    client.update_item.side_effect = botocore.exceptions.ClientError(
        response, "update_item"
    )

    with pytest.raises(botocore.exceptions.ClientError):
        demo._base_save(client, "my-table-name")


def test_base_save_transforms_conditional_errors():
    """When the client raises an error we should reraise it."""
    demo = DemoClass("my-string")
    client = mock.MagicMock()
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}
    client.update_item.side_effect = botocore.exceptions.ClientError(
        response, "update_item"
    )

    with pytest.raises(errors.ConcurrentUpdateError):
        demo._base_save(client, "my-table-name")


def test_base_delete_reraises_client_errors():
    """When the client raises an error we should reraise it."""
    demo = DemoClass("my-string")
    client = mock.MagicMock()
    response = {"Error": {"Code": "UnhandledException"}}
    client.delete_item.side_effect = botocore.exceptions.ClientError(
        response, "delete_item"
    )

    with pytest.raises(botocore.exceptions.ClientError):
        demo._base_delete(client, "my-table-name")


def test_base_delete_transforms_conditional_errors():
    """When the client raises an error we should reraise it."""
    demo = DemoClass("my-string")
    client = mock.MagicMock()
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}
    client.delete_item.side_effect = botocore.exceptions.ClientError(
        response, "delete_item"
    )

    with pytest.raises(errors.ConcurrentUpdateError):
        demo._base_delete(client, "my-table-name")


def test_continue_from():
    """We should be able to continue from a previous state."""
    demo1 = DemoClass("my-string")
    demo2 = DemoClass("my-string", _serial=42)

    result = demo1.continue_from(demo2)

    assert demo1._serial != demo2._serial
    assert result._serial == demo2._serial
    assert result == demo1
