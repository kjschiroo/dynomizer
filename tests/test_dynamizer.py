import dataclasses
import datetime
import typing
from unittest import mock

import dynamizer


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

    result = demo._default_save(client, "my-table-name")

    assert result.created_at is not None
    assert result.updated_at is not None
    assert result._serial == 1


def test_demo_class_save_old():
    """Old records should be able to be saved, resulting in a serial increment."""
    demo = DemoClass("my-string", barfoo=None, _serial=1)
    client = mock.MagicMock()

    result = demo._default_save(client, "my-table-name")

    assert result.created_at is not None
    assert result.updated_at is not None
    assert result._serial == 2
    assert result.barfoo is None


def test_demo_class_delete():
    """Should be able to delete without error."""
    demo = DemoClass("my-string")
    client = mock.MagicMock()

    demo._default_delete(client, "my-table-name")

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


def test_demo_class_default_load_with_item():
    """We should be able to use the default loader to pull a record."""
    client = mock.MagicMock()
    client.get_item.return_value = {
        "Item": {
            "foobar": {"S": "fizuzz"},
            "created_at": {"S": "2022-06-28T03:08:00+00:00"},
            "updated_at": {"S": "2023-06-28T03:08:00+00:00"},
        }
    }

    record = DemoClass._default_load(client, "my-table-name", "hash-key", "range-key")

    expected = DemoClass(
        "fizuzz",
        created_at=datetime.datetime(2022, 6, 28, 3, 8, tzinfo=datetime.timezone.utc),
        updated_at=datetime.datetime(2023, 6, 28, 3, 8, tzinfo=datetime.timezone.utc),
    )
    assert record == expected


def test_demo_class_default_load_without_item():
    """We should be able to use the default loader to pull a record."""
    client = mock.MagicMock()
    client.get_item.return_value = {}

    record = DemoClass._default_load(client, "my-table-name", "hash-key", "range-key")

    assert record is None
