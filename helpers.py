import re
from openpyxl import load_workbook
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

# ========= LangChain Helpers =========

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

# ========= Spreadsheet Helpers =========

def extract_table_data_all_sheets(wb, max_rows=30, max_cols=10):
    all_data = []
    for sheet in wb.sheetnames:
        ws = wb[sheet]
        all_data.append(f"### Sheet: {sheet}")
        for row in ws.iter_rows(min_row=1, max_row=max_rows, max_col=max_cols, values_only=True):
            row_text = "\t".join(str(cell) if cell is not None else "" for cell in row)
            all_data.append(row_text)
        all_data.append("")  # spacing
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

# ========= Utility Helpers =========

def extract_cell(text):
    match = re.search(r"\b([A-Z]{1,2}[0-9]{1,4})\b", text.upper())
    return match.group(1) if match else "A1"

def is_cell_reference(text):
    return bool(re.search(r"\b([A-Z]{1,2}[0-9]{1,4})\b", text.upper()))
