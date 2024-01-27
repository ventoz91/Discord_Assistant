from flask import Flask, request, render_template, send_from_directory
from werkzeug.utils import secure_filename
import os
import time
import subprocess
from datetime import datetime

UPLOAD_FOLDER = r'.\recordings'

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'audioFile' not in request.files:
        return 'No file part', 400
    file = request.files['audioFile']
    if file.filename == '':
        return 'No selected file', 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    # Generate a unique filename for the output
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    output_filename = f"{filename.rsplit('.', 1)[0]}_{timestamp}.wav"
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

    # Convert RIFF to WAV using ffmpeg
    try:
        subprocess.run(["ffmpeg", "-i", file_path, "-acodec", "pcm_s16le", output_path], check=True)
    except subprocess.CalledProcessError as e:
        return f'Error converting file: {e}', 500

    # Delay before trying to delete the file
    time.sleep(1)  # Delay for 1 second

    # Try to delete the original file after conversion
    try:
        os.remove(file_path)
    except PermissionError as e:
        print(f"Permission error when deleting file {file_path}: {e}")
        return f'File uploaded but unable to delete original file', 200

    return f'File uploaded and converted to WAV successfully: {output_filename}', 200

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)








