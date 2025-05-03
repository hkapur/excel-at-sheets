import os
import re
import tempfile
import openpyxl
import io
import uuid
import pandas as pd
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
    generate_financial_analysis,
    create_transaction_table
)

load_dotenv()
app = Flask(__name__)
app.secret_key = "spreadsheet-bot"
app.jinja_env.filters['markdown'] = lambda text: Markup(markdown(text, extensions=["fenced_code", "tables"]))

# Point CHARTS_DIR back to the subdirectory
CHARTS_DIR = Path("static") / "generated_charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)
print(f"Using chart directory: {CHARTS_DIR.resolve()}") 

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
                print(f"Attempting to save file to: {temp_path}")
                
                file.save(temp_path)
                print(f"File successfully saved to: {temp_path}")

                session["file_path"] = temp_path
                session["original_filename"] = filename
                session["chat_history"] = []
                print("Session updated with file_path and original_filename, redirecting to /chat")
                return redirect(url_for("chat"))
            except Exception as e: # Correctly indented except
                print(f"Error saving file or updating session: {e}") 
                return redirect(request.url)
        else:
            print("Error: File object invalid or missing.")
            return redirect(request.url)
            
    # GET request or initial load
    print("GET request received at / route or initial load.") # Log: GET request
    return render_template("index.html", file_uploaded=False)

