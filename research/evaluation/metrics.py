"""Calculate retrieval metrics at the original-paragraph level.

Map subchunks to parents before computing Recall@5, Paragraph Evidence
F1@5, MRR@10, and Candidate Recall@20. Include only queries with valid
text evidence in the retrieval denominator.

For Recall@5 and F1@5, take the best score across valid reference sets
and macro-average by query. Estimate confidence intervals for
differences with paired bootstrap resampling by paper.
"""
