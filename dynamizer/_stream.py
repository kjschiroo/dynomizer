import dataclasses
import datetime
import enum
import typing


from . import errors
from . import _models


class ChangeType(enum.Enum):
    """An enumeration of the types of changes that can occur in a dynamodb table."""

    INSERT = "INSERT"
    MODIFY = "MODIFY"
    REMOVE = "REMOVE"


def _identify_model_class(
    keys: dict, image: dict, candidates: typing.List[type]
) -> type:
    """Identify the model class of an image."""
    for cls in candidates:
        obj = cls.inflate(image)
        for key in ("hash_key", "range_key"):
            try:
                key_getter = getattr(obj, key, lambda: None)
                key_val = key_getter() if callable(key_getter) else key_getter
            except:
                # We don't want to have a poisoned class break
                # the whole thing.
                break
            if key_val is None or keys[key]["S"] != key_val:
                break
        else:
            return cls
    raise errors.ModelNotFoundError("Could not identify the model class of the image.")


@dataclasses.dataclass(kw_only=True, frozen=True)
class StreamedChange:
    """A summary of a change from a dynamodb change stream."""

    # The model class of the item that changed
    model_class: type
    # The type of change, one of "INSERT", "MODIFY", "REMOVE"
    type: ChangeType
    # The new image of the item, if the change is an INSERT or MODIFY
    new: _models.DynamiteModel = None
    # The old image of the item, if the change is a MODIFY or REMOVE
    old: _models.DynamiteModel = None
    # The time the change was made
    timestamp: datetime.datetime

    @classmethod
    def from_change_record(cls, record: dict) -> "StreamedChange":
        """
        Create a StreamedChange from a dynamodb change stream record.

        Take a record from the dynamodb change stream and inflate it,
        identifying the associated class and creating the new and old
        version of the model if they exist.
        """
        stream_record = record["dynamodb"]
        if stream_record["StreamViewType"] != "NEW_AND_OLD_IMAGES":
            raise errors.UnsupportedStreamModeError(
                "StreamedChange requires NEW_AND_OLD_IMAGES stream view type but got "
                f"{stream_record['StreamViewType']}. This can be set when creating the "
                "dynamodb table change stream."
            )
        subs = [cls for cls in _models.DynamiteModel.__subclasses__()]
        image = stream_record.get("NewImage") or stream_record.get("OldImage")
        model_cls = _identify_model_class(stream_record["Keys"], image, subs)
        new = (
            model_cls.inflate(stream_record.get("NewImage"))
            if "NewImage" in stream_record
            else None
        )
        old = (
            model_cls.inflate(stream_record.get("OldImage"))
            if "OldImage" in stream_record
            else None
        )
        return cls(
            model_class=model_cls,
            type=ChangeType(record["eventName"]),
            new=new,
            old=old,
            timestamp=datetime.datetime.fromtimestamp(
                stream_record["ApproximateCreationDateTime"], tz=datetime.timezone.utc
            ),
        )
