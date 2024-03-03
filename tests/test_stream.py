import dataclasses
import pathlib

import pytest
import yaml

from dynamizer import _stream
from dynamizer import _models


@dataclasses.dataclass(frozen=True)
class Alice(_models.DynamiteModel):
    value: str

    @property
    def hash_key(self) -> str:
        return "alice/hash_key"

    def range_key(self) -> str:
        return "alice/range_key"


@dataclasses.dataclass(frozen=True)
class Bob(_models.DynamiteModel):
    value: str

    @property
    def hash_key(self) -> str:
        return "bob/hash_key"

    def range_key(self) -> str:
        return "bob/range_key"


CLASSES = {"Alice": Alice, "Bob": Bob}


SCENARIO_DIR = pathlib.Path(__file__).parent / "stream_scenarios"
SCENARIOS = [f for f in SCENARIO_DIR.iterdir()]


@pytest.mark.parametrize("scenario_file", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_stream_scenarios(scenario_file: pathlib.Path):
    """Should be able to run the stream scenarios."""
    scenario = yaml.safe_load(scenario_file.read_text())
    raw_expected = scenario["expected"]
    expected = _stream.StreamedChange(
        model_class=CLASSES[raw_expected["model_class"]],
        type=_stream.ChangeType(raw_expected["type"]),
        new=(
            CLASSES[raw_expected["model_class"]](**raw_expected["new"])
            if raw_expected["new"]
            else None
        ),
        old=(
            CLASSES[raw_expected["model_class"]](**raw_expected["old"])
            if raw_expected["old"]
            else None
        ),
        timestamp=raw_expected["timestamp"],
    )

    result = _stream.StreamedChange.from_change_record(scenario["change_record"])

    assert result == expected


def test_non_existent_model():
    """Should raise a ValueError if the model class cannot be identified."""
    with pytest.raises(ValueError):
        _stream.StreamedChange.from_change_record(
            {
                "dynamodb": {
                    "StreamViewType": "NEW_AND_OLD_IMAGES",
                    "Keys": {
                        "hash_key": {"S": "nothing-matches-this"},
                        "range_key": {"S": "nothing-matches-this-either"},
                    },
                    "NewImage": {"value": {"S": "new-value"}},
                    "OldImage": {"value": {"S": "old-value"}},
                },
            }
        )


def test_bad_stream_view_type():
    """Should raise a ValueError if the stream view type is not NEW_AND_OLD_IMAGES."""
    with pytest.raises(ValueError):
        _stream.StreamedChange.from_change_record(
            {"dynamodb": {"StreamViewType": "NEW_IMAGE"}}
        )
