import dataclasses
import datetime
import json
import random
import re
import typing

import botocore.exceptions

from dynamizer import errors


_TYPE_ENCODERS = {
    int: lambda x: {"N": str(x)},
    float: lambda x: {"N": str(x)},
    str: lambda x: {"S": x},
    bool: lambda x: {"BOOL": x},
    datetime.datetime: lambda x: {"S": x.isoformat()},
    list: lambda x: {"S": json.dumps(x)},
    dict: lambda x: {"S": json.dumps(x)},
}

_TYPE_DECODERS = {
    int: lambda x: int(x["N"]),
    float: lambda x: float(x["N"]),
    str: lambda x: x["S"],
    bool: lambda x: x["BOOL"],
    datetime.datetime: lambda x: datetime.datetime.fromisoformat(x["S"]),
    list: lambda x: json.loads(x["S"]),
    dict: lambda x: json.loads(x["S"]),
}


def _find_coder(
    field: dataclasses.Field, coders: dict
) -> typing.Optional[typing.Callable]:
    """Find an encoder for the type of the given field."""
    if field.type in coders:
        return coders[field.type]
    base_type = typing.get_origin(field.type)
    if base_type is typing.Union and type(None) in typing.get_args(field.type):
        return coders[typing.get_args(field.type)[0]]
    return None


def _default_encode_value(field: dataclasses.Field, value: typing.Any) -> typing.Any:
    """Encode a value for dynamodb."""
    if encoder := _find_coder(field, _TYPE_ENCODERS):
        return encoder(value)
    raise errors.UnsupportedTypeError(
        f"Unsupported type {field.type} for field {field.name}"
        " consider defining a custom serializer by adding the following method:"
        f"`_serialize_{field.name}(self) -> str`"
    )


def _default_decode_value(
    field: dataclasses.Field, value: typing.Dict[str, typing.Any]
) -> typing.Any:
    """Decode a value from dynamodb."""
    if decoder := _find_coder(field, _TYPE_DECODERS):
        return decoder(value)
    raise errors.UnsupportedTypeError(
        f"Unsupported type {field.type} for field {field.name}"
        " consider defining a custom deserializer by adding the following method:"
        f"`_deserialize_{field.name}(self, value: dict) -> {field.type}`"
    )


