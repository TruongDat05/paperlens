"""Calibrate output token budget, retrieval focus, and explanation depth by question complexity.

Maps research question categories to target output token ranges according to the complexity matrix:
- Paper nghiên cứu vấn đề gì? (Overview): 500–1,000 tokens
- Giải thích một khái niệm (Concept): 800–1,500 tokens
- Phân tích methodology (Methodology): 1,500–3,000 tokens
- Giải thích công thức toán (Math formulas): 2,000–4,000 tokens
- Phân tích experimental results (Experiments): 2,000–4,000 tokens
- So sánh 2–3 papers (Comparison): 3,000–5,000 tokens
- Critical review, limitations, research gaps (Critical review): 3,000–6,000 tokens
- Literature review nhiều papers (Literature review): 5,000–10,000+ tokens
- Baseline / General research question: ~3,000 tokens (2,000–4,000 tokens)
"""

from typing import NamedTuple
import re
import unicodedata


class QuestionComplexity(NamedTuple):
    category: str
    label: str
    target_tokens_min: int
    target_tokens_max: int
    max_output_tokens: int
    retrieval_focus: str
    reasoning_focus: str
    synthesis_guidance: str


def _normalize(text: str) -> str:
    cleaned = text.lower().replace("đ", "d").replace("Đ", "d")
    return "".join(
        c for c in unicodedata.normalize("NFKD", cleaned)
        if not unicodedata.combining(c)
    )


