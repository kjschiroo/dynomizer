# Dynamizer

A supportive set of defaults for dynamodb. Dynamizer doesn't aim to
abstract away the nuances of dynamodb, but rather to provide effective
defaults for the repetitive tasks of (de)serializing models to and from
dynamodb.

It provides:

- Automatic deserialization from dynamo's format. This is helpful when
  processing a change stream from dynamo.
- Overwrite detection. If a model is changed between reading it and writing
  it back to dynamodb an error will be raised, preventing the unintentional
  overwriting of existing data.
- Supportive base delete, save, and load function to make a programmers life
  easier.

## Usage

Dynamizer models are built on top of immutable data classes.

```python
import dataclasses
import dynamizer


@dataclasses.dataclass(frozen=True)
class DemoClass(dynamizer.DynamiteModel):
    """A demo class."""

    foobar: str
    fizbuzz: typing.Optional[str] = None

    @property
    def hash_key(self) -> str:
        """
        Get the hash key.

        Dynamizer can't tell you what the right hash/range key scheme is
        write for your use case and access patterns so you must define
        how to translate the model's data into a hash and range key.
        """
        return f"hash-key/{self.foobar}"

    @property
    def range_key(self) -> str:
        """Get the range key."""
        return "/range-key"

    def _gs1(self) -> str:
        """
        Get the gs1 value.

        Dynamizer will also support you in instantiating any global secondary
        indices. It expects these to be defined matching the pattern
        `^_?gs\d+$`. Dynamizer searches the class for any functions matching
        this pattern and automatically manages their lifecycle within dynamodb,
        creating them dynamically as the model is saved, and deleting them
        if they are null in some part of the models life. Note that The index
        itself still needs to be created within dynamodb.
        """
        return f"{self.foobar}/hash-key"

    @classmethod
    def load(cls, my_identifier: typing.Any) -> "DemoClass":
        """
        Load a model from dynamodb.

        Dynamizer does not provide a default load function, since it doesn't
        know all of your specific access patterns and how incoming arguments
        are to be translated into a hash key, range key pair, but it does
        provide helpful secondary methods to make writing a load function
        easier.
        """
        hash_key = _hash_key(my_identifier)
        range_key = _hash_key(my_identifier)
        client = boto3.client("dynamodb")
        result = cls._base_load(client, "my-table-name", hash_key, range_key)
        if result is None:
            raise NotFoundError(f"Could not find {my_identifier}")
        return result

    @classmethod
    def list_group(cls, my_group: typing.Any) -> typing.List["DemoClass"]:
        """
        List a model under the specified group.

        Dynamizer provides methods for easily converting a dynamodb response
        into a python model making it easier to write functions defining a
        variety of access patterns.
        """
        ...
        response = client.query("Something fancy")
        return [cls.inflate(item) for item in response.get("Items", [])]


    def save(self) -> "DemoClass":
        """
        Save a model.

        Dynamizer keeps a count of changes to a model and checks when saving
        to ensure that no changes have come in since the model was initially
        read. This prevents data from being overwritten both during initial
        creation and during updates.
        """
        ...
        return self._base_save(client, "table_to_save_to")

    def delete(self):
        """
        Delete a model.

        Like during saves, Dynamizer keeps a count of changes and will prevent
        a delete from taking place if an update has taken place since the last
        read.
        """
        ...
        self._base_delete(client, "table_to_delete_from")
```

## Mocking

Dynamizer provides a mechanism for mocking out dynamodb calls for testing. The
initial state of dynamodb can be set via yaml files.

```python
import dynamizer.mock

data = yaml.safe_load("/path/to/data.yaml")

with dynamizer.mock.from_yaml(data):
    # Within this context dynamodb will have the state defined in data.yaml
```

The expected format of the yaml file is:

```yaml
- table_name: my-table-name
  region: us-east-1 # Optional
  secondary_indexes: # Optional
    - name: gs1-gs2
      hash_key: gs1
      range_key: gs2
  objects:
    MyDynamizerSubCls:
      - foo: {S: bar}
        fiz: {S: buzz}
    AnotherDynamizerSubCls:
      - mock: {S: data}
```