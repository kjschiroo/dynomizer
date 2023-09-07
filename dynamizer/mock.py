import contextlib
import typing

import boto3
import moto

import dynamizer


def _create_tables(data: list):
    """Create the mock tables."""
    for table_data in data:
        client = boto3.client("dynamodb", region_name=table_data.get("region"))
        attrs = {
            key
            for i in table_data.get("secondary_indexes", [])
            for key in (i.get("hash_key"), i.get("range_key"))
            if key
        }
        attrs.add("hash_key")
        attrs.add("range_key")
        gsis = [
            {
                "IndexName": index["name"],
                "KeySchema": [
                    {"AttributeName": key, "KeyType": type_}
                    for key, type_ in [
                        (index.get("hash_key"), "HASH"),
                        (index.get("range_key"), "RANGE"),
                    ]
                    if key
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
            for index in table_data.get("secondary_indexes", [])
        ]
        gsi_args = {"GlobalSecondaryIndexes": gsis} if gsis else {}
        client.create_table(
            TableName=table_data["table_name"],
            AttributeDefinitions=[
                {"AttributeName": a, "AttributeType": "S"} for a in attrs
            ],
            KeySchema=[
                {"AttributeName": "hash_key", "KeyType": "HASH"},
                {"AttributeName": "range_key", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
            **gsi_args,
        )


def _fill_table(table_data: dict):
    """Fill the table with data."""
    subs = {cls.__name__: cls for cls in dynamizer.DynamiteModel.__subclasses__()}
    table = table_data["table_name"]
    for type_ in table_data.get("objects", {}):
        cls = subs[type_]
        for item in table_data["objects"][type_]:
            obj = cls.inflate(item)
            obj._base_save(
                boto3.client("dynamodb", region_name=table_data.get("region")),
                table,
                force=True,
            )


@contextlib.contextmanager
def from_yaml(data: dict):
    """Mock the dynamodb environment with the given data."""
    with moto.mock_dynamodb():
        if isinstance(data, dict):
            data = [data]
        _create_tables(data)
        for table_data in data:
            _fill_table(table_data)
        yield
