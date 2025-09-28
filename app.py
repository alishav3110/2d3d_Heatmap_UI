import pandas as pd
import vertexai
from vertexai.generative_models import GenerativeModel
import re
import os
import io
from flask import Flask, request, send_file, render_template_string, redirect, url_for

# --- Configuration (from your original code) ---
# TODO: Replace with your Google Cloud project ID
PROJECT_ID = "integral-iris-449816-g3"  # <--- IMPORTANT: KEEP THIS
LOCATION = "us-central1"

app = Flask(__name__)

# NOTE: The install_if_missing logic is removed as dependencies will be managed
# in requirements.txt and Dockerfile.

def generate_visualization_with_gemini(df, excel_filename, sheet_name):
    """
    Reads data from a DataFrame (instead of a file), sends it to the Gemini model,
    and returns the paths to the generated plot images.
    """
    # --- Step 1 & 2: Convert DataFrame to CSV Text ---
    print(f"Step 1 & 2: Converting DataFrame to CSV text...")
    csv_data_string = df.to_csv()

    # --- Step 3: Prepare Detailed Instructions for the AI ---
    print("Step 3: Preparing detailed instructions (prompt) for the Gemini AI...")
    base_name = os.path.splitext(excel_filename)[0]
    sheet_str = str(sheet_name).replace(" ", "_")
    output_filename_composite = f"{base_name}_sheet_{sheet_str}_composite_plot.png"
    output_filename_combined = f"{base_name}_sheet_{sheet_str}_combined_ctp_graph.png"
    
    # Store images temporarily in the /tmp directory (standard for Cloud Run)
    composite_path = os.path.join("/tmp", output_filename_composite)
    combined_path = os.path.join("/tmp", output_filename_combined)

    # The prompt is updated to write files to the /tmp directory.
    prompt = f"""
    You are an expert Python data visualization programmer. Your task is to write a single, runnable Python script that generates TWO separate plot images from the data provided.

    Here is the data in CSV format:
    --- START OF DATA ---
    {csv_data_string}
    --- END OF DATA ---

    Please write a Python script that contains two separate functions and then calls both of them.

    ### Function 1: Create Composite Plot
    This function must perform these actions:
    1. Import all necessary libraries: pandas, numpy, matplotlib, matplotlib.gridspec, matplotlib.colors, adjustText, and io.
    2. Read the provided CSV data string into a pandas DataFrame using io.StringIO.
    3. Separate the data into `main_data`, `longitudinal_ctp`, and `circumferential_ctp`.
    4. Use a custom LinearSegmentedColormap with ["red", "yellow", "green"].
    5. The plot must have 'Longitudinal Position' (M-values) on the Y-axis and 'Circumferential Position' (C-values) on the X-axis.
    6. Automatically find and mark all row/column minima on the central contour plot.
    7. Use `adjustText` to create clear, non-overlapping labels for the marked points.
    8. The top panel must plot `longitudinal_ctp` and be titled 'Circumferential CTP'.
    9. The right-side panel must plot `circumferential_ctp` and be titled 'Longitudinal CTP'.
    10. Save this plot as a PNG file to the path: '{composite_path}'.

    ### Function 2: Create Combined CTP Line Graph
    This function must perform these actions:
    1. Create a new figure.
    2. Plot both `longitudinal_ctp` and `circumferential_ctp` on the same axes.
    3. Include a legend to distinguish the two lines.
    4. Add a title 'Combined CTP Trends' and appropriate axis labels.
    5. Save this plot as a PNG file to the path: '{combined_path}'.

    CRITICAL INSTRUCTION: Your entire response must be only the raw Python code required to define and call these two functions. Do not include any extra text, explanations, or markdown formatting.
    """

    # --- Step 4: Contact Gemini ---
    print(f"Step 4: Connecting to Gemini via Vertex AI (Project: {PROJECT_ID})...")
    try:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        model = GenerativeModel("gemini-2.5-pro")
        
        print("  > Sending instructions to Gemini...")
        response = model.generate_content(prompt, generation_config={"temperature": 0.0})
        generated_code = re.sub(r'```python\n|```', '', response.text).strip()
        
    except Exception as e:
        print(f"  > An error occurred while communicating with the Gemini API: {e}")
        return None, None

    # --- Step 5: Execute the AI's Code ---
    print("Step 5: Received plotting script from Gemini.")

    print("  > Executing the AI-generated code to create the plots...")
    
    # Add io and the CSV data string as failsafes/global variables for the script
    # to access, as the script is only code, not functions with arguments.
    # Note: exec is generally discouraged for unknown code, but here the source is the trusted AI model.
    try:
        # Prepend necessary imports and the CSV data string
        preamble = f"""
import io
csv_data_string = r'''{csv_data_string}'''
"""
        full_script = preamble + generated_code
        
        # Execute the script
        exec(full_script, globals())

        print(f"\nSuccess! Plots have been generated.")
        return composite_path, combined_path
    except Exception as e:
        print(f"  > An error occurred while executing the code from Gemini: {e}")
        print("\n--- Code Generated by Gemini (for debugging) ---")
        print(generated_code)
        return None, None

