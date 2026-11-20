#!/usr/bin/env python3
"""PaperLens Model Usage and Token Tracking CLI.

Displays aggregated token usage, calls, and metrics across models and users
from the SQLite usage_ledger table.

Usage:
    python scripts/track_usage.py
    python scripts/track_usage.py --by-day
    python scripts/track_usage.py --by-user
    python scripts/track_usage.py --json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add repo root to python path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.db import get_connection


def format_num(val):
    return f"{val:,}" if isinstance(val, (int, float)) else str(val)


def print_table(headers, rows):
    if not rows:
        print("  (Không có dữ liệu)")
        return
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_str = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, col_widths)) + " |"

    print(sep)
    print(header_str)
    print(sep)
    for row in rows:
        row_str = "| " + " | ".join(str(val).rjust(w) if i >= 2 else str(val).ljust(w) for i, (val, w) in enumerate(zip(row, col_widths))) + " |"
        print(row_str)
    print(sep)


def get_model_summary(conn):
    query = """
    SELECT
        model,
        provider,
        COUNT(*) as total_calls,
        SUM(input_tokens) as in_tokens,
        SUM(output_tokens) as out_tokens,
        SUM(input_tokens + output_tokens) as total_tokens,
        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_calls,
        SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) as failed_calls
    FROM usage_ledger
    GROUP BY model, provider
    ORDER BY total_tokens DESC
    """
    return conn.execute(query).fetchall()


def get_daily_summary(conn):
    query = """
    SELECT
        SUBSTR(created_at, 1, 10) as date,
        model,
        COUNT(*) as total_calls,
        SUM(input_tokens) as in_tokens,
        SUM(output_tokens) as out_tokens,
        SUM(input_tokens + output_tokens) as total_tokens
    FROM usage_ledger
    GROUP BY date, model
    ORDER BY date DESC, total_tokens DESC
    """
    return conn.execute(query).fetchall()


def get_user_summary(conn):
    query = """
    SELECT
        owner_id,
        model,
        COUNT(*) as total_calls,
        SUM(input_tokens) as in_tokens,
        SUM(output_tokens) as out_tokens,
        SUM(input_tokens + output_tokens) as total_tokens
    FROM usage_ledger
    GROUP BY owner_id, model
    ORDER BY owner_id, total_tokens DESC
    """
    return conn.execute(query).fetchall()


def main():
    parser = argparse.ArgumentParser(description="PaperLens Model Usage and Token Tracker")
    parser.add_argument("--by-day", action="store_true", help="Group token usage by date and model")
    parser.add_argument("--by-user", action="store_true", help="Group token usage by user ID and model")
    parser.add_argument("--json", action="store_true", help="Output raw JSON data")
    args = parser.parse_args()

    conn = get_connection()

    if args.json:
        models = [dict(r) for r in get_model_summary(conn)]
        daily = [dict(r) for r in get_daily_summary(conn)]
        users = [dict(r) for r in get_user_summary(conn)]
        print(json.dumps({"by_model": models, "by_day": daily, "by_user": users}, indent=2, ensure_ascii=False))
        return

    print("\n" + "=" * 80)
    print(" 📊 BÁO CÁO TỔNG HỢP DUNG LƯỢNG TOKEN & MÔ HÌNH - PAPERLENS")
    print("=" * 80)

    if args.by_day:
        print("\n📅 THỐNG KÊ THEO NGÀY:")
        daily_rows = get_daily_summary(conn)
        table_data = []
        for r in daily_rows:
            table_data.append([
                r["date"],
                r["model"],
                format_num(r["total_calls"]),
                format_num(r["in_tokens"] or 0),
                format_num(r["out_tokens"] or 0),
                format_num(r["total_tokens"] or 0),
            ])
        print_table(["Ngày", "Model", "Số Calls", "Input Tokens", "Output Tokens", "Tổng Tokens"], table_data)

    elif args.by_user:
        print("\n👤 THỐNG KÊ THEO NGƯỜI DÙNG (OWNER):")
        user_rows = get_user_summary(conn)
        table_data = []
        for r in user_rows:
            table_data.append([
                r["owner_id"][:16] + "..." if len(r["owner_id"]) > 18 else r["owner_id"],
                r["model"],
                format_num(r["total_calls"]),
                format_num(r["in_tokens"] or 0),
                format_num(r["out_tokens"] or 0),
                format_num(r["total_tokens"] or 0),
            ])
        print_table(["Owner ID", "Model", "Số Calls", "Input Tokens", "Output Tokens", "Tổng Tokens"], table_data)

    else:
        # Default: Model overview
        print("\n🤖 THỐNG KÊ TỔNG QUAN THEO MODEL:")
        models_rows = get_model_summary(conn)
        table_data = []
        tot_calls = 0
        tot_in = 0
        tot_out = 0
        tot_all = 0
        for r in models_rows:
            in_t = r["in_tokens"] or 0
            out_t = r["out_tokens"] or 0
            all_t = r["total_tokens"] or 0
            calls = r["total_calls"] or 0
            tot_calls += calls
            tot_in += in_t
            tot_out += out_t
            tot_all += all_t
            table_data.append([
                r["model"],
                r["provider"],
                format_num(calls),
                format_num(in_t),
                format_num(out_t),
                format_num(all_t),
                f"{r['success_calls']}/{calls}",
            ])
        print_table(["Model", "Provider", "Số Calls", "Input Tokens", "Output Tokens", "Tổng Tokens", "Thành công"], table_data)
        print(f"\n👉 TỔNG CỘNG TOÀN HỆ THỐNG: {format_num(tot_calls)} requests | {format_num(tot_in)} Input Tokens | {format_num(tot_out)} Output Tokens | TỔNG CỘNG: {format_num(tot_all)} TOKENS\n")
        print("💡 Gợi ý lệnh:")
        print("   - Xem theo ngày:        python scripts/track_usage.py --by-day")
        print("   - Xem theo người dùng:  python scripts/track_usage.py --by-user")
        print("   - Xuất JSON:            python scripts/track_usage.py --json\n")


if __name__ == "__main__":
    main()
