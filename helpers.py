import os
import re
import pandas as pd
import matplotlib
matplotlib.use('Agg') # Use non-interactive backend for server use
import matplotlib.pyplot as plt
import uuid
from pathlib import Path # To create directory
import base64 # Import base64
from typing import Literal, Optional # For Pydantic model
from pydantic import BaseModel, Field # For Pydantic model

from openpyxl import load_workbook
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from markdown import markdown
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
import io

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3, api_key=os.getenv("OPENAI_API_KEY"))

# Ensure the directory for saving charts exists
CHARTS_DIR = Path("static") / "generated_charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

# ========= Pydantic Model for Tool Arguments ==========
class ChartRequestArgs(BaseModel):
    """Schema for arguments of the chart request tool."""
    chart_type: Literal["bar", "histogram", "scatter", "none"] = Field(description="The type of chart requested (bar, histogram, scatter, or none).")
    column1: Optional[str] = Field(None, description="The primary column name for the chart (required if chart_type is not 'none').")
    column2: Optional[str] = Field(None, description="The secondary column name (required only if chart_type is 'scatter').")

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

def get_column_summary(df):
    """Creates a text summary of DataFrame columns for the LLM."""
    if df is None or df.empty:
        return "The spreadsheet is empty or could not be read."
    
    summary_lines = ["Spreadsheet Columns:"]
    for col in df.columns:
        dtype = str(df[col].dtype)
        line = f"- '{col}' (Type: {dtype})"
        # Add unique count for potential categorical columns
        if dtype in ['object', 'category']:
            num_unique = df[col].nunique()
            line += f" ({num_unique} unique values)"
        summary_lines.append(line)
    return "\n".join(summary_lines)

def generate_analysis_report(df, table_text):
    """Generates ONLY the text analysis report using the LLM."""
    
    column_summary = get_column_summary(df)
    
    # Prompt focused ONLY on generating the text report
    system = f'''You are a professional data analyst assistant. Analyze the column summary and data sample provided below.

**Task:** Generate a comprehensive text-based analysis report.

**Important Note:** In a subsequent step, you will be asked (via a tool call) to specify the most appropriate chart (bar, histogram, scatter, or none) based on this data. Please write your analysis text *anticipating* the chart you intend to request. For example, if you plan to request a bar chart of 'Category', your 'Key Findings' should include insights derivable from such a chart.

**Report Structure Requirements:**
1. Objective and Scope
2. Data Description
3. Methodology (Describe analysis based on data sample)
4. Visualizations and Tables (Briefly describe the chart you *intend* to request later, or state why none is appropriate)
5. Key Findings (Derived ONLY from the provided data sample, *incorporating insights from the anticipated chart*)
6. Conclusions and Recommendations (Based ONLY on the provided data sample *and anticipated chart insights*)
7. Professional Formatting (Use markdown headings, bullet points, etc.)

Generate *only* the narrative report content. Do NOT include placeholders for charts or the actual tool call request in this text.'''

    user = f'''
**Column Summary:**
{column_summary}

**Spreadsheet Data Sample:**
{table_text}

**Generate the text analysis report based ONLY on the summary and sample provided.**
'''

    try:
        # Invoke LLM for text generation ONLY
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        report_text = response.content
        print("--- LLM Text Report Generation Complete ---")
        return report_text.strip()

    except Exception as e:
        print(f"Error in generate_analysis_report (text only): {e}")
        import traceback
        traceback.print_exc() 
        return f"Error generating text report: {str(e)}"

