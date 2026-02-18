import io
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

def process_pdf_fields(input_pdf_bytes, answers, fields, offset_x=0, offset_y=5):
    reader = PdfReader(io.BytesIO(input_pdf_bytes))
    writer = PdfWriter()

    for page_num in range(len(reader.pages)):
        packet = io.BytesIO()
        can = canvas.Canvas(packet)
        page = reader.pages[page_num]
        
        # Filtramos campos de esta página (pdfminer usa base 1 para páginas)
        page_fields = [f for f in fields if f['page'] == page_num + 1]
        
        for i, field in enumerate(page_fields):
            # Calculamos el índice global de la respuesta
            # (Esto es necesario si el PDF tiene varias páginas)
            global_index = i # Si es solo 1 página, esto vale.
            
            if i < len(answers):
                current_x = field['x'] + offset_x
                current_y = field['y'] + offset_y
                
                # AJUSTE INTELIGENTE:
                # Si el campo es el primero o detectamos "D./Dña" cerca
                if i == 0 or "D./D" in field.get('text_before', ''):
                    current_x += 35 # Espacio para no pisar la etiqueta fija
                
                can.setFont("Helvetica", 10)
                can.drawString(current_x, current_y, str(answers[i]))
        
        # IMPORTANTE: El save y la mezcla van FUERA del bucle de los campos
        can.save()
        packet.seek(0)
        
        new_pdf = PdfReader(packet)
        if len(new_pdf.pages) > 0:
            page.merge_page(new_pdf.pages[0])
        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output