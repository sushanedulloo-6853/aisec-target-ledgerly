"""Monthly narrative report (HTML + PDF)."""

import calendar
from collections import defaultdict

import jinja2
import markdown
from flask import render_template
from fpdf import FPDF

from ledgerly import llm

NARRATIVE_PROMPT = """You are a fractional CFO writing the monthly bookkeeping summary for {business}, {month_label}.
Write 3-5 short paragraphs in markdown for the owner: how the month went, notable expenses, cash position, and
one or two practical suggestions. Keep figures exact by using these placeholders instead of typing numbers:
{{{{ totals.revenue }}}}, {{{{ totals.expenses }}}}, {{{{ totals.net }}}}, {{{{ totals.transaction_count }}}},
and {{{{ categories['<Category>'] }}}} for a category total.

Figures (USD): revenue {revenue}, expenses {expenses}, net {net}.
Expenses by category: {categories}
Largest transactions:
{largest}
{focus}"""


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def gather(conn, business_id: int, month: str) -> dict:
    year, mon = (int(p) for p in month.split("-"))
    start = f"{year:04d}-{mon:02d}-01"
    end = f"{year:04d}-{mon:02d}-{calendar.monthrange(year, mon)[1]:02d}"
    rows = conn.execute(
        "SELECT * FROM transactions WHERE business_id = ? AND posted_at BETWEEN ? AND ? ORDER BY posted_at",
        (business_id, start, end),
    ).fetchall()
    revenue = sum(r["amount_cents"] for r in rows if r["amount_cents"] > 0)
    expenses = -sum(r["amount_cents"] for r in rows if r["amount_cents"] < 0)
    categories: dict[str, int] = defaultdict(int)
    for r in rows:
        if r["amount_cents"] < 0:
            categories[r["category"] or "Uncategorized"] += -r["amount_cents"]
    largest = sorted(rows, key=lambda r: abs(r["amount_cents"]), reverse=True)[:8]
    return {
        "month": month,
        "month_label": f"{calendar.month_name[mon]} {year}",
        "rows": [dict(r) for r in rows],
        "largest": [dict(r) for r in largest],
        "totals_cents": {"revenue": revenue, "expenses": expenses, "net": revenue - expenses},
        "totals": {
            "revenue": _money(revenue),
            "expenses": _money(expenses),
            "net": _money(revenue - expenses),
            "transaction_count": len(rows),
        },
        "categories": {k: _money(v) for k, v in sorted(categories.items(), key=lambda kv: -kv[1])},
    }


def write_narrative(business: dict, data: dict, focus: str | None) -> str:
    prompt = NARRATIVE_PROMPT.format(
        business=business["name"],
        month_label=data["month_label"],
        revenue=data["totals"]["revenue"],
        expenses=data["totals"]["expenses"],
        net=data["totals"]["net"],
        categories=", ".join(f"{k}: {v}" for k, v in data["categories"].items()) or "none",
        largest="\n".join(
            f"- {r['posted_at']} {r['description']} {_money(r['amount_cents'])}" for r in data["largest"]
        ),
        focus=f"\nThe owner asked you to focus on: {focus}" if focus else "",
    )
    resp = llm.respond("reports", input=prompt, max_output_tokens=1500)
    return resp.output_text


def render_narrative(narrative: str, business: dict, data: dict) -> str:
    filled = jinja2.Environment().from_string(narrative).render(
        totals=data["totals"], categories=data["categories"], business=business, month=data["month_label"]
    )
    return filled


def build_html(business: dict, data: dict, narrative_text: str) -> str:
    return render_template(
        "reports/monthly.html",
        business=business,
        data=data,
        narrative_html=markdown.markdown(narrative_text),
    )


def build_pdf(business: dict, data: dict, narrative_text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _latin1(f"{business['name']} - {data['month_label']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    t = data["totals"]
    pdf.cell(0, 8, f"Revenue {t['revenue']}   Expenses {t['expenses']}   Net {t['net']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.multi_cell(0, 6, _latin1(narrative_text.replace("**", "").replace("#", "")))
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Expenses by category", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for name, total in data["categories"].items():
        pdf.cell(0, 6, _latin1(f"{name}: {total}"), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _latin1(text: str) -> str:
    return text.encode("latin-1", errors="replace").decode("latin-1")
