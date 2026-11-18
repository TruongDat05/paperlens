"""Build a BM25 index and rank passages within one paper.

Accept chunked passages and a question. Return the lexical ranking for
B1, RRF fusion, and the product's BM25 fallback.
"""
