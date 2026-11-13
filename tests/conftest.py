import copy
import pytest
from studio.core import load
from pathlib import Path

@pytest.fixture
def project():
    return copy.deepcopy(load(Path(__file__).parents[1]/"studio/data/first-film.json"))
