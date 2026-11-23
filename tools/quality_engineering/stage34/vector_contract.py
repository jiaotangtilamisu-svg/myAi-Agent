"""Pure validation for copying already-existing vectors, with no I/O."""
import math

def validate_vectors(docs):
    if len(docs)!=61:
        raise ValueError('EXPECTED_61_APPROVED_LAW_CHUNKS')
    for row in docs:
        vector=row.get('_source',{}).get('embedding')
        if (not isinstance(vector,list) or len(vector)!=1024 or not any(vector)
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in vector)):
            raise ValueError('ES_SOURCE_VECTOR_MISSING_OR_INVALID')
