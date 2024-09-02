from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import fitz  # PyMuPDF for PDF processing
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
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
    
    # Extract text from the PDF
    extracted_text = extract_text(file)
    
    # Reconstruct the PDF with the extracted text
    pdf_content = reconstruct_pdf(extracted_text)
    
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

def extract_text(file):
    pdf_document = fitz.open(stream=file.read(), filetype="pdf")
    text = ""
    for page in pdf_document:
        text += page.get_text("text")
    return text

def reconstruct_pdf(text):
    pdf_buffer = BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=letter)
    width, height = letter
    text_object = c.beginText(40, height - 50)
    text_object.setFont("Helvetica", 12)
    
    lines = text.split('\n')
    for line in lines:
        text_object.textLine(line)
        if text_object.getY() < 50:  # Move to a new page if needed
            c.drawText(text_object)
            c.showPage()
            text_object = c.beginText(40, height - 50)
            text_object.setFont("Helvetica", 12)
    
    c.drawText(text_object)
    c.save()

    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()  # Return the content as bytes

if __name__ == '__main__':
    app.run(debug=True)