# ========= New Function for Chart Decision ==========
def decide_chart_request(df):
    """Asks the LLM to decide on a chart via tool call based on data structure."""
    if df is None or df.empty:
        print("Chart Decision: DataFrame empty, skipping LLM call.")
        return None
        
    column_summary = get_column_summary(df)

    system = f'''You are a data visualization expert. Based on the following column summary, decide the single most appropriate chart type (bar, histogram, scatter) to visualize a key aspect of the data, OR decide 'None' if no single chart is significantly meaningful or possible.

**Instructions:**
1. Analyze the columns, types, and unique value counts.
2. **CRITICAL:** Use the `register_chart_request` tool to register your decision. Provide the arguments `chart_type`, `column1`, and `column2` (if applicable) based on your analysis.
   - For `bar` or `histogram`, specify `column1`.
   - For `scatter`, specify both `column1` and `column2`.
   - For `none`, specify `chart_type` as `none` and leave columns as `None`.
Do NOT generate any other text output, only make the tool call.'''

    user = f'''
**Column Summary:**
{column_summary}

**Use the `register_chart_request` tool to specify the best chart based on this summary.**
'''

    try:
        llm_with_tool = llm.bind_tools([ChartRequestArgs])
        response = llm_with_tool.invoke([SystemMessage(content=system), HumanMessage(content=user)])

        # Process tool calls
        tool_args = None
        tool_calls = getattr(response, 'tool_calls', [])
        if tool_calls:
            first_tool_call = tool_calls[0]
            if first_tool_call.get('name') == ChartRequestArgs.__name__:
                 tool_args = first_tool_call.get('args')
                 print(f"Chart Decision: Parsed Tool Call Args: {tool_args}")
            else:
                 print(f"Chart Decision Warning: Unexpected tool call: {first_tool_call.get('name')}")
        else:
            # Check additional_kwargs as fallback
            additional_kwargs = getattr(response, 'additional_kwargs', {})
            tool_call_data = additional_kwargs.get('tool_calls')
            if tool_call_data and isinstance(tool_call_data, list) and len(tool_call_data) > 0:
                 first_tool_call_legacy = tool_call_data[0]
                 if first_tool_call_legacy.get('function', {}).get('name') == ChartRequestArgs.__name__:
                    try:
                        import json
                        tool_args = json.loads(first_tool_call_legacy.get('function', {}).get('arguments', '{}'))
                        print(f"Chart Decision: Parsed Tool Call Args (from additional_kwargs): {tool_args}")
                    except json.JSONDecodeError:
                        print("Chart Decision Warning: Failed to parse tool call args from additional_kwargs.")
                 else:
                     print(f"Chart Decision Warning: Unexpected function name in additional_kwargs: {first_tool_call_legacy.get('function', {}).get('name')}")
            else:
                print("Chart Decision Warning: LLM did not make the expected tool call.")

        return tool_args # Return the dictionary of args or None

    except Exception as e:
        print(f"Error in decide_chart_request: {e}")
        import traceback
        traceback.print_exc()
        return None # Return None on error

