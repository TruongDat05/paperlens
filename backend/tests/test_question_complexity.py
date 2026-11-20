"""Tests for question complexity classification and output token calibration."""

import pytest
from backend.app.agent.complexity import determine_question_complexity


def test_question_complexity_overview():
    # Paper nghiên cứu vấn đề gì? -> 500–1.000 tokens
    c1 = determine_question_complexity("Paper này nghiên cứu vấn đề gì?")
    assert c1.category == "overview"
    assert c1.target_tokens_min == 500
    assert c1.target_tokens_max == 1000

    c2 = determine_question_complexity("Tóm tắt các đóng góp chính và motivation của bài báo")
    assert c2.category == "overview"
    assert c2.target_tokens_min == 500
    assert c2.target_tokens_max == 1000


def test_question_complexity_concept():
    # Giải thích một khái niệm -> 800–1.500 tokens
    c1 = determine_question_complexity("Self-attention là gì và định nghĩa như thế nào?")
    assert c1.category == "concept"
    assert c1.target_tokens_min == 800
    assert c1.target_tokens_max == 1500

    c2 = determine_question_complexity("Giải thích khái niệm Positional Encoding trong paper")
    assert c2.category == "concept"
    assert c2.target_tokens_min == 800
    assert c2.target_tokens_max == 1500


def test_question_complexity_methodology():
    # Phân tích methodology -> 1.500–3.000 tokens
    c1 = determine_question_complexity("Phân tích methodology và kiến trúc của Transformer")
    assert c1.category == "methodology"
    assert c1.target_tokens_min == 1500
    assert c1.target_tokens_max == 3000

    c2 = determine_question_complexity("Pipeline và thuật toán xử lý dữ liệu hoạt động như thế nào?")
    assert c2.category == "methodology"
    assert c2.target_tokens_min == 1500
    assert c2.target_tokens_max == 3000


def test_question_complexity_math_formula():
    # Giải thích công thức toán -> 2.000–4.000 tokens
    c1 = determine_question_complexity("Giải thích công thức toán học tính Scaled Dot-Product Attention")
    assert c1.category == "math_formula"
    assert c1.target_tokens_min == 2000
    assert c1.target_tokens_max == 4000

    c2 = determine_question_complexity("Phân tích phương trình đạo hàm và loss function của mô hình")
    assert c2.category == "math_formula"
    assert c2.target_tokens_min == 2000
    assert c2.target_tokens_max == 4000


def test_question_complexity_experimental_results():
    # Phân tích experimental results -> 2.000–4.000 tokens
    c1 = determine_question_complexity("Phân tích experimental results trong Table 1 và benchmark BLEU")
    assert c1.category == "experimental_results"
    assert c1.target_tokens_min == 2000
    assert c1.target_tokens_max == 4000

    c2 = determine_question_complexity("Đánh giá kết quả thực nghiệm và các bảng số liệu ablation study")
    assert c2.category == "experimental_results"
    assert c2.target_tokens_min == 2000
    assert c2.target_tokens_max == 4000


def test_question_complexity_paper_comparison():
    # So sánh 2–3 papers -> 3.000–5.000 tokens
    c1 = determine_question_complexity("So sánh bài báo này với paper Reformer và Longformer")
    assert c1.category == "paper_comparison"
    assert c1.target_tokens_min == 3000
    assert c1.target_tokens_max == 5000

    c2 = determine_question_complexity("Điểm khác biệt và ưu nhược điểm so với paper FlashAttention")
    assert c2.category == "paper_comparison"
    assert c2.target_tokens_min == 3000
    assert c2.target_tokens_max == 5000


def test_question_complexity_critical_review():
    # Critical review, limitations, research gaps -> 3.000–6.000 tokens
    c1 = determine_question_complexity("Critical review: Phân tích các limitations và research gaps của bài báo")
    assert c1.category == "critical_review"
    assert c1.target_tokens_min == 3000
    assert c1.target_tokens_max == 6000

    c2 = determine_question_complexity("Đánh giá phê bình các điểm yếu và thách thức chưa giải quyết được")
    assert c2.category == "critical_review"
    assert c2.target_tokens_min == 3000
    assert c2.target_tokens_max == 6000


def test_question_complexity_literature_review():
    # Literature review nhiều papers -> 5.000–10.000+ tokens
    c1 = determine_question_complexity("Thực hiện một bài literature review nhiều papers về Efficient Attention")
    assert c1.category == "literature_review"
    assert c1.target_tokens_min == 5000
    assert c1.target_tokens_max == 10000
    assert c1.max_output_tokens >= 10000

    c2 = determine_question_complexity("Tổng quan tài liệu và khảo sát các bài báo nghiên cứu về Sparse Transformer")
    assert c2.category == "literature_review"
    assert c2.target_tokens_min == 5000
    assert c2.target_tokens_max == 10000


def test_question_complexity_general_baseline():
    # Final answer baseline -> ~3.000 tokens
    c = determine_question_complexity("Làm rõ các khía cạnh lý thuyết và ứng dụng thực tiễn")
    assert c.category == "general"
    assert c.target_tokens_min == 2000
    assert c.target_tokens_max == 4000
    assert c.max_output_tokens == 5000
