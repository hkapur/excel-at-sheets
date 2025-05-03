import os
import re
import tempfile
import openpyxl
import io
import uuid
from flask import Flask, request, render_template, redirect, url_for, session, send_file, make_response, current_app
from dotenv import load_dotenv
from markupsafe import Markup
from markdown import markdown
from pathlib import Path
from werkzeug.utils import secure_filename

from helpers import (
    ask_about_spreadsheet,
    explain_formula,
    extract_cell,
    is_cell_reference,
    get_cell_value_across_sheets,
    extract_table_data_all_sheets,
    build_formula_chain,
    generate_analysis_report,
    generate_report_pdf,
    generate_dynamic_prompts,
    decide_chart_request,
    _plot_bar, _plot_histogram, _plot_scatter,
    process_pdf_with_ocr,
    extract_receipt_data_llm,
    categorize_receipts,
    plot_expense_pie_chart,
    generate_expense_summary
)

load_dotenv()
app = Flask(__name__)
app.secret_key = "spreadsheet-bot"
app.jinja_env.filters['markdown'] = lambda text: Markup(markdown(text, extensions=["fenced_code", "tables"]))

CHARTS_DIR = Path("static") / "generated_charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        if 'file' not in request.files:
            return redirect(request.url)

        file = request.files["file"]
        if file.filename == '':
            return redirect(request.url)

        if file:
            try:
                temp_dir = tempfile.gettempdir()
                filename = file.filename
                temp_path = os.path.join(temp_dir, filename)
                file.save(temp_path)

                session["file_path"] = temp_path
                session["original_filename"] = filename
                session["chat_history"] = []
                return redirect(url_for("chat"))
            except Exception:
                return redirect(request.url)

    return render_template("index.html", file_uploaded=False)

@app.route("/chat", methods=["GET", "POST"])
def chat():
    explanation = ""
    chat_history = session.get("chat_history", [])
    file_path = session.get("file_path")

    if not file_path or not os.path.exists(file_path):
        return redirect(url_for("upload_file"))

    if request.method == "POST":
        if 'question' not in request.form:
            return redirect(url_for("chat"))

        user_input = request.form["question"].strip()
        if not user_input:
            return redirect(url_for("chat"))

        chat_history.append({"role": "user", "content": user_input})

        if user_input == "Generate Analysis Report":
            try:
                df, table_text = extract_table_data_all_sheets(file_path)
                report_text = generate_analysis_report(df, table_text)
                tool_args = decide_chart_request(df)

                chart_markdown = ""
                if tool_args:
                    chart_type = tool_args.get('chart_type')
                    col1 = tool_args.get('column1')
                    col2 = tool_args.get('column2')
                    plot_success = False
                    chart_filename = None

                    if chart_type != 'none' and col1:
                        chart_filename = f"chart_{uuid.uuid4()}.png"
                        chart_path = CHARTS_DIR / chart_filename
                        if chart_type == 'bar':
                            plot_success = _plot_bar(df, col1, chart_path)
                            if plot_success: chart_markdown = f"\n\n![Bar chart of {col1}](/static/generated_charts/{chart_filename})\n\n"
                        elif chart_type == 'histogram':
                            plot_success = _plot_histogram(df, col1, chart_path)
                            if plot_success: chart_markdown = f"\n\n![Histogram of {col1}](/static/generated_charts/{chart_filename})\n\n"
                        elif chart_type == 'scatter' and col2:
                            plot_success = _plot_scatter(df, col1, col2, chart_path)
                            if plot_success: chart_markdown = f"\n\n![Scatter plot of {col1} vs {col2}](/static/generated_charts/{chart_filename})\n\n"

                        if not plot_success:
                            chart_markdown = "\n*(Chart generation failed)*\n"
                explanation = report_text.strip() + "\n\n" + chart_markdown.strip()

            except Exception as e:
                explanation = f"Sorry, error during report generation: {str(e)}"

        elif is_cell_reference(user_input):
            wb = openpyxl.load_workbook(file_path)
            cell = extract_cell(user_input)
            val = get_cell_value_across_sheets(wb, cell)
            if isinstance(val, str) and val.startswith("="):
                explanation = explain_formula(val)
                explanation += "\n\n" + build_formula_chain(wb, val)
            else:
                explanation = f"**Cell {cell} contains:** `{val}`"
        else:
            _, table_text = extract_table_data_all_sheets(file_path, max_rows=30, max_cols=10)
            explanation = ask_about_spreadsheet(table_text, user_input)

        chat_history.append({"role": "bot", "content": explanation})
        session["chat_history"] = chat_history
        return redirect(url_for("chat"))

    original_filename = session.get("original_filename")
    dynamic_prompts = []
    try:
        df, _ = extract_table_data_all_sheets(file_path)
        dynamic_prompts = generate_dynamic_prompts(df)
    except:
        pass

    return render_template(
        "index.html",
        file_uploaded=True,
        chat_history=chat_history,
        filename=original_filename,
        dynamic_prompts=dynamic_prompts
    )

