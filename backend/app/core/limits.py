"""Enforce input limits, quotas, and inference budgets.

Check the size of the paper, question, and history. Enforce rate,
concurrency, and quota limits from the product policy.

Reserve budget in a transaction before calling FPT or the gateway,
including agent searches. Reconcile usage per attempt and retain unknown
status when the cost cannot be determined.
"""
