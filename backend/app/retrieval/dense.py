"""Create E5 vectors and retrieve similar passages within one paper.

Use the "passage: " prefix for paragraph embeddings and "query: " for
question embeddings. Apply the same rules in the product and benchmark.

Check vector dimensions and model snapshots. Rank candidates by cosine
similarity or dot product on normalized vectors and return candidates
from the loaded paper.
"""
