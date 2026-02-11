import fitz  # PyMuPDF
import re

class FileProcessor:
    def extract_text(self, uploaded_file):
        """Extracts text from Streamlit UploadedFile object."""
        try:
            if uploaded_file.type == "application/pdf":
                doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
                text = ""
                for page in doc:
                    text += page.get_text() + "\n"
                return text
            else:
                # Fallback for text/md
                return str(uploaded_file.read(), "utf-8")
        except Exception as e:
            return f"Error extracting text: {e}"

    def chunk_text(self, text, chunk_size=500):
        """Splits text into chunks of roughly 'chunk_size' words."""
        words = text.split()
        chunks = []
        current_chunk = []
        current_count = 0
        
        for word in words:
            current_chunk.append(word)
            current_count += 1
            
            if current_count >= chunk_size:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_count = 0
                
        if current_chunk:
            chunks.append(" ".join(current_chunk))
            
        return chunks

file_processor = FileProcessor()