# HTML Template for the Web UI
HTML_TEMPLATE = """
<!doctype html>
<title>Gemini Visualization App</title>
<h1>Upload Excel/CSV for Visualization</h1>
<form method=post enctype=multipart/form-data>
  <label for="file">Excel/CSV File:</label>
  <input type=file name=file id=file required><br><br>
  <label for="sheet">Sheet Name/Index (e.g., 'Sheet1' or '0'):</label>
  <input type=text name=sheet id=sheet value="0" required><br><br>
  <input type=submit value=Visualize>
</form>

{% if message %}
    <p style="color: green;">{{ message }}</p>
{% endif %}

{% if error %}
    <p style="color: red;">Error: {{ error }}</p>
{% endif %}

{% if composite_url and combined_url %}
    <h2>Generated Plots</h2>
    <p>Right-click and "Save Image As..." to download.</p>
    <div>
        <h3>Composite Plot</h3>
        <img src="{{ composite_url }}" style="max-width: 80%; border: 1px solid #ccc;"><br>
        <a href="{{ composite_url }}" download>Download Composite Plot</a>
    </div>
    <hr>
    <div>
        <h3>Combined CTP Line Graph</h3>
        <img src="{{ combined_url }}" style="max-width: 80%; border: 1px solid #ccc;"><br>
        <a href="{{ combined_url }}" download>Download Combined Plot</a>
    </div>
{% endif %}
"""

# Route for file upload and processing
@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template_string(HTML_TEMPLATE, error='No file part')
        
        file = request.files['file']
        sheet_input = request.form.get('sheet', '0')

        if file.filename == '':
            return render_template_string(HTML_TEMPLATE, error='No selected file')
        
        if file:
            filename = file.filename
            file_extension = os.path.splitext(filename)[1].lower()

            try:
                # Read the file into a DataFrame
                file_stream = io.BytesIO(file.read())
                
                if file_extension in ['.xlsx', '.xls']:
                    sheet_identifier = int(sheet_input) if sheet_input.isdigit() else sheet_input
                    df = pd.read_excel(file_stream, sheet_name=sheet_identifier, index_col=0)
                elif file_extension == '.csv':
                    df = pd.read_csv(file_stream, index_col=0)
                else:
                    return render_template_string(HTML_TEMPLATE, error=f'Unsupported file type: {file_extension}. Please use .xlsx, .xls, or .csv.')

                # Generate the plots
                composite_path, combined_path = generate_visualization_with_gemini(df, filename, sheet_input)

                if composite_path and combined_path:
                    # After generation, redirect to the main page with image URLs
                    return render_template_string(
                        HTML_TEMPLATE, 
                        message=f"Successfully generated plots from {filename}.",
                        composite_url=url_for('serve_image', filename=os.path.basename(composite_path)),
                        combined_url=url_for('serve_image', filename=os.path.basename(combined_path))
                    )
                else:
                    return render_template_string(HTML_TEMPLATE, error="Plot generation failed. Check Cloud Run logs for details.")

            except Exception as e:
                app.logger.error(f"Processing error: {e}")
                return render_template_string(HTML_TEMPLATE, error=f"An internal error occurred during processing: {e}")

    return render_template_string(HTML_TEMPLATE)

# Route to serve the generated images from /tmp
@app.route('/images/<filename>')
def serve_image(filename):
    file_path = os.path.join("/tmp", filename)
    if os.path.exists(file_path):
        return send_file(file_path, mimetype='image/png')
    else:
        return "Image not found", 404

if __name__ == '__main__':
    # Cloud Run/Gunicorn will set the PORT environment variable
    port = int(os.environ.get('PORT', 8080))
    # Running in debug mode for local testing is fine, but Gunicorn is used for deployment
    app.run(host='0.0.0.0', port=port, debug=True)