@app.route("/chat", methods=["GET", "POST"])
def chat():
    explanation = ""
    chat_history = session.get("chat_history", [])
    file_path = session.get("file_path")

    # --- Display last receipt result if available (RE-APPLIED AGAIN) --- 
    last_receipt_result = session.pop('last_receipt_result', None)
    if last_receipt_result:
         # Temporarily insert it into the history for rendering this one time
         # It won't be saved back to the session unless another POST happens
         if not chat_history or chat_history[-1].get('content') != last_receipt_result:
              # Find the corresponding bot summary message and replace it
              for i in range(len(chat_history) - 1, -1, -1):
                   if chat_history[i].get('role') == 'bot' and chat_history[i].get('content').startswith("Successfully analyzed receipt"): 
                        chat_history[i]['content'] = last_receipt_result
                        break
              else: # If no placeholder found (e.g., error during processing), append
                   # Avoid appending if it's identical to the last message already
                   if not chat_history or chat_history[-1].get('content') != last_receipt_result:
                        chat_history.append({"role": "bot", "content": last_receipt_result})
         # --- Add Logging --- 
         print("--- Rendering /chat GET with last_receipt_result --- ")
         # Find the message content actually being sent to template
         final_bot_message = "[Could not find final bot message for logging]"
         for msg in reversed(chat_history):
             if msg.get('role') == 'bot':
                 final_bot_message = msg.get('content', '[Bot message content missing]')
                 break
         print(f"Final Bot Message Content Rendered:\n{repr(final_bot_message)}")
         print("-------------------------------------------------")
         # --- End Logging ---
    # --- End Display Logic --- 

    # Original logic: If no excel file path, redirect to upload (RE-APPLIED LOGIC AGAIN)
    if not file_path or not os.path.exists(file_path):
        # If we just processed a receipt (file_path is None), render without redirect
        if file_path is None:
             print("Rendering chat page without active Excel file.")
             dynamic_prompts = [] # No prompts without excel file
             original_filename = None
             file_uploaded_state = bool(session.get("chat_history")) 
             return render_template(
                  "index.html", 
                  file_uploaded=file_uploaded_state, 
                  chat_history=chat_history, 
                  filename=original_filename, 
                  dynamic_prompts=dynamic_prompts
             )
        else: # file_path exists but file is gone - redirect
             print("File path exists in session but not on disk, redirecting to upload.")
        return redirect(url_for("upload_file"))

    # --- Existing POST/GET logic for Excel file follows ---
    # (This part is now only reached if file_path points to a valid Excel file)
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

            if receipt_df.empty or 'total' not in receipt_df.columns:
                print("Warning: Extracted data is empty or missing 'total' column.")
                receipt_info = f"❌ Could not extract valid data (missing totals) from receipt: {file.filename}"
            else:
                # --- Data Preparation & CLEANING ---
                
                # ** Clean the 'total' column **
                print(f"Raw 'total' column before cleaning:\n{receipt_df['total']}")
                # Remove $, ,, and potentially 'CA' prefix then convert to numeric, coercing errors to NaN
                receipt_df['total'] = receipt_df['total'].astype(str).str.replace(r'[$,]|CA', '', regex=True)
                receipt_df['total'] = pd.to_numeric(receipt_df['total'], errors='coerce')
                # Fill any NaNs resulting from conversion with 0.0
                original_nan_count = receipt_df['total'].isna().sum()
                if original_nan_count > 0:
                     print(f"Warning: Coerced {original_nan_count} non-numeric 'total' values to NaN. Filling with 0.")
                     receipt_df['total'].fillna(0.0, inplace=True)
                print(f"Cleaned 'total' column after processing:\n{receipt_df['total']}")
                # ** End 'total' cleaning **

                # Standardize Date (Moved after cleaning total, but independent)
                try:
                    receipt_df['date'] = pd.to_datetime(receipt_df['date'], errors='coerce')
                    # Create the string version *before* potential fillna
                    receipt_df['date_str'] = receipt_df['date'].dt.strftime('%Y-%m-%d')
                    # Fix fillna warning: Assign result back instead of using inplace=True on slice
                    receipt_df['date_str'] = receipt_df['date_str'].fillna('Invalid Date')
                except Exception as date_err:
                    print(f"Warning: Error standardizing dates: {date_err}")
                    # Ensure date_str exists even on error
                    if 'date_str' not in receipt_df.columns:
                         receipt_df['date_str'] = 'Date Error' 
                    else:
                         receipt_df['date_str'].fillna('Date Error', inplace=True) # This inplace is okay on the whole column

                # Calculate Period, Total, Count (using the *cleaned* total column)
                valid_dates = receipt_df['date'].dropna()
                if not valid_dates.empty:
                    min_date = valid_dates.min().strftime('%Y-%m-%d')
                    max_date = valid_dates.max().strftime('%Y-%m-%d')
                    period_str = f"{min_date} to {max_date}"
                else:
                    period_str = "Date range undetermined"
                
                # Calculate Total, Count (using the *cleaned* total column)
                # No need to coerce again here, already done
                total_spent = receipt_df['total'].sum()
                total_spent_str = f"${total_spent:.2f}"
                num_transactions = len(receipt_df)
                print(f"Period: {period_str}, Total: {total_spent_str}, Transactions: {num_transactions}")
                # --- End Data Preparation ---

                # Use date_str for categorization input if available
                # Fix duplicate columns warning: Select specific columns *before* rename
                df_for_cat = receipt_df[['vendor', 'total', 'date_str']].copy()
                # Rename 'date_str' to 'date' as expected by categorize_receipts
                df_for_cat.rename(columns={'date_str': 'date'}, inplace=True)
                receipts_list = df_for_cat.to_dict(orient="records")
                
                categorized_data = categorize_receipts(receipts_list)
                
                # Need DataFrame again for table/plot, ensure date is the string version
                categorized_df = pd.DataFrame(categorized_data)
                # Check/merge date_str back if categorization somehow dropped it (more robust)
                if 'date' not in categorized_df.columns:
                    print("Warning: 'date' field missing after categorization, attempting to merge back.")
                    # Ensure we have the original date_str to merge back
                    if 'date_str' in receipt_df.columns:
                        # Merge based on vendor and total, assuming they are unique enough identifiers *for this merge*
                        # This might be fragile if vendor+total are not unique
                        categorized_df = categorized_df.merge(
                            receipt_df[['vendor', 'total', 'date_str']], 
                            on=['vendor', 'total'], 
                            how='left'
                        )
                        # Rename the merged column back to 'date' if merge was successful
                        if 'date_str' in categorized_df.columns:
                             categorized_df.rename(columns={'date_str': 'date'}, inplace=True)
                             categorized_df['date'].fillna('Unknown Date', inplace=True)
                        else:
                             categorized_df['date'] = 'Merge Failed' 
                    else:
                         categorized_df['date'] = 'Unknown Date'

                # Create Detailed Table (using cleaned totals)
                transaction_table_md = create_transaction_table(categorized_df.to_dict(orient='records'))

                # Plot Pie Chart (using cleaned totals via categorized_data)
                pie_filename = f"expense_pie_{uuid.uuid4()}.png"
                pie_path = CHARTS_DIR / pie_filename
                pie_success = plot_expense_pie_chart(categorized_data, pie_path)

                # Generate Structured Analysis
                analysis_text = generate_financial_analysis(categorized_data, period_str, total_spent_str, num_transactions)

                # --- Assemble Final Report --- 
                receipt_info = f"## Monthly Expense Report\n\n"
                receipt_info += f"**Period:** {period_str}\n"
                receipt_info += f"**Total Expenses:** {total_spent_str} across {num_transactions} transactions\n\n"
                receipt_info += f"### Detailed Transactions\n{transaction_table_md}\n\n"
                if pie_success:
                    receipt_info += f"### Category Breakdown\n![Expense Breakdown](/static/generated_charts/{pie_filename})\n"
                else:
                    receipt_info += "*(Pie chart generation failed)*\n\n"
                    
                # Add the structured analysis (already contains headers)
                receipt_info += analysis_text
                # --- End Assembly ---

            # -- Session Management (RE-APPLIED AGAIN) --
            chat_history = session.get("chat_history", [])
            # Add user message
            chat_history.append({"role": "user", "content": f"Uploaded Receipt: {file.filename}"})
            # Add **only a summary** of the bot response to history to keep session small
            summary_bot_message = f"Successfully analyzed receipt: {file.filename}. See details above."
            chat_history.append({"role": "bot", "content": summary_bot_message})
            session["chat_history"] = chat_history
            print("Receipt analysis summary added to chat history.")
            
            # Store the full response temporarily just for the immediate redirect display
            session['last_receipt_result'] = receipt_info
            
            # Clear Excel-specific session keys to prevent type conflict later
            session.pop('file_path', None)
            session.pop('original_filename', None)
            print("Cleared Excel file path from session after PDF processing.")
            # -- End Session Management --

        except Exception as e:
            # Log error and add error message to history (without full report)
            print(f"Error processing receipt file: {e}")
            chat_history = session.get("chat_history", [])
            chat_history.append({"role": "user", "content": f"Uploaded Receipt: {file.filename}"})
            chat_history.append({"role": "bot", "content": f"❌ Error processing receipt: {str(e)}"})
            session["chat_history"] = chat_history
            # Clear potentially problematic session keys even on error
            session.pop('file_path', None)
            session.pop('original_filename', None)
            session.pop('last_receipt_result', None) # Clear partial result too
        finally:
            # Cleanup temporary file
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                try:
                    os.remove(temp_pdf_path)
                    print(f"Cleaned up temporary file: {temp_pdf_path}")
                except Exception as e_clean:
                    print(f"Error cleaning up temp file {temp_pdf_path}: {e_clean}")

    else:
        # Handle invalid file type before session modification
        print(f"Error: Invalid file type or file object for receipt. Filename: {file.filename}")
        # TODO: Add user feedback (e.g., flash message for non-PDF)

    return redirect(url_for("chat")) # Redirect back to main chat page

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

        chart_path_match = re.search(r'!\[.*?\]\((/static/.*?)\)', last_report_content)
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
