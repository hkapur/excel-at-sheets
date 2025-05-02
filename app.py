import os
import re
import tempfile
import openpyxl
from flask import Flask, request, render_template, redirect, url_for, session
from markupsafe import Markup
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from markdown import markdown

load_dotenv()
app = Flask(__name__)
app.secret_key = "spreadsheet-bot"

# Register markdown filter
app.jinja_env.filters['markdown'] = lambda text: Markup(markdown(text, extensions=["fenced_code", "tables"]))

# Initialize OpenAI LLM
llm = ChatOpenAI(model="gpt-4o", temperature=0.3)

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
    ws = wb.active

    if request.method == "POST":
        user_input = request.form["question"].strip()
        chat_history.append({"role": "user", "content": user_input})

        if is_cell_reference(user_input):
            cell = extract_cell(user_input)
            val = ws[cell].value
            if isinstance(val, str) and val.startswith("="):
                explanation = explain_formula(val)
                explanation += "\n\n" + build_formula_chain(ws, val)
            else:
                explanation = f"**Cell {cell} contains:** `{val}`"
        else:
            table_text = extract_table_data(ws)
            explanation = ask_about_spreadsheet(table_text, user_input)

        chat_history.append({"role": "bot", "content": explanation})
        session["chat_history"] = chat_history

    return render_template("index.html", file_uploaded=True, chat_history=chat_history)

# ========== LangChain Helpers ==========

def ask_about_spreadsheet(table_text, user_question):
    system = "You are a helpful assistant that analyzes spreadsheet tables and answers user questions clearly."
    user = f"""
Please answer the user's question using bullet points and markdown formatting.

**Spreadsheet:**
{table_text}

**Question:** {user_question}
"""
    try:
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return response.content
    except Exception as e:
        return f"Error: {str(e)}"

def explain_formula(formula):
    system = "You are a helpful assistant who explains Excel formulas step-by-step using markdown and bullet points."
    user = f"Explain what this Excel formula does:\n\n`{formula}`"
    try:
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return response.content
    except Exception as e:
        return f"Error: {str(e)}"

# ========== Local Helpers ==========

def extract_table_data(ws, max_rows=30, max_cols=10):
    data = []
    for row in ws.iter_rows(min_row=1, max_row=max_rows, max_col=max_cols, values_only=True):
        data.append("\t".join(str(cell) if cell is not None else "" for cell in row))
    return "\n".join(data)

def extract_cell(text):
    match = re.search(r"\b([A-Z]{1,2}[0-9]{1,4})\b", text.upper())
    return match.group(1) if match else "A1"

def is_cell_reference(text):
    return bool(re.search(r"\b([A-Z]{1,2}[0-9]{1,4})\b", text.upper()))

def build_formula_chain(ws, formula):
    refs = re.findall(r'\b[A-Z]{1,2}[0-9]{1,4}\b', formula)
    if not refs:
        return ""
    parts = ["\n**Referenced cells:**"]
    for ref in refs:
        try:
            val = ws[ref].value
            parts.append(f"- `{ref}` = `{val}`")
        except:
            parts.append(f"- `{ref}` = (unavailable)")
    return "\n".join(parts)

if __name__ == "__main__":
    app.run(debug=True)
