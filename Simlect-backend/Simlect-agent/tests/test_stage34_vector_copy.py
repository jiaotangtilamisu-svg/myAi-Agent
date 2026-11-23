"""Regression for ES9 omitting dense vectors from default _source responses."""
import pytest
from tools.quality_engineering.stage34.vector_contract import validate_vectors

def documents(vector):
    return [{'_source':{'content':'synthetic unit fixture','embedding':vector}} for _ in range(61)]

def test_explicit_vector_copy_accepts_existing_valid_vectors():
    validate_vectors(documents([1.0]+[0.0]*1023))

@pytest.mark.parametrize('count',[0,60,62])
def test_copy_cannot_claim_success_for_wrong_chunk_count(count):
    with pytest.raises(ValueError,match='EXPECTED_61'):
        validate_vectors(documents([1.0]+[0.0]*1023)[:count] if count<=61 else documents([1.0]+[0.0]*1023)+[{'_source':{}}])

@pytest.mark.parametrize('vector',[
    None,[],[0.0]*1024,[True]+[0.0]*1023,[1.0]*1023,
    [float('nan')]+[0.0]*1023,[float('inf')]+[0.0]*1023,['1']+[0.0]*1023,
])
def test_missing_or_invalid_source_vectors_fail_before_writing(vector):
    with pytest.raises(ValueError,match='MISSING_OR_INVALID'):
        validate_vectors(documents(vector))
