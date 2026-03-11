from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import io
import datetime
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from pdf_generator import generate_pdf
from docx_generator import generate_docx

app = Flask(__name__)
# Atļaujam Shopify lapai sūtīt pieprasījumus uz šo serveri
CORS(app) 

GOOGLE_DRIVE_FOLDER_ID = "1vqhkHGH9WAMaFnXtduyyjYdEzHMx0iX9" 
TOKEN_FILE = "token.json"
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_drive_service():
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.valid:
            return build('drive', 'v3', credentials=creds)
    return None

def upload_to_drive(file_buffer, filename, mime_type):
    try:
        service = get_drive_service()
        if not service: return False
        file_metadata = {'name': filename, 'parents': [GOOGLE_DRIVE_FOLDER_ID]}
        file_buffer.seek(0)
        media = MediaIoBaseUpload(file_buffer, mimetype=mime_type, resumable=True)
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_buffer.seek(0)
        return True
    except Exception as e:
        print(f"Drive Error: {e}")
        return False

@app.route('/generate/<file_type>', methods=['POST'])
def generate_doc(file_type):
    data = request.json
    
    # Ģenerējam faila nosaukumu
    doc_id = data.get('doc_id', 'BR_0000').replace(" ", "_")
    doc_type_name = data.get('doc_type', 'Pavadzime').replace(" ", "_")
    
    if file_type == 'pdf':
        buffer = generate_pdf(data)
        filename = f"{doc_type_name}_{doc_id}.pdf"
        mime = "application/pdf"
    elif file_type == 'docx':
        buffer = generate_docx(data)
        filename = f"{doc_type_name}_{doc_id}.docx"
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        return jsonify({"error": "Nezināms formāts"}), 400

    # Augšupielādējam Google Drive
    upload_to_drive(buffer, filename, mime)

    # Nosūtām atpakaļ lietotājam lejupielādei
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype=mime
    )

if __name__ == '__main__':
    # Serveris klausās uz portu
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
