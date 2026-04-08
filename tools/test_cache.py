import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from tools.cache_manager import CacheManager

def test():
    cache = CacheManager()
    
    query1 = "What is the death benefit for AIA Guaranteed Protect Plus III?"
    query2 = "What's the death benefit payout for AIA Guaranteed Protect Plus 3?" # Semantically similar
    
    print("--- Test 1: Canonical Extraction ---")
    key = cache.extract_canonical_key(query1)
    print(f"Query: {query1}")
    print(f"Extracted Key: {key}")
    
    print("\n--- Test 2: Store and Retrieve Layer A ---")
    answer = "The death benefit is 100% of the sum assured plus bonuses."
    cache.store_cache(query1, answer=answer, fragment="Death benefit section: ...")
    
    retrieved_answer = cache.get_answer(query1)
    print(f"Retrieved directly: {retrieved_answer}")
    assert retrieved_answer == answer
    
    print("\n--- Test 3: Semantic Fallback ---")
    key2 = cache.extract_canonical_key(query2)
    print(f"Query: {query2}")
    print(f"Extracted Key: {key2}")
    
    # Manually check similarity for debugging
    query1_vec = cache.embeddings.embed_query(query1)
    query2_vec = cache.embeddings.embed_query(query2)
    sim = cache._cosine_similarity(query1_vec, query2_vec)
    print(f"Manual Similarity Score: {sim:.4f}")

    semantic_answer = cache.get_answer(query2)
    print(f"Retrieved via semantic fallback for '{query2}':")
    print(f"Answer: {semantic_answer}")
    
    print("\n--- Test 4: Layer B (Fragment) ---")
    frag_data = cache.get_fragment(query1)
    if frag_data:
        print(f"Fragment found for ID {frag_data[0]}: {frag_data[1]}")
    
    print("\n--- Test 5: MD5 Sync and Invalidation ---")
    # This will check the raw_policies dir
    invalidated = cache.sync_and_invalidate()
    print(f"Policies invalidated/initialized: {invalidated}")
    
    # Try small modification to a dummy file if it exists
    # (Skipping destructive file modification for safety in test script)

if __name__ == "__main__":
    test()