# ========= PDF Generation Helper =========
def generate_report_pdf(markdown_content, chart_image_abs_path=None):
    """Converts Markdown report content (including chart reference) to PDF bytes."""
    
    html_content = markdown(markdown_content, extensions=["fenced_code", "tables"])
    
    # --- Image Embedding Logic --- 
    if chart_image_abs_path and os.path.exists(chart_image_abs_path):
        try:
            # 1. Read image data
            with open(chart_image_abs_path, "rb") as image_file:
                image_data = image_file.read()
            
            # 2. Encode as Base64
            base64_encoded_data = base64.b64encode(image_data).decode('utf-8')
            
            # 3. Create data URI (assuming PNG, adjust if other formats are possible)
            mime_type = "image/png" 
            data_uri = f"data:{mime_type};base64,{base64_encoded_data}"
            print(f"PDF Generation: Created data URI (length: {len(data_uri)})")

            # 4. Find the relative path pattern in the original markdown content
            chart_path_match = re.search(r'!\[.*?\]\((/static/generated_charts/.*?)\)', markdown_content)
            
            if chart_path_match:
                chart_relative_path = chart_path_match.group(1)
                print(f"PDF Generation: Found relative path in markdown: {chart_relative_path}")
                
                # 5. Find and replace the <img> tag's src in the generated HTML
                img_tag_pattern = f'<img [^>]*src="{re.escape(chart_relative_path)}"[^>]*>'
                # More flexible replacement focusing only on the src attribute
                def replace_src(match):
                    return match.group(0).replace(f'src="{chart_relative_path}"' , f'src="{data_uri}"')

                html_content_new, replacements_made = re.subn(
                    img_tag_pattern, 
                    replace_src,
                    html_content,
                    count=1 
                )
                
                if replacements_made > 0:
                    html_content = html_content_new
                    print(f"PDF Generation: Replaced relative src '{chart_relative_path}' with data URI.")
                else:
                    print(f"PDF Generation Warning: Could not find matching <img> tag src for relative path '{chart_relative_path}' in HTML content.")
                    # Fallback: try replacing raw string - less reliable but might catch cases
                    # where markdown parser changed attributes around src
                    if f'src="{chart_relative_path}"' in html_content:
                        html_content = html_content.replace(f'src="{chart_relative_path}"' , f'src="{data_uri}"' , 1)
                        print(f"PDF Generation: (Fallback) Replaced raw src string with data URI.")
                    else:
                        print(f"PDF Generation Warning: Fallback replacement also failed.")
            else:
                print("PDF Generation Warning: Could not find chart path pattern in markdown content.")
        except Exception as e:
            print(f"PDF Generation Error during image embedding: {e}")
            # Continue without the image if embedding fails

    elif chart_image_abs_path:
        print(f"PDF Generation Warning: Provided chart path does not exist: {chart_image_abs_path}")
    else:
         print("PDF Generation: No chart path provided for embedding.")
    # --- End Image Embedding Logic ---

    # Basic CSS for PDF styling
    css = CSS(string='''
        @page { size: A4; margin: 2cm; }
        body { font-family: sans-serif; line-height: 1.4; }
        h1, h2, h3, h4, h5, h6 { font-weight: bold; margin-top: 1.5em; margin-bottom: 0.5em; }
        h1 { font-size: 1.8em; }
        h2 { font-size: 1.5em; }
        h3 { font-size: 1.2em; }
        p { margin-bottom: 1em; }
        ul, ol { margin-left: 20px; margin-bottom: 1em; }
        li { margin-bottom: 0.5em; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 1em; }
        th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        img { max-width: 100%; height: auto; display: block; margin: 1em auto; }
        pre { background-color: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; }
        code { font-family: monospace; }
    ''')
    
    font_config = FontConfiguration()

    # Generate PDF bytes using the modified HTML
    try:
        html = HTML(string=html_content)
        pdf_bytes = html.write_pdf(stylesheets=[css], font_config=font_config)
        print("PDF Generation: PDF bytes created successfully.")
        return pdf_bytes
    except Exception as e:
        print(f"Error generating PDF with WeasyPrint: {e}")
        return None

# ========= Spreadsheet Helpers =========

def extract_table_data_all_sheets(file_path, max_rows=30, max_cols=10):
    """Extracts data from the first sheet into a pandas DataFrame 
       and also creates a text representation of all sheets (limited rows/cols)."""
    
    # Read the first sheet into a pandas DataFrame
    try:
        df = pd.read_excel(file_path, sheet_name=0) # Read first sheet (index 0)
    except Exception as e:
        print(f"Error reading Excel file into DataFrame: {e}")
        df = pd.DataFrame() # Return empty DataFrame on error

    # Create limited text representation (existing logic)
    all_data = []    
    try:
        wb = load_workbook(file_path) # Need to reload for openpyxl processing
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            all_data.append(f"### Sheet: {sheet}")
            # Limit rows/cols for text preview
            preview_rows = min(ws.max_row, max_rows)
            preview_cols = min(ws.max_column, max_cols)
            for row in ws.iter_rows(min_row=1, max_row=preview_rows, max_col=preview_cols, values_only=True):
                row_text = "\t".join(str(cell) if cell is not None else "" for cell in row)
                all_data.append(row_text)
            all_data.append("")  # spacing
    except Exception as e:
         print(f"Error processing sheets with openpyxl: {e}")
         all_data.append("[Error processing sheet data for text preview]")

    return df, "\n".join(all_data)

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

