import os
import re
import tempfile
import openpyxl
import io
from flask import Flask, request, render_template, redirect, url_for, session, send_file, make_response, current_app
from dotenv import load_dotenv
from markupsafe import Markup
from markdown import markdown
from pathlib import Path
import uuid

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
    generate_plot_ideas
)

load_dotenv()
app = Flask(__name__)
app.secret_key = "spreadsheet-bot"
app.jinja_env.filters['markdown'] = lambda text: Markup(markdown(text, extensions=["fenced_code", "tables"]))

# --- Define CHARTS_DIR here --- 
CHARTS_DIR = Path("static") / "generated_charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)
print(f"Ensured chart directory exists: {CHARTS_DIR.resolve()}") # Log path
# --- End CHARTS_DIR definition ---

@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        print("POST request received at / route.") # Log: Request received
        if 'file' not in request.files:
            print("Error: 'file' not found in request.files") # Log: No file part
            # Optionally: Add user feedback via flash messages
            return redirect(request.url)
        
        file = request.files["file"]
        print(f"Received file: {file.filename}") # Log: File object received

        if file.filename == '':
            print("Error: No selected file") # Log: Empty filename
            # Optionally: Add user feedback
            return redirect(request.url)

        if file: # Check if file object exists and has a name
            try:
                temp_dir = tempfile.gettempdir()
                # Sanitize filename slightly (basic example, consider more robust sanitization)
                # For simplicity, let's just use the original name for now, but be aware of security risks
                filename = file.filename 
                temp_path = os.path.join(temp_dir, filename)
                print(f"Attempting to save file to: {temp_path}") # Log: Save path
                
                file.save(temp_path)
                print(f"File successfully saved to: {temp_path}") # Log: Save success

                session["file_path"] = temp_path
                session["original_filename"] = filename # Store original filename
                session["chat_history"] = []
                print("Session updated with file_path and original_filename, redirecting to /chat") # Log: Redirecting
                return redirect(url_for("chat"))
            except Exception as e:
                print(f"Error saving file: {e}") # Log: Save error
                # Optionally: Add user feedback
                return redirect(request.url) # Redirect back on error
        else:
            print("Error: File object invalid or missing.") # Log: Invalid file object
            return redirect(request.url)
            
    # GET request or initial load
    print("GET request received at / route or initial load.") # Log: GET request
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
            print("Error: 'question' key missing in POST form data.")
            # Redirect back to chat, maybe with a flash message later
            return redirect(url_for("chat"))
        
        user_input = request.form["question"].strip()
        
        # Add empty input check after stripping
        if not user_input:
            print("Info: Empty question submitted, redirecting.")
            return redirect(url_for("chat"))
            
        chat_history.append({"role": "user", "content": user_input})

        # Process input (Report, Cell, or General Question)
        if user_input == "Generate Analysis Report":
            try:
                df, table_text = extract_table_data_all_sheets(file_path)
                
                # STEP A: Generate Text Report
                report_text = generate_analysis_report(df, table_text)
                
                # STEP B: Decide on Chart via Tool Call
                tool_args = decide_chart_request(df)
                
                # STEP C: Generate Chart based on Tool Args
                chart_markdown = "" # Default to no chart
                if tool_args:
                    chart_type = tool_args.get('chart_type')
                    col1 = tool_args.get('column1')
                    col2 = tool_args.get('column2')
                    plot_success = False
                    chart_filename = None

                    if chart_type != 'none' and col1: # Need at least type and col1 unless 'none'
                        chart_filename = f"chart_{uuid.uuid4()}.png"
                        chart_path = CHARTS_DIR / chart_filename
                        
                        if chart_type == 'bar':
                            plot_success = _plot_bar(df, col1, chart_path)
                            if plot_success: chart_markdown = f"\n\n![Bar chart of {col1}](/static/generated_charts/{chart_filename})\n\n"
                        elif chart_type == 'histogram':
                             plot_success = _plot_histogram(df, col1, chart_path)
                             if plot_success: chart_markdown = f"\n\n![Histogram of {col1}](/static/generated_charts/{chart_filename})\n\n"
                        elif chart_type == 'scatter' and col2: # Scatter needs col2
                            plot_success = _plot_scatter(df, col1, col2, chart_path)
                            if plot_success: chart_markdown = f"\n\n![Scatter plot of {col1} vs {col2}](/static/generated_charts/{chart_filename})\n\n"
                        else:
                             print(f"Route Info: Unsupported chart type '{chart_type}' or missing args from tool call: {tool_args}")
                             chart_markdown = "\n*(Unsupported chart type requested by LLM)*\n"

                        if not plot_success:
                             chart_markdown = "\n*(Chart generation failed)*\n"
                    elif chart_type != 'none': # Handle cases like bar/hist without col1
                         print(f"Route Info: Invalid arguments for chart type '{chart_type}': {tool_args}")
                         chart_markdown = "\n*(Invalid arguments for chart request)*\n"
                
                # STEP D: Combine Text and Chart
                print("--- Report Text for Combination ---")
                print(repr(report_text)) # Log the exact text being searched
                print("--- End Report Text ---")
                
                # Use regex to find insertion point more robustly
                # Looks for variations like \n4. Viz..., ## 4 Viz..., **4.** Viz...
                section_marker_pattern = r"(^|\n)[#*]*\s*4\.?\s+(Visualization[s]?)(?:\s+and\s+Tables)?.*"
                match = re.search(section_marker_pattern, report_text, re.IGNORECASE | re.MULTILINE)

                explanation = None # Initialize explanation
                if match:
                    # Find the end of the matched heading line to insert after it
                    insert_after_pos = match.end()
                    # Find the next newline after the heading match to insert before that part
                    next_newline_pos = report_text.find('\n', insert_after_pos)
                    
                    if next_newline_pos != -1:
                        part1 = report_text[:next_newline_pos].strip() # Includes the heading and maybe following text
                        part2 = report_text[next_newline_pos:]      # Rest of the report
                        # Insert chart markdown between the heading line and the rest
                        explanation = part1 + "\n\n" + chart_markdown.strip() + "\n" + part2
                        print(f"Report Combination: Inserted chart after regex match at pos {insert_after_pos}")
                    else:
                        # If heading is the last thing, append after it
                        print("Report Combination Warning: No newline found after matched Section 4 heading. Appending chart after heading.")
                        explanation = report_text.strip() + "\n\n" + chart_markdown.strip() 
                else:
                    # Fallback: If section marker not found, append chart to the very end
                    print("Report Combination Warning: Regex marker for Section 4 not found. Appending chart to the end.")
                    explanation = report_text.strip() + "\n\n" + chart_markdown.strip() # Append if marker not found
                    
            except Exception as e:
                print(f"Error processing report request in /chat route: {e}")
                import traceback
                traceback.print_exc()
                explanation = f"Sorry, I encountered an error processing the report request: {str(e)}"
        
        # Otherwise, handle cell references or general questions
        elif is_cell_reference(user_input):
            wb = openpyxl.load_workbook(file_path) # Load workbook for cell check
            cell = extract_cell(user_input)
            val = get_cell_value_across_sheets(wb, cell)
            if isinstance(val, str) and val.startswith("="):
                explanation = explain_formula(val)
                explanation += "\n\n" + build_formula_chain(wb, val)
            else:
                explanation = f"**Cell {cell} contains:** `{val}`"
        else:
            # Extract limited text for general questions
            _, table_text = extract_table_data_all_sheets(file_path, max_rows=30, max_cols=10)
            explanation = ask_about_spreadsheet(table_text, user_input)

        chat_history.append({"role": "bot", "content": explanation})
        session["chat_history"] = chat_history
        # Redirect back to chat to show the new message
        return redirect(url_for("chat")) 

    # For GET request, just render the page
    original_filename = session.get("original_filename") # Get filename from session
    dynamic_prompts = []
    try:
        # Generate dynamic prompts based on the data for GET requests
        df, _ = extract_table_data_all_sheets(file_path)
        dynamic_prompts = generate_dynamic_prompts(df)
    except Exception as e:
        print(f"Error generating dynamic prompts: {e}")
        # Continue without dynamic prompts if error

    return render_template(
        "index.html", 
        file_uploaded=True, 
        chat_history=chat_history, 
        filename=original_filename, 
        dynamic_prompts=dynamic_prompts # Pass dynamic prompts
    )

