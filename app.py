from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return "Vidhide Downloader Backend is Live and Running!"

@app.route('/get-download-link', methods=['GET'])
def get_download_link():
    file_code = request.args.get('code')
    if not file_code:
        return jsonify({'success': False, 'message': 'File code is required'}), 400

    direct_link = f"https://vidhidepro.com/d/{file_code}"
    
    return jsonify({
        'success': True,
        'download_url': direct_link
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
    
