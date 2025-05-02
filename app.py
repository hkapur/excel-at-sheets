import os
import re
import tempfile
import openpyxl

from flask import Flask, request, render_template, redirect, url_for, session
from dotenv import load_dotenv
from markupsafe import Markup
from markdown import markdown

from helpers import (
    ask_about_spreadsheet,
    explain_formula,
    extract_cell,
    is_cell_reference,
    get_cell_value_across_sheets,
    extract_table_data_all_sheets,
    build_formula_chain
)

load_dotenv()
app = Flask(__name__)
app.secret_key = "spreadsheet-bot"
app.jinja_env.filters['markdown'] = lambda text: Markup(markdown(text, extensions=["fenced_code", "tables"]))

@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        file = request.files["file"]
        if file:
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, file.filename)
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

if __name__ == "__main__":
    app.run(debug=True)
