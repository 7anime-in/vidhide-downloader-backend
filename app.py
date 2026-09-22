from flask import Flask, jsonify, request
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)  # Direct browser requests allow karne ke liye

# Teri dono Vidhide API Keys (Primary + Backup)
API_KEYS = [
    "47650ignlp8w9m7zimhp7",  # Account 1
    "47699lkja012c5mp3mw23"   # Account 2
]

@app.route('/get-download-link', methods=['GET'])
def get_download_link():
    file_code = request.args.get('code')
    
    if not file_code:
        return jsonify({"success": False, "message": "File Code missing hai!"}), 400

    # Dono API Keys ko ek-ek karke check karega (Fallback mechanism)
    for key in API_KEYS:
        api_url = f"https://vidhidepro.com/api/file/direct_link?key={key}&file_code={file_code}"
        
        try:
            response = requests.get(api_url, timeout=8)
            data = response.json()

            # Agar API response success (200) deta hai
            if data.get('status') == 200 and 'result' in data and 'download_url' in data['result']:
                return jsonify({
                    "success": True,
                    "download_url": data['result']['download_url']
                })
        except Exception as e:
            continue  # Agli Key try karega agar error aata hai

    # Agar dono Keys fail ho jayein
    return jsonify({
        "success": False, 
        "message": "Direct link generate nahi ho paya. Keys limit full ho sakti hai."
    }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

