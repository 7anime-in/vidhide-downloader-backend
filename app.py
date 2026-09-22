from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return "Vidhide Direct Downloader Backend Active!"

@app.route('/get-download-link', methods=['GET'])
def get_download_link():
    file_code = request.args.get('code')
    if not file_code:
        return jsonify({'success': False, 'message': 'File code is required'}), 400

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': f'https://vidhidepro.com/embed/{file_code}'
    }

    embed_url = f"https://vidhidepro.com/embed/{file_code}"

    try:
        # Vidhide embed page HTML fetch karna
        response = requests.get(embed_url, headers=headers, timeout=10)
        html = response.text

        # JavaScript code se direct source video link extract karna
        source_match = re.search(r'file\s*:\s*["\'](https?://[^"\']+)["\']', html)
        
        if source_match:
            direct_stream_url = source_match.group(1)
            return jsonify({
                'success': True,
                'download_url': direct_stream_url
            })
        else:
            # Backup link agar direct source scrape na ho paye
            return jsonify({
                'success': True,
                'download_url': f"https://vidhidepro.com/d/{file_code}"
            })

    except Exception as e:
        print("Extraction Error:", e)
        return jsonify({
            'success': False,
            'download_url': f"https://vidhidepro.com/d/{file_code}"
        })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
    