@app.route("/download_report")
def download_report():
    """Finds the last generated report in session and returns it as PDF."""
    chat_history = session.get("chat_history", [])
    last_report_content = None
    chart_full_path = None # Initialize

    user_request_indices = [i for i, msg in enumerate(chat_history) 
                            if msg.get('role') == 'user' and msg.get('content') == 'Generate Analysis Report']

    if not user_request_indices:
        print("Download Error: No 'Generate Analysis Report' request found in history.")
        return "No report found to download.", 404

    last_request_index = user_request_indices[-1]
    if last_request_index + 1 < len(chat_history) and chat_history[last_request_index + 1].get('role') == 'bot':
        last_report_content = chat_history[last_request_index + 1].get('content')
        
        # --- Log the content being searched ---
        if last_report_content:
            print("--- Start Report Content for Download ---")
            print(repr(last_report_content)) # Use repr() to see exact characters like \n
            print("--- End Report Content for Download ---")
        else:
             print("Download Error: Found bot message index, but content is missing.")
             return "Could not find the report content.", 404
        # --- End Log ---

        # Extract the relative chart path (/static/...) from the markdown
        chart_path_match = re.search(r'!\[.*?\]\((/static/generated_charts/.*?)\)', last_report_content)
        if chart_path_match:
            chart_relative_path = chart_path_match.group(1)
            # Construct absolute path using app.static_folder
            # chart_relative_path starts with '/', slice it off for os.path.join
            chart_filename = os.path.basename(chart_relative_path)
            chart_full_path = os.path.join(current_app.static_folder, "generated_charts", chart_filename)
            print(f"Download Request: Constructed absolute chart path: {chart_full_path}") # Log the path
            if not os.path.exists(chart_full_path):
                 print(f"Download Warning: Chart file not found at: {chart_full_path}") # Log if not found
                 chart_full_path = None # Prevent passing non-existent path
        else:
             print("Download Info: No chart path found in the report markdown (Regex failed to match).") # Added detail

    if not last_report_content:
        print("Download Error: Could not find bot response for the last report request.")
        return "Could not find the report content.", 404

    print(f"Download Request: Calling generate_report_pdf. Chart path: {chart_full_path}")
    pdf_bytes = generate_report_pdf(last_report_content, chart_full_path)

    if pdf_bytes:
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=analysis_report.pdf'
        print("Download Request: Sending PDF response.")
        return response
    else:
        print("Download Error: PDF generation failed.")
        return "Error generating PDF.", 500

@app.route("/get_plot_ideas")
def get_plot_ideas():
    """Returns three interactive plot ideas based on the uploaded file."""
    file_path = session.get("file_path")
    
    if not file_path or not os.path.exists(file_path):
        return redirect(url_for("upload_file"))
    
    try:
        df, _ = extract_table_data_all_sheets(file_path)
        plot_ideas = generate_plot_ideas(df)
        session["plot_ideas"] = plot_ideas
        return redirect(url_for("chat"))
    except Exception as e:
        print(f"Error generating plot ideas: {e}")
        session["plot_ideas"] = ["Basic Chart", "Data Analysis", "Visual Insights"]
        return redirect(url_for("chat"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5018)))