def generate_dynamic_prompts(df, max_prompts=3):
    """Generates a list of relevant prompt suggestions based on DataFrame columns."""
    prompts = []
    if df is None or df.empty:
        return prompts

    categorical_cols = df.select_dtypes(include=['object', 'category']).columns
    numerical_cols = df.select_dtypes(include=['number']).columns

    # Suggestion 1: Value counts for first categorical column
    if len(categorical_cols) > 0:
        col_name = categorical_cols[0]
        # Check if column has a reasonable number of unique values for counts
        if df[col_name].nunique() < 50: # Avoid suggesting counts for ID-like columns
             prompts.append(f"Show value counts for '{col_name}'.")
    
    # Suggestion 2: Average for first numerical column
    if len(numerical_cols) > 0:
        prompts.append(f"What is the average of '{numerical_cols[0]}'?")

    # Suggestion 3: Unique values for second categorical column (if exists)
    if len(categorical_cols) > 1:
         col_name = categorical_cols[1]
         if df[col_name].nunique() < 50:
            prompts.append(f"What are the unique values in '{categorical_cols[1]}'?")
    # If no second categorical, try sum of first numerical (if not already added)
    elif len(numerical_cols) > 0 and len(prompts) < max_prompts:
         prompts.append(f"What is the sum of '{numerical_cols[0]}'?")

    # Add more generic prompts if we still have space
    if len(prompts) < max_prompts:
        prompts.append("Summarize the first few rows.")
    if len(prompts) < max_prompts and len(df.columns) > 0:
         prompts.append(f"What are the column names?")

    return prompts[:max_prompts]

# ========= Utility Helpers =========

def extract_cell(text):
    match = re.search(r"\b([A-Z]{1,2}[0-9]{1,4})\b", text.upper())
    return match.group(1) if match else "A1"

def is_cell_reference(text):
    return bool(re.search(r"\b([A-Z]{1,2}[0-9]{1,4})\b", text.upper()))

# ========= Helper functions for plotting (add these) =========
def _plot_bar(df, col_name, chart_path):
    """Generates and saves a bar chart."""
    try:
        if col_name not in df.columns:
            print(f"Plot Error: Column '{col_name}' not found for bar chart.")
            return False
        if df[col_name].nunique() > 50 or df[col_name].nunique() < 2:
            print(f"Plot Error: Column '{col_name}' has unsuitable number of unique values ({df[col_name].nunique()}) for bar chart.")
            return False
        
        plt.figure(figsize=(10, 6))
        df[col_name].value_counts().plot(kind='bar')
        plt.title(f'Counts by {col_name}')
        plt.xlabel(col_name)
        plt.ylabel('Count')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.savefig(chart_path)
        plt.close()
        print(f"Plot Success: Saved bar chart for '{col_name}' to {chart_path}")
        return True
    except Exception as e:
        print(f"Plot Error (Bar): {e}")
        return False

def _plot_histogram(df, col_name, chart_path):
    """Generates and saves a histogram."""
    try:
        if col_name not in df.columns:
            print(f"Plot Error: Column '{col_name}' not found for histogram.")
            return False
        if not pd.api.types.is_numeric_dtype(df[col_name]):
            print(f"Plot Error: Column '{col_name}' is not numeric for histogram.")
            return False
        if df[col_name].nunique() <= 1:
            print(f"Plot Error: Column '{col_name}' needs more than 1 unique value for histogram.")
            return False
        
        plt.figure(figsize=(10, 6))
        df[col_name].plot(kind='hist', bins=15)
        plt.title(f'Distribution of {col_name}')
        plt.xlabel(col_name)
        plt.ylabel('Frequency')
        plt.tight_layout()
        plt.savefig(chart_path)
        plt.close()
        print(f"Plot Success: Saved histogram for '{col_name}' to {chart_path}")
        return True
    except Exception as e:
        print(f"Plot Error (Histogram): {e}")
        return False

def _plot_scatter(df, col1_name, col2_name, chart_path):
    """Generates and saves a scatter plot."""
    try:
        if col1_name not in df.columns or col2_name not in df.columns:
            print(f"Plot Error: One or both columns ('{col1_name}', '{col2_name}') not found for scatter.")
            return False
        if not pd.api.types.is_numeric_dtype(df[col1_name]) or not pd.api.types.is_numeric_dtype(df[col2_name]):
            print(f"Plot Error: Both columns ('{col1_name}', '{col2_name}') must be numeric for scatter.")
            return False
            
        plt.figure(figsize=(10, 6))
        plt.scatter(df[col1_name], df[col2_name])
        plt.title(f'Scatter Plot of {col1_name} vs {col2_name}')
        plt.xlabel(col1_name)
        plt.ylabel(col2_name)
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(chart_path)
        plt.close()
        print(f"Plot Success: Saved scatter plot for '{col1_name}' vs '{col2_name}' to {chart_path}")
        return True
    except Exception as e:
        print(f"Plot Error (Scatter): {e}")
        return False