def determine_question_complexity(question: str) -> QuestionComplexity:
    """Analyze the research question and calibrate the target output token budget and reasoning depth."""
    q = _normalize(question)

    # 1. Literature review nhiều papers (5.000–10.000+ tokens)
    if any(re.search(pat, q) for pat in [
        r"literature\s+review",
        r"tong\s+quan\s+tai\s+lieu",
        r"tong\s+hop.*(?:paper|bai\s+bao|nghien\s+cuu)",
        r"(?:nhieu|hang\s+loat|cac)\s+(?:paper|bai\s+bao|nghien\s+cuu)\s+ve",
        r"survey.*(?:paper|literature)",
        r"khao\s+sat.*(?:tai\s+lieu|bai\s+bao|paper)",
    ]):
        return QuestionComplexity(
            category="literature_review",
            label="Literature review nhiều papers",
            target_tokens_min=5000,
            target_tokens_max=10000,
            max_output_tokens=14000,
            retrieval_focus="Trích xuất các đoạn văn, bảng dữ liệu và phương pháp từ nhiều bài báo khoa học liên quan.",
            reasoning_focus="Phân tích tổng hợp, phân loại theo trường phái/hướng tiếp cận và đối chiếu kết luận giữa các bài báo.",
            synthesis_guidance=(
                "Viết một bài Literature Review toàn diện, cấu trúc rõ ràng với các chủ đề lớn, bảng tổng hợp so sánh, "
                "phân tích sự phát triển của các phương pháp, ưu nhược điểm của từng nhóm nghiên cứu và xu hướng tương lai. "
                "Độ dài mục tiêu: 5.000–10.000+ tokens, giải thích đầy đủ, trích dẫn rõ section/page và đính kèm link bài báo."
            ),
        )

    # 2. So sánh 2–3 papers (3.000–5.000 tokens)
    if any(re.search(pat, q) for pat in [
        r"so\s+sanh|compare|versus|\bvs\b",
        r"khac\s+gi|khac\s+nhau|diem\s+khac\s+biet",
        r"uu\s+nhuoc\s+diem\s+giua",
        r"so\s+voi\s+(?:paper|bai\s+bao|nghien\s+cuu)",
    ]):
        return QuestionComplexity(
            category="paper_comparison",
            label="So sánh 2–3 papers",
            target_tokens_min=3000,
            target_tokens_max=5000,
            max_output_tokens=6500,
            retrieval_focus="Trích xuất đúng các đoạn văn mô tả bài toán, kiến trúc, hàm mục tiêu và kết quả thực nghiệm của từng bài báo cần so sánh.",
            reasoning_focus="Đối chiếu song song các cơ chế kỹ thuật, đánh giá sự tương quan giữa các giả thuyết và kiểm chứng kết quả đối đầu.",
            synthesis_guidance=(
                "Trình bày bài so sánh chi tiết giữa các bài báo: nêu rõ bài toán chung, so sánh kiến trúc/methodology theo từng thành phần, "
                "phân tích bảng số liệu thực nghiệm đối đầu, chỉ ra các đánh đổi (trade-offs) về tốc độ/bộ nhớ/chính xác, và đính kèm link chính xác tới các paper. "
                "Độ dài mục tiêu: 3.000–5.000 tokens, giải thích đầy đủ, trích dẫn rõ section/page."
            ),
        )

    # 3. Critical review, limitations, research gaps (3.000–6.000 tokens)
    if any(re.search(pat, q) for pat in [
        r"critical\s+review",
        r"danh\s+gia\s+phe\s+binh|phe\s+binh",
        r"limitation|weakness|drawback",
        r"han\s+che|diem\s+yeu|nhuoc\s+diem",
        r"research\s+gap|gap\b|khoang\s+trong\s+nghien\s+cuu",
        r"thach\s+thuc|van\s+de\s+ton\s+tai|chua\s+giai\s+quyet",
    ]):
        return QuestionComplexity(
            category="critical_review",
            label="Critical review, limitations, research gaps",
            target_tokens_min=3000,
            target_tokens_max=6000,
            max_output_tokens=8192,
            retrieval_focus="Trích xuất các đoạn văn về giả định nghiên cứu, phần limitation, failure cases và phần thảo luận của tác giả.",
            reasoning_focus="Phân tích và đối chiếu kết luận với nguồn, mổ xẻ các giả định ngầm định, rủi ro kỹ thuật và kiểm định tính vững chắc của bằng chứng.",
            synthesis_guidance=(
                "Đưa ra Critical Review sâu sắc, đánh giá khách quan các đóng góp, phân tích cặn kẽ các hạn chế kỹ thuật (limitations), "
                "các điểm nghẽn về giả định/tính tổng quát hóa, và chỉ ra các khoảng trống nghiên cứu (research gaps) cụ thể. "
                "Độ dài mục tiêu: 3.000–6.000 tokens, giải thích đầy đủ, trích dẫn chính xác section/page."
            ),
        )

    # 4. Giải thích công thức toán (2.000–4.000 tokens)
    if any(re.search(pat, q) for pat in [
        r"cong\s+thuc|equation|formula",
        r"toan\s+hoc|mathematical",
        r"dao\s+ham|chung\s+minh|derivation|proof",
        r"ham\s+mat\s+mat|loss\s+function|objective\s+function",
        r"dinh\s+ly|theorem|lemma",
        r"ky\s+hieu|notation",
    ]):
        return QuestionComplexity(
            category="math_formula",
            label="Giải thích công thức toán",
            target_tokens_min=2000,
            target_tokens_max=4000,
            max_output_tokens=5500,
            retrieval_focus="Trích xuất đúng công thức toán học nguyên bản, các đoạn văn định nghĩa ký hiệu và ngữ cảnh diễn giải của tác giả.",
            reasoning_focus="Kiểm tra tính nhất quán toán học (chiều vector, quy ước ma trận), trực giác xác suất/hình học và đối chiếu từng bước biến đổi.",
            synthesis_guidance=(
                "Giải thích cặn kẽ công thức toán học: viết chuẩn LaTeX display/inline, định nghĩa từng ký hiệu trước khi dùng, "
                "phân tích trực giác bản chất toán học, diễn giải từng bước biến đổi toán học và nêu rõ vai trò của công thức trong toàn bộ thuật toán. "
                "Độ dài mục tiêu: 2.000–4.000 tokens, trích dẫn đúng số hiệu công thức và section/page."
            ),
        )

    # 5. Phân tích experimental results (2.000–4.000 tokens)
    if any(re.search(pat, q) for pat in [
        r"thuc\s+nghiem|experiment|experimental",
        r"ket\s+qua|results",
        r"bang\s+\d+|table\s+\d+|bang\s+so\s+lieu",
        r"bieu\s+do|chart|plot|figure\s+\d+",
        r"benchmark|baseline|ablation",
        r"metric|accuracy|f1|bleu|rouge|recall|precision|latency",
    ]):
        return QuestionComplexity(
            category="experimental_results",
            label="Phân tích experimental results",
            target_tokens_min=2000,
            target_tokens_max=4000,
            max_output_tokens=5500,
            retrieval_focus="Trích xuất đúng các bảng kết quả thực nghiệm, biểu đồ, con số thống kê cụ thể và đoạn văn mô tả thiết lập benchmark/ablation.",
            reasoning_focus="Đối chiếu các con số thực tế với tuyên bố của tác giả, phân tích ý nghĩa thống kê và kiểm tra xem kết luận có được hỗ trợ đầy đủ bởi dữ liệu không.",
            synthesis_guidance=(
                "Phân tích toàn diện kết quả thực nghiệm: tái hiện hoặc trích dẫn bảng số liệu chính, nêu rõ các dataset và baseline được so sánh, "
                "mổ xẻ kết quả ablation study để chứng minh đóng góp của từng thành phần, và đưa ra nhận xét khách quan. "
                "Độ dài mục tiêu: 2.000–4.000 tokens, trích dẫn chính xác Table/Figure và section/page."
            ),
        )

    # 6. Phân tích methodology (1.500–3.000 tokens)
    if any(re.search(pat, q) for pat in [
        r"methodology|phuong\s+phap",
        r"kien\s+truc|architecture",
        r"quy\s+trinh|pipeline|framework",
        r"thuat\s+toan|algorithm",
        r"hoat\s+dong\s+nhu\s+the\s+nao|cach\s+thuc\s+hoat\s+dong",
        r"co\s+che|mechanism",
        r"cac\s+buoc|flow",
    ]):
        return QuestionComplexity(
            category="methodology",
            label="Phân tích methodology",
            target_tokens_min=1500,
            target_tokens_max=3000,
            max_output_tokens=4500,
            retrieval_focus="Trích xuất đúng các đoạn văn phần Method, mô tả thuật toán, sơ đồ khối và các kỹ thuật thực thi then chốt.",
            reasoning_focus="Phân tích logic từng bước trong quy trình, liên kết các module thành phần và đối chiếu cơ chế với mục tiêu đề ra.",
            synthesis_guidance=(
                "Phân tích chuyên sâu về methodology: giải thích kiến trúc tổng quan, chi tiết từng thành phần/bước xử lý, thuật toán xử lý dữ liệu, "
                "và các kỹ thuật tối ưu đặc biệt được nhóm tác giả áp dụng. "
                "Độ dài mục tiêu: 1.500–3.000 tokens, giải thích đầy đủ, trích dẫn rõ section/page."
            ),
        )

    # 7. Giải thích một khái niệm (800–1.500 tokens)
    if any(re.search(pat, q) for pat in [
        r"khai\s+niem|concept",
        r"la\s+gi\b|dinh\s+nghia|definition",
        r"y\s+nghia\s+cua|the\s+nao\s+la",
        r"giai\s+thich.*(?:thuat\s+ngu|cum\s+tu)",
    ]):
        return QuestionComplexity(
            category="concept",
            label="Giải thích một khái niệm",
            target_tokens_min=800,
            target_tokens_max=1500,
            max_output_tokens=2500,
            retrieval_focus="Trích xuất định nghĩa chính thức của khái niệm trong bài báo, ngữ cảnh xuất hiện đầu tiên và ví dụ của tác giả.",
            reasoning_focus="Làm rõ trực giác đằng sau khái niệm, phân biệt với các khái niệm tương tự và đối chiếu với cách hiểu chuẩn trong chuyên ngành.",
            synthesis_guidance=(
                "Giải thích rõ ràng khái niệm được hỏi: nêu định nghĩa chính xác trong bài báo, trực giác cốt lõi, vai trò của nó trong toàn bộ nghiên cứu "
                "và đưa ra ví dụ minh họa trực quan. "
                "Độ dài mục tiêu: 800–1.500 tokens, có trích dẫn section/page xuất hiện khái niệm."
            ),
        )

    # 8. Paper nghiên cứu vấn đề gì? (500–1.000 tokens)
    if any(re.search(pat, q) for pat in [
        r"nghien\s+cuu.*van\s+de\s+gi|nghien\s+cuu.*cai\s+gi",
        r"bai\s+bao.*noi\s+ve\s+gi|bai\s+bao.*lam\s+gi",
        r"de\s+tai\s+gi|tom\s+tat|overview",
        r"what\s+problem|key\s+contributions",
        r"dong\s+gop\s+chinh|muc\s+tieu\s+chinh",
    ]):
        return QuestionComplexity(
            category="overview",
            label="Paper nghiên cứu vấn đề gì?",
            target_tokens_min=500,
            target_tokens_max=1000,
            max_output_tokens=1800,
            retrieval_focus="Trích xuất phần Abstract, Introduction (đoạn nêu vấn đề và đóng góp) và Conclusion.",
            reasoning_focus="Tổng hợp động lực nghiên cứu (motivation), điểm nghẽn của các nghiên cứu trước và giải pháp bài báo đề xuất.",
            synthesis_guidance=(
                "Tóm lược súc tích vấn đề cốt lõi mà bài báo nghiên cứu: bối cảnh và động lực (motivation), vấn đề/khoảng trống chưa giải quyết, "
                "giải pháp cốt lõi được đề xuất và 3–4 đóng góp chính của tác giả. "
                "Độ dài mục tiêu: 500–1.000 tokens, trích dẫn rõ section/page."
            ),
        )

    # 9. Mặc định: Phân tích nghiên cứu chuyên sâu (~3.000 tokens)
    return QuestionComplexity(
        category="general",
        label="Nghiên cứu chuyên sâu",
        target_tokens_min=2000,
        target_tokens_max=4000,
        max_output_tokens=5000,
        retrieval_focus="Trích xuất đúng đoạn văn, bảng số liệu, công thức liên quan từ các phần chính của bài báo.",
        reasoning_focus="Phân tích và đối chiếu kết luận với nguồn, kiểm tra tính vững chắc của bằng chứng trước khi khẳng định.",
        synthesis_guidance=(
            "Cung cấp câu trả lời hoàn chỉnh, sâu sắc và có cấu trúc: giải thích cặn kẽ cơ chế, trực giác, đối chiếu chặt chẽ với dữ liệu nguồn. "
            "Độ dài mục tiêu: ~3.000 tokens (trong khoảng 2.000–4.000 tokens), giải thích đầy đủ, có trích dẫn section/page rõ ràng."
        ),
    )
