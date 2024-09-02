from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import fitz  # PyMuPDF for PDF processing
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import os
import tempfile

app = Flask(__name__)

# Set a unique and secret key for session management
app.secret_key = os.urandom(24)

# Temporary file path for PDF content
TEMP_PDF_PATH = tempfile.mktemp(suffix=".pdf")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files or request.files['file'].filename == '':
        flash('No file selected. Please choose a file to upload.')
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    # Extract text with formatting from the PDF
    extracted_text = extract_text_with_formatting(file)
    
    # Reconstruct the PDF with the extracted text
    pdf_content = reconstruct_pdf_with_formatting(extracted_text)
    
    # Save the reconstructed PDF to a temporary file
    with open(TEMP_PDF_PATH, 'wb') as f:
        f.write(pdf_content)
    
    return render_template('result.html', text=extracted_text, filename=file.filename)

@app.route('/download/<filename>')
def download_file(filename):
    if os.path.exists(TEMP_PDF_PATH):
        return send_file(TEMP_PDF_PATH, as_attachment=True, download_name=filename, mimetype='application/pdf')
    else:
        flash('No PDF content found.')
        return redirect(url_for('index'))

def extract_text_with_formatting(file):
    pdf_document = fitz.open(stream=file.read(), filetype="pdf")
    text_data = []
    
    for page_num, page in enumerate(pdf_document):
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] == 0:  # text block
                for line in block["lines"]:
                    line_text = ""
                    for span in line["spans"]:
                        line_text += span["text"]
                    text_data.append({
                        "text": line_text,
                        "font": span["font"],
                        "size": span["size"],
                        "color": span["color"]
                    })
                    
    return text_data

def extract_color(color_value):
    """Convert the extracted color value to a tuple format suitable for reportlab."""
    if isinstance(color_value, int):
        # Convert integer color (e.g., 0xRRGGBB) to (R, G, B)
        r = (color_value >> 16) & 0xFF
        g = (color_value >> 8) & 0xFF
        b = color_value & 0xFF
        return (r / 255.0, g / 255.0, b / 255.0)
    elif isinstance(color_value, tuple) and len(color_value) == 3:
        # Color might be already in RGB tuple
        return (color_value[0] / 255.0, color_value[1] / 255.0, color_value[2] / 255.0)
    else:
        # Default to black if color is not recognized
        return (0, 0, 0)

def reconstruct_pdf_with_formatting(text_data):
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter)
    content = []
    styles = getSampleStyleSheet()
    
    # Define a mapping from extracted fonts to standard fonts
    font_mapping = {
        'calibri': 'Helvetica',  # Map Calibri to Helvetica
        'times': 'Times-Roman',  # Map Times to Times-Roman
        'arial': 'Helvetica',    # Map Arial to Helvetica
        'courier': 'Courier'     # Map Courier to Courier
        # Add more mappings as needed
    }
    
    for item in text_data:
        # Map the extracted font to a supported font
        font_name = font_mapping.get(item.get('font', '').lower(), 'Helvetica')
        
        # Extract color and ensure it's in the correct format
        color = extract_color(item.get('color', (0, 0, 0)))
        
        # Create a custom style based on extracted formatting
        custom_style = ParagraphStyle(
            name='CustomStyle',
            fontName=font_name,
            fontSize=item.get('size', 12),
            textColor=color
        )
        
        p = Paragraph(item["text"], style=custom_style)
        content.append(p)
        content.append(Spacer(1, 12))  # Add space between paragraphs
        
    doc.build(content)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()  # Return the content as bytes

if __name__ == '__main__':
    app.run(debug=True, port=3000)
