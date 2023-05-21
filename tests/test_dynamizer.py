import dataclasses
import datetime
import json
import typing
from unittest import mock

import pytest

import dynamizer
from dynamizer import errors


@dataclasses.dataclass(frozen=True)
class DemoClass(dynamizer.DynamiteModel):
    """A demo class for dynamite."""

    foobar: str
    barfoo: typing.Optional[str] = None

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


def test_demo_class_save_new():
    """New records should be able to be saved, resulting in a serial of 1."""
    demo = DemoClass("my-string")
    client = mock.MagicMock()

    result = demo._base_save(client, "my-table-name")

    assert result.created_at is not None
    assert result.updated_at is not None
    assert result._serial == 1


def test_demo_class_save_old():
    """Old records should be able to be saved, resulting in a serial increment."""
    demo = DemoClass("my-string", barfoo=None, _serial=1)
    client = mock.MagicMock()

    result = demo._base_save(client, "my-table-name")

    assert result.created_at is not None
    assert result.updated_at is not None
    assert result._serial == 2
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
        }
    }

    record = DemoClass._base_load(client, "my-table-name", "hash-key", "range-key")

    expected = DemoClass(
        "fizuzz",
        created_at=datetime.datetime(2022, 6, 28, 3, 8, tzinfo=datetime.timezone.utc),
        updated_at=datetime.datetime(2023, 6, 28, 3, 8, tzinfo=datetime.timezone.utc),
    )
    assert record == expected


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

    @property
    def hash_key(self) -> str:
        """Get the hash key."""
        return f"hash-key"

    @property
    def range_key(self) -> str:
        """Get the range key."""
        return "/range-key"

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
    client = mock.MagicMock()

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
