"""Định nghĩa dữ liệu paper, passage và retrieval dùng chung.

Mô tả Paper, Section, Passage và EvidenceResult cho backend và QASPER.
Passage mang ID riêng, parent_passage_id khi chia nhỏ và vị trí nguồn
theo loại HTML hoặc QASPER.

Sở hữu schema HTTP của session, ingest và retrieve. Các kiểu action,
observation và answer của agent được định nghĩa trong agent/schemas.py.
"""
