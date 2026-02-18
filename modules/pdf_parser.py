from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar, LTTextLine

def find_fillable_fields(pdf_path):
    fields = []
    for page_layout in extract_pages(pdf_path):
        for element in page_layout:
            if isinstance(element, LTTextContainer):
                for text_line in element:
                    line_text = text_line.get_text()
                    
                    # Si la línea tiene puntos o guiones, buscamos grupos individuales
                    if ".." in line_text or "___" in line_text:
                        current_group = []
                        last_x = 0
                        
                        for char in text_line:
                            if isinstance(char, LTChar) and char.get_text() in "._":
                                # Si hay un salto grande entre caracteres, es un campo nuevo
                                if abs(char.bbox[0] - last_x) > 10 and current_group:
                                    fields.append(save_field(current_group, page_layout.pageid, line_text))
                                    current_group = []
                                
                                current_group.append(char)
                                last_x = char.bbox[2] # Bbox[2] es el final del caracter
                        
                        if current_group:
                            fields.append(save_field(current_group, page_layout.pageid, line_text))
    return fields

def save_field(char_list, page_id, full_text):
    first_char = char_list[0]
    # Intentamos sacar una etiqueta limpia del texto de la línea
    label = full_text.replace(".", "").replace("_", "").strip()
    if not label: label = "Dato"
    
    return {
        "x": first_char.bbox[0],
        "y": first_char.bbox[1],
        "page": page_id,
        "label": label[:20], # Contexto de la línea
        "raw_text": full_text # Para el ajuste inteligente
    }