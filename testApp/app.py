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
from openai import OpenAI
from dummy_des import dummy_description

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

key = "add key here"
client = OpenAI(api_key=key)

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
    
    # Extract content with formatting from the PDF
    extracted_content = extract_content_with_formatting(file)
    
    # Extract text content for AI processing and display
    text_content = extract_text_content(extracted_content)
    
    # Get AI response
    response = client.chat.completions.create(
        messages=[{
            "role": "user",
            "content": f"Improve the following resume text. Do not modify any text above the '---PERSONAL_INFO_END---' line. For the content below the marker, maintain the exact structure, including line breaks, bullet points, and special characters. Focus on enhancing language and impact without changing the overall format or adding new lines:\n\n{text_content}\n\nJob description:\n\n{dummy_description}",
        }],
        model="gpt-3.5-turbo",
    )
    
    ai_response = response.choices[0].message.content
    
    # Update the extracted content with AI suggestions
    updated_content = update_content_with_ai_suggestions(extracted_content, ai_response)
    
    # Reconstruct the PDF with the updated content
    pdf_content = reconstruct_pdf_with_formatting(updated_content)
    
    # Save the reconstructed PDF to a temporary file
    with open(TEMP_PDF_PATH, 'wb') as f:
        f.write(pdf_content)
    
    return render_template('result.html', 
                           extracted_content=text_content, 
                           ai_response=ai_response, 
                           filename=file.filename)

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
                                
                                # Handle bullet points
                                text = str(span.get("text", ""))
                                if text.strip().startswith('•'):
                                    c.drawString(x, y, '•')
                                    c.drawString(x + c.stringWidth('• ', font_name, font_size), y, text[1:].strip())
                                else:
                                    c.drawString(x, y, text)
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
    for page_num, page in enumerate(content_data):
        page_text = []
        for block in page.get("text", []):
            if block.get("type") == 0:  # text block
                for line in block.get("lines", []):
                    line_text = "".join(span.get("text", "") for span in line.get("spans", []))
                    page_text.append(line_text)
        text_content.append("\n".join(page_text))
    
    # Treat the first page as personal information
    return f"{text_content[0]}\n---PERSONAL_INFO_END---\n" + "\n".join(text_content[1:])

def update_content_with_ai_suggestions(original_content, ai_suggestions):
    ai_lines = ai_suggestions.split('\n')
    try:
        personal_info_end = ai_lines.index("---PERSONAL_INFO_END---")
        ai_lines = ai_lines[personal_info_end+1:]  # Remove the marker and personal info
    except ValueError:
        # If marker not found, assume all content needs to be processed
        pass
    
    ai_index = 0
    for page_num, page in enumerate(original_content):
        if page_num == 0:  # Skip the first page (personal information)
            continue
        for block in page['text']:
            if block['type'] == 0:  # text block
                for line in block['lines']:
                    if ai_index < len(ai_lines):
                        new_text = ai_lines[ai_index].strip()
                        ai_index += 1
                        
                        # Preserve original formatting (bullet points, special characters)
                        original_text = "".join(span['text'] for span in line['spans'])
                        if original_text.strip().startswith(('•', '-', '*')):
                            new_text = original_text[0] + ' ' + new_text
                        
                        # Distribute the new text across spans, maintaining original structure
                        words = new_text.split()
                        word_index = 0
                        for span in line['spans']:
                            original_length = len(span['text'])
                            span_words = []
                            while word_index < len(words) and len(' '.join(span_words + [words[word_index]])) <= original_length:
                                span_words.append(words[word_index])
                                word_index += 1
                            new_span_text = ' '.join(span_words)
                            # Pad with spaces to maintain original length
                            span['text'] = new_span_text.ljust(original_length)
    
    return original_content

if __name__ == '__main__':
    app.run(debug=True, port=3000)