@app.route("/process_receipt", methods=["POST"])
def process_receipt():
    if 'receipt_file' not in request.files:
        return redirect(url_for("chat"))

    file = request.files["receipt_file"]
    if file.filename == '':
        return redirect(url_for("chat"))

    if file and file.filename.lower().endswith('.pdf'):
        temp_pdf_path = None
        try:
            temp_dir = tempfile.gettempdir()
            temp_filename = f"receipt_{uuid.uuid4()}.pdf"
            temp_pdf_path = os.path.join(temp_dir, temp_filename)
            file.save(temp_pdf_path)

            ocr_text = process_pdf_with_ocr(temp_pdf_path)
            receipt_df = extract_receipt_data_llm(ocr_text)

            if receipt_df.empty:
                receipt_info = f"❌ Could not extract data from receipt: {file.filename}"
            else:
                receipts_list = receipt_df.to_dict(orient="records")
                categorized = categorize_receipts(receipts_list)

                pie_filename = f"expense_pie_{uuid.uuid4()}.png"
                pie_path = CHARTS_DIR / pie_filename
                pie_success = plot_expense_pie_chart(categorized, pie_path)

                summary_text = generate_expense_summary(categorized)

                receipt_info = f"**Processed Receipt: {file.filename}**\n\n"
                receipt_info += receipt_df.to_markdown(index=False) + "\n\n"
                if pie_success:
                    receipt_info += f"![Expense Breakdown](/static/generated_charts/{pie_filename})\n\n"
                receipt_info += f"**Spending Summary:**\n\n{summary_text}"

            chat_history = session.get("chat_history", [])
            chat_history.append({"role": "user", "content": f"Uploaded Receipt: {file.filename}"})
            chat_history.append({"role": "bot", "content": receipt_info})
            session["chat_history"] = chat_history

        except Exception as e:
            chat_history = session.get("chat_history", [])
            chat_history.append({"role": "user", "content": f"Uploaded Receipt: {file.filename}"})
            chat_history.append({"role": "bot", "content": f"❌ Error processing receipt: {str(e)}"})
            session["chat_history"] = chat_history
        finally:
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                try:
                    os.remove(temp_pdf_path)
                except:
                    pass

    return redirect(url_for("chat"))

@app.route("/download_report")
def download_report():
    chat_history = session.get("chat_history", [])
    last_report_content = None
    chart_full_path = None

    user_request_indices = [i for i, msg in enumerate(chat_history)
                            if msg.get('role') == 'user' and msg.get('content') == 'Generate Analysis Report']

    if not user_request_indices:
        return "No report found to download.", 404

    last_request_index = user_request_indices[-1]
    if last_request_index + 1 < len(chat_history) and chat_history[last_request_index + 1].get('role') == 'bot':
        last_report_content = chat_history[last_request_index + 1].get('content')

        chart_path_match = re.search(r'!\[.*?\]\((/static/generated_charts/.*?)\)', last_report_content)
        if chart_path_match:
            chart_filename = os.path.basename(chart_path_match.group(1))
            chart_full_path = os.path.join(current_app.static_folder, "generated_charts", chart_filename)

    if not last_report_content:
        return "Could not find the report content.", 404

    pdf_bytes = generate_report_pdf(last_report_content, chart_full_path)
    if pdf_bytes:
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=analysis_report.pdf'
        return response
    else:
        return "Error generating PDF.", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