@dataclasses.dataclass(kw_only=True, frozen=True)
class DynamiteModel:
    """Base class for dynamite models."""

    created_at: datetime.datetime = None
    updated_at: datetime.datetime = None
    _serial: int = dataclasses.field(compare=False, default=None)

    def __post_init__(self):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        if not self.created_at:
            object.__setattr__(self, "created_at", now_utc)
        if not self.updated_at:
            object.__setattr__(self, "updated_at", now_utc)

    def __get_hash_range_keys(self) -> dict:
        """Get the methods used for hash and range keys."""
        return {
            v: ({"S": getattr(self, v)()} if getattr(self, v)() is not None else None)
            for v in dir(self)
            if re.match(r"^_?gs\d+$", v)
        }

    def __get_field_update_args(self):
        """Get the update args associated with fields."""
        exclude = {"created_at", "_serial"}
        set_parts = ["#c = if_not_exists(#c, :c)"]
        remove_parts = []
        values = {}
        fields = {}

        for i, field in enumerate(dataclasses.fields(self)):
            if field.name in exclude:
                continue
            value = getattr(self, field.name)
            fields[f"#d{i}"] = field.name
            if value is None:
                remove_parts.append(f"#d{i}")
            else:
                set_parts.append(f"#d{i} = :d{i}")
                values[f":d{i}"] = self.__serialize_field(field)

        fields["#s"] = "_serial"
        if self._serial:
            values[":s"] = {"N": str(self._serial)}
        values[":ns"] = {"N": str(random.randint(1, 1_000_000_000_000))}
        set_parts.append("#s = :ns")

        fields["#c"] = "created_at"
        values[":c"] = {"S": self.created_at.isoformat()}

        return (set_parts, remove_parts, values, fields)

    def __get_secondary_key_update_args(self):
        """Get the update args associated with index keys."""
        remove_parts = []
        values = {}
        fields = {}
        keys = self.__get_hash_range_keys()
        for i, key in enumerate(keys):
            value = keys[key]
            fields[f"#k{i}"] = key
            if value is None:
                remove_parts.append(f"#k{i}")
            else:
                values[f":k{i}"] = keys[key]
        return (remove_parts, values, fields)

    def _base_update_args(self, table: str, force: bool):
        """Get the base update args for dynamo."""
        (sets, removes, values, fields) = self.__get_field_update_args()
        (rms, vls, flds) = self.__get_secondary_key_update_args()
        removes.extend(rms)
        values.update(vls)
        fields.update(flds)

        conditional_expression = "attribute_not_exists(#s)"
        update_expression = ""
        if removes:
            update_expression = f'{update_expression}REMOVE {", ".join(removes)}'
        update_expression = f'{update_expression} SET {", ".join(sets)}'
        if self._serial:
            conditional_expression = "#s = :s"
        result = {
            "TableName": table,
            "Key": self.__base_update_key_args(),
            "UpdateExpression": update_expression,
            "ConditionExpression": conditional_expression if not force else None,
            "ExpressionAttributeValues": values,
            "ExpressionAttributeNames": fields,
            "ReturnValues": "UPDATED_NEW",
        }
        return {k: v for k, v in result.items() if v is not None}

    @classmethod
    def inflate(cls, dynamo_record: dict) -> "DynamiteModel":
        """Inflate a record from dynamodb format to a python class."""
        values = {}
        for field in dataclasses.fields(cls):
            value = dynamo_record.get(field.name)
            values[field.name] = None
            if value is not None:
                values[field.name] = cls.__deserialize_field(field, value)
        return cls(**values)

    def deflate(self) -> dict:
        """Deflate a record from python class to dynamodb format."""
        return {
            field.name: self.__serialize_field(field)
            for field in dataclasses.fields(self)
            if getattr(self, field.name) is not None
        }

    def continue_from(self, prev: "DynamiteModel") -> "DynamiteModel":
        """
        Allow the model to continue from a previous state specified by `prev`.

        Dynamite models have a token to prevent writing over a previous update.
        If it is desired to start from a fresh model and overwrite existing state,
        then this can be used to enable it without requiring forcing.
        """
        return dataclasses.replace(self, _serial=prev._serial)

    def __base_update_key_args(self) -> dict:
        """Generate the key argument for a dynamo update operation."""
        return {
            "hash_key": {
                "S": (self.hash_key() if callable(self.hash_key) else self.hash_key)
            },
            "range_key": {
                "S": (self.range_key() if callable(self.range_key) else self.range_key)
            },
        }

    def _base_save(self, client, table: str, force: bool = False) -> "DynamiteModel":
        """Provide a default save function."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        to_save = dataclasses.replace(self, updated_at=now_utc)
        try:
            response = client.update_item(**to_save._base_update_args(table, force))
        except botocore.exceptions.ClientError as err:
            if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise errors.ConcurrentUpdateError()
            raise err
        return dataclasses.replace(
            to_save,
            _serial=int(response["Attributes"]["_serial"]["N"]),
        )

    def _base_delete(
        self,
        client,
        table: str,
    ):
        """Delete the record."""
        try:
            client.delete_item(
                TableName=table,
                Key={
                    "hash_key": {
                        "S": (
                            self.hash_key()
                            if callable(self.hash_key)
                            else self.hash_key
                        )
                    },
                    "range_key": {
                        "S": (
                            self.range_key()
                            if callable(self.range_key)
                            else self.range_key
                        )
                    },
                },
                ConditionExpression="#s = :s",
                ExpressionAttributeNames={"#s": "_serial"},
                ExpressionAttributeValues={":s": {"N": self._serial}},
            )
        except botocore.exceptions.ClientError as err:
            if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise errors.ConcurrentUpdateError()
            raise err

    @classmethod
    def _base_load(
        cls, client, table: str, hash_key: str, range_key: str
    ) -> typing.Optional["DynamiteModel"]:
        """Default load function given a specific hash and range key."""
        response = client.get_item(
            TableName=table,
            Key={"hash_key": {"S": hash_key}, "range_key": {"S": range_key}},
        )
        if "Item" not in response:
            return None
        return cls.inflate(response["Item"])

    def __serialize_field(
        self, field: dataclasses.Field
    ) -> typing.Dict[str, typing.Any]:
        """Serialize a single field, utilizing custom serializers where present."""
        custom_serializer = getattr(self, f"_serialize_{field.name}", None)
        if custom_serializer:
            return custom_serializer()
        value = getattr(self, field.name)
        return _default_encode_value(field, value)

    @classmethod
    def __deserialize_field(
        cls, field: dataclasses.Field, value: typing.Dict[str, typing.Any]
    ) -> typing.Any:
        """Deserialize a single field, utilizing custom deserializers where present."""
        custom_deserializer = getattr(cls, f"_deserialize_{field.name}", None)
        if custom_deserializer:
            return custom_deserializer(value)
        return _default_decode_value(field, value)