def generate_plot_ideas(df):
    """
    Uses LLM to generate three interactive plot ideas based on the uploaded xlsx file.
    For each idea, it generates a title, description, and a detailed specification
    for plotting.
    Returns a list of dictionaries with 'title', 'description', and 'specification' for each plot idea.
    """
    if df is None or df.empty:
        # Return default ideas with placeholder specifications if df is empty
        default_spec = {"plot_type": "info", "message": "No data available"}
        return [
            {"title": "Basic Bar Chart", "description": "Visualize categorical data distributions", "specification": default_spec},
            {"title": "Simple Time Series", "description": "Track changes over time for key metrics", "specification": default_spec},
            {"title": "Data Distribution", "description": "Examine numerical value distribution", "specification": default_spec}
        ]
        
    column_summary = get_column_summary(df)
    
    # Create a more detailed data summary for better context
    data_sample = ""
    numeric_cols = df.select_dtypes(include=['number']).columns
    cat_cols = df.select_dtypes(include=['object', 'category']).columns
    
    try:
        if len(numeric_cols) > 0:
            data_sample += "\nNumerical Column Statistics:\n"
            for col in numeric_cols[:5]:
                stats = df[col].agg(['min', 'max', 'mean', 'std', lambda x: x.isna().sum()]).to_dict()
                data_sample += f"- {col}: min={stats.get('min', 'N/A')}, max={stats.get('max', 'N/A')}, mean={stats.get('mean', 'N/A'):.2f}, std={stats.get('std', 'N/A'):.2f}, nulls={stats.get('<lambda>', 0)}\n"
        
        if len(cat_cols) > 0:
            data_sample += "\nTop Values in Categorical Columns:\n"
            for col in cat_cols[:3]:
                top_values = df[col].value_counts().head(3).to_dict()
                data_sample += f"- {col} top values: {top_values}, nulls={df[col].isna().sum()}\n"
    except Exception as e:
        print(f"Error generating data sample: {e}")
        data_sample = "\nCould not generate detailed data sample.\n" # Provide fallback text
    
    system = """You are a data visualization expert specializing in interactive data exploration. 
Based on the detailed column summary and data sample provided, generate THREE specific, insightful, and highly relevant plot ideas.

**For EACH of the THREE plot ideas, provide:**
1.  A concise, specific **title** (3-5 words) indicating what is shown.
2.  A short **description** (1-2 sentences) explaining the insight the visualization provides.
3.  A detailed **specification** dictionary containing the necessary information to *programmatically* create the plot. The specification keys should include:
    *   `plot_type`: (string) e.g., 'bar', 'histogram', 'scatter', 'line', 'pie', 'box'. Choose the *most appropriate* type.
    *   `x_column`: (string or null) The name of the column for the x-axis. Use null if not applicable (e.g., pie chart).
    *   `y_column`: (string or null) The name of the column for the y-axis. Use null if the y-axis represents frequency/count (e.g., histogram, count bar chart).
    *   `aggregation`: (string or null) How to aggregate `y_column` if specified (e.g., 'sum', 'mean', 'median', 'count'). Use 'count' for bar charts showing frequency, null otherwise or if `y_column` is null.
    *   `color_column`: (string or null) Optional column to use for coloring (e.g., different categories in a scatter plot).
    *   `time_unit`: (string or null) Optional for time series ('D', 'W', 'M', 'Y') if aggregation is needed.
    *   `rationale`: (string) Briefly explain *why* this plot and these columns were chosen based on the data.

**Guidelines:**
*   Focus on visualizations revealing genuine insights about THIS SPECIFIC dataset.
*   Ensure each idea highlights different aspects and uses potentially different plot types.
*   Tailor suggestions to the actual columns, data types, and values present (use exact column names).
*   Base your choices on analytical value.

Return your response as a VALID Python list of dictionaries with this exact format:
[
  {
    "title": "...", 
    "description": "...", 
    "specification": {"plot_type": "...", "x_column": "...", ... "rationale": "..."}
  },
  { ... },
  { ... }
]
"""
    
    user = f"""
**Column Summary:**
{column_summary}

**Data Sample Information:**
{data_sample}

Generate THREE tailored plot ideas with titles, descriptions, and detailed specifications in the specified Python list format.
"""
    
    plot_ideas = [] # Initialize default empty list
    
    try:
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = response.content.strip()
        
        # Improved extraction focusing on the JSON-like structure
        match = re.search(r'(\[.*\])', content, re.DOTALL)
        if match:
            list_text = match.group(1)
            try:
                # Use json.loads for more robust parsing than eval
                import json
                parsed_ideas = json.loads(list_text) 
                
                if isinstance(parsed_ideas, list) and len(parsed_ideas) > 0:
                    valid_ideas = []
                    for idea in parsed_ideas[:3]:
                        # Validate structure more thoroughly
                        if (isinstance(idea, dict) and 
                            'title' in idea and isinstance(idea['title'], str) and
                            'description' in idea and isinstance(idea['description'], str) and
                            'specification' in idea and isinstance(idea['specification'], dict) and
                            'plot_type' in idea['specification'] and isinstance(idea['specification']['plot_type'], str) and # Basic check
                            'rationale' in idea['specification'] and isinstance(idea['specification']['rationale'], str)): # Check rationale presence
                            
                            # Basic cleaning/limiting
                            idea['title'] = idea['title'][:60]
                            idea['description'] = idea['description'][:200]
                            idea['specification']['plot_type'] = idea['specification'].get('plot_type', 'unknown').lower()
                            # Ensure required spec fields exist, provide defaults if missing
                            idea['specification'].setdefault('x_column', None)
                            idea['specification'].setdefault('y_column', None)
                            idea['specification'].setdefault('aggregation', None)
                            idea['specification'].setdefault('color_column', None)
                            idea['specification'].setdefault('time_unit', None)
                            
                            valid_ideas.append(idea)
                    
                    if valid_ideas:
                        plot_ideas = valid_ideas # Assign successfully parsed and validated ideas
                        
            except json.JSONDecodeError as json_e:
                print(f"Error parsing plot ideas JSON: {json_e}")
                # Keep plot_ideas as empty, fallback will be triggered
            except Exception as e:
                print(f"Error processing parsed plot ideas: {e}")
                # Keep plot_ideas as empty, fallback will be triggered
        else:
             print("Could not find JSON-like list structure in LLM response for plot ideas.")
             # Keep plot_ideas as empty, fallback will be triggered

        # If parsing failed or returned no valid ideas, use a fallback
        if not plot_ideas:
            print("Falling back to default plot ideas.")
            default_spec = {
                "plot_type": "fallback", 
                "x_column": None, "y_column": None, "aggregation": None, 
                "color_column": None, "time_unit": None,
                "rationale": "Fallback due to parsing error or missing data."
            }
            plot_ideas = [
                {"title": "Column Distribution Analysis", "description": "Visualize key value distributions", "specification": default_spec},
                {"title": "Data Correlation Insights", "description": "Explore relationships between numerical variables", "specification": default_spec},
                {"title": "Trend Visualization", "description": "Analyze changes across categories or time", "specification": default_spec}
            ]
        
        return plot_ideas[:3] # Ensure max 3 ideas are returned
        
    except Exception as e:
        print(f"Error generating plot ideas: {e}")
        # Final fallback in case of major error in the try block
        default_spec = {
            "plot_type": "error", 
            "x_column": None, "y_column": None, "aggregation": None, 
            "color_column": None, "time_unit": None,
            "rationale": "Fallback due to exception during generation."
            }
        return [
            {"title": "Basic Data Overview", "description": "Simple visualization of core metrics", "specification": default_spec},
            {"title": "Column Relationships", "description": "Explore connections between data points", "specification": default_spec},
            {"title": "Value Distribution", "description": "See how values are distributed", "specification": default_spec}
        ]
