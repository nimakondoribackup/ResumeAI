from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import fitz  # PyMuPDF for PDF processing
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import os
import tempfile
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
import logging
from PIL import Image

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Set a unique and secret key for session management
app.secret_key = os.urandom(24)

# Temporary file path for PDF content
TEMP_PDF_PATH = tempfile.mktemp(suffix=".pdf")

pdfmetrics.registerFont(TTFont('Calibri', 'Calibri.ttf'))
addMapping('Calibri', 0, 0, 'Calibri')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files or request.files['file'].filename == '':
        flash('No file selected. Please choose a file to upload.')
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    # Extract content with formatting from the PDF
    extracted_content = extract_content_with_formatting(file)
    
    # Extract text content for display
    text_content = extract_text_content(extracted_content)
    
    # Reconstruct the PDF with the extracted content
    pdf_content = reconstruct_pdf_with_formatting(extracted_content)
    
    # Save the reconstructed PDF to a temporary file
    with open(TEMP_PDF_PATH, 'wb') as f:
        f.write(pdf_content)
    
    return render_template('result.html', content=text_content, filename=file.filename)

@app.route('/download/<filename>')
def download_file(filename):
    if os.path.exists(TEMP_PDF_PATH):
        return send_file(TEMP_PDF_PATH, as_attachment=True, download_name=filename, mimetype='application/pdf')
    else:
        flash('No PDF content found.')
        return redirect(url_for('index'))

def extract_content_with_formatting(file):
    pdf_document = fitz.open(stream=file.read(), filetype="pdf")
    content_data = []
    
    for page in pdf_document:
        page_dict = page.get_text("dict")
        images = []
        for img in page.get_images(full=True):
            xref = img[0]
            base_image = pdf_document.extract_image(xref)
            images.append({
                "image": base_image["image"],
                "rect": page.get_image_bbox(img),
                "width": base_image["width"],
                "height": base_image["height"]
            })
        
        content_data.append({
            "text": page_dict["blocks"],
            "lines": page.get_drawings(),
            "images": images,
            "links": page.get_links(),
            "width": page.rect.width,
            "height": page.rect.height
        })
    
    pdf_document.close()
    return content_data

def extract_color(color_value):
    try:
        if color_value is None:
            return (0, 0, 0)
        if isinstance(color_value, int):
            r = (color_value >> 16) & 0xFF
            g = (color_value >> 8) & 0xFF
            b = color_value & 0xFF
            return (r / 255.0, g / 255.0, b / 255.0)
        elif isinstance(color_value, (tuple, list)) and len(color_value) == 3:
            return tuple(max(0, min(1, float(c) / 255.0)) for c in color_value)
        else:
            logger.warning(f"Unrecognized color value: {color_value}")
            return (0, 0, 0)
    except Exception as e:
        logger.error(f"Error extracting color: {e}")
        return (0, 0, 0)

def get_font_name(original_font):
    """Map original font names to available ReportLab fonts."""
    font_mapping = {
        'Calibri': 'Helvetica',  # Use Helvetica as a fallback for Calibri
        'Arial': 'Helvetica',
        'Times New Roman': 'Times-Roman',
        # Add more mappings as needed
    }
    return font_mapping.get(original_font, 'Helvetica')

def reconstruct_pdf_with_formatting(content_data):
    pdf_buffer = BytesIO()
    try:
        c = canvas.Canvas(pdf_buffer, pagesize=(float(content_data[0]["width"]), float(content_data[0]["height"])))
    except (IndexError, KeyError, ValueError) as e:
        logger.error(f"Error creating canvas: {e}")
        return None

    for page_num, page_content in enumerate(content_data):
        try:
            # Draw images
            for img in page_content.get("images", []):
                try:
                    image = Image.open(BytesIO(img["image"]))
                    image_path = f"temp_image_{page_num}.png"
                    image.save(image_path)
                    c.drawImage(image_path, img["rect"][0], float(page_content["height"]) - img["rect"][3], 
                                width=img["rect"][2] - img["rect"][0], height=img["rect"][3] - img["rect"][1])
                    os.remove(image_path)
                except Exception as e:
                    logger.error(f"Error drawing image on page {page_num}: {e}")

            # Draw lines and shapes
            for line in page_content.get("lines", []):
                try:
                    color = extract_color(line.get("color"))
                    c.setStrokeColorRGB(*color)
                    c.setLineWidth(max(0.1, float(line.get("width", 1))))
                    if line.get("type") == "l":  # Line
                        x0, y0, x1, y1 = line.get("rect", [0, 0, 0, 0])
                        c.line(x0, float(page_content["height"]) - y0, x1, float(page_content["height"]) - y1)
                    elif line.get("type") in ["re", "qu"]:  # Rectangle or Quad
                        x0, y0, x1, y1 = line.get("rect", [0, 0, 0, 0])
                        c.rect(x0, float(page_content["height"]) - y1, x1 - x0, y1 - y0)
                except Exception as e:
                    logger.error(f"Error drawing line/shape on page {page_num}: {e}")

            # Draw text
            for block in page_content.get("text", []):
                if block.get("type") == 0:  # text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            try:
                                font_name = get_font_name(span.get("font", "Helvetica"))
                                font_size = max(1, float(span.get("size", 12)))
                                c.setFont(font_name, font_size)
                                color = extract_color(span.get("color"))
                                c.setFillColorRGB(*color)
                                x = float(span.get("origin", [0, 0])[0])
                                y = float(page_content["height"]) - float(span.get("origin", [0, 0])[1])
                                c.drawString(x, y, str(span.get("text", "")))
                            except Exception as e:
                                logger.error(f"Error drawing text on page {page_num}: {e}")

            # Add links
            for link in page_content.get("links", []):
                try:
                    rect = link.get("from")
                    if rect:
                        c.linkURL(link.get("uri", ""), (rect[0], float(page_content["height"]) - rect[3], 
                                                        rect[2], float(page_content["height"]) - rect[1]))
                except Exception as e:
                    logger.error(f"Error adding link on page {page_num}: {e}")

            c.showPage()
        except Exception as e:
            logger.error(f"Error processing page {page_num}: {e}")

    try:
        c.save()
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()
    except Exception as e:
        logger.error(f"Error saving PDF: {e}")
        return None

def extract_text_content(content_data):
    text_content = []
    for page in content_data:
        page_text = []
        for block in page.get("text", []):
            if block.get("type") == 0:  # text block
                for line in block.get("lines", []):
                    line_text = ""
                    for span in line.get("spans", []):
                        line_text += span.get("text", "")
                    page_text.append(line_text)
        text_content.append("\n".join(page_text))
    return text_content

if __name__ == '__main__':
    app.run(debug=True, port=3000)
