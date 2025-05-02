import os
import re
import tempfile
import openpyxl
from flask import Flask, request, render_template, redirect, url_for, session
from dotenv import load_dotenv
from markupsafe import Markup
from markdown import markdown

# LangChain
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

load_dotenv()
app = Flask(__name__)
app.secret_key = "spreadsheet-bot"

# Enable markdown rendering
app.jinja_env.filters['markdown'] = lambda text: Markup(markdown(text, extensions=["fenced_code", "tables"]))

# OpenAI model setup via LangChain
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        file = request.files["file"]
        if file:
            temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx").name
            file.save(temp_path)
            session["file_path"] = temp_path
            session["chat_history"] = []
            return redirect(url_for("chat"))
    return render_template("index.html", file_uploaded=False)

@app.route("/chat", methods=["GET", "POST"])
def chat():
    explanation = ""
    chat_history = session.get("chat_history", [])
    file_path = session.get("file_path")

    if not file_path or not os.path.exists(file_path):
        return redirect(url_for("upload_file"))

    wb = openpyxl.load_workbook(file_path)

    if request.method == "POST":
        user_input = request.form["question"].strip()
        chat_history.append({"role": "user", "content": user_input})

        if is_cell_reference(user_input):
            cell = extract_cell(user_input)
            val = get_cell_value_across_sheets(wb, cell)
            if isinstance(val, str) and val.startswith("="):
                explanation = explain_formula(val)
                explanation += "\n\n" + build_formula_chain(wb, val)
            else:
                explanation = f"**Cell {cell} contains:** `{val}`"
        else:
            table_text = extract_table_data_all_sheets(wb)
            explanation = ask_about_spreadsheet(table_text, user_input)

        chat_history.append({"role": "bot", "content": explanation})
        session["chat_history"] = chat_history

    return render_template("index.html", file_uploaded=True, chat_history=chat_history)

# ========== LangChain Helpers ==========

def ask_about_spreadsheet(table_text, user_question):
    system = "You are a helpful assistant that analyzes spreadsheets with multiple sheets and answers clearly."
    user = f"""
Use bullet points and markdown formatting in your response.

**Spreadsheet content:**

{table_text}

**User question:** {user_question}
"""
    try:
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return response.content
    except Exception as e:
        return f"Error: {str(e)}"

def explain_formula(formula):
    system = "You are a helpful assistant who explains Excel formulas step-by-step using markdown."
    user = f"Explain this Excel formula:\n\n`{formula}`"
    try:
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return response.content
    except Exception as e:
        return f"Error: {str(e)}"

# ========== Spreadsheet Helpers ==========

def extract_table_data_all_sheets(wb, max_rows=30, max_cols=10):
    all_data = []
    for sheet in wb.sheetnames:
        ws = wb[sheet]
        all_data.append(f"### Sheet: {sheet}")
        for row in ws.iter_rows(min_row=1, max_row=max_rows, max_col=max_cols, values_only=True):
            row_text = "\t".join(str(cell) if cell is not None else "" for cell in row)
            all_data.append(row_text)
        all_data.append("")  # spacing between sheets
    return "\n".join(all_data)

def get_cell_value_across_sheets(wb, cell):
    for sheet in wb.sheetnames:
        ws = wb[sheet]
        try:
            val = ws[cell].value
            if val is not None:
                return val
        except:
            continue
    return "(not found in any sheet)"

def build_formula_chain(wb, formula):
    refs = re.findall(r'\b[A-Z]{1,2}[0-9]{1,4}\b', formula)
    if not refs:
        return ""
    parts = ["\n**Referenced cells:**"]
    for sheet in wb.sheetnames:
        ws = wb[sheet]
        for ref in refs:
            try:
                val = ws[ref].value
                if val is not None:
                    parts.append(f"- `{ref}` in *{sheet}* = `{val}`")
            except:
                continue
    return "\n".join(parts)

# ========== Utility Helpers ==========

def extract_cell(text):
    match = re.search(r"\b([A-Z]{1,2}[0-9]{1,4})\b", text.upper())
    return match.group(1) if match else "A1"

def is_cell_reference(text):
    return bool(re.search(r"\b([A-Z]{1,2}[0-9]{1,4})\b", text.upper()))

if __name__ == "__main__":
    app.run(debug=True)
