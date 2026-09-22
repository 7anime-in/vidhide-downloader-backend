from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re

app = Flask(__name__)
CORS(app)  # Mobile Browser Cross-Origin Issue Fix

def unpack_packer(packed_js):
    """Dean Edwards JS Packer ko decode karne ka function"""
    try:
        pattern = r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)"
        match = re.search(pattern, packed_js, re.DOTALL)
        if not match:
            return ""

        payload, radix_str, count_str, symtab_str = match.groups()
        radix = int(radix_str)
        symtab = symtab_str.split('|')

        alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

        def decode_word(word):
            try:
                val = 0
                for char in word:
                    val = val * radix + alphabet.index(char)
                if val < len(symtab) and symtab[val]:
                    return symtab[val]
            except Exception:
                pass
            return word

        return re.sub(r'\b\w+\b', lambda m: decode_word(m.group(0)), payload)
    except Exception as e:
        return ""

@app.route('/')
def home():
    return "Vidhide Direct Downloader Backend is Live!"

@app.route('/get-download-link', methods=['GET'])
def get_download_link():
    file_code = request.args.get('code')
    if not file_code:
        return jsonify({'success': False, 'message': 'File code is required'}), 400

    try:
        embed_url = f"https://vidhidepro.com/embed/{file_code}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://vidhidepro.com/'
        }

        response = requests.get(embed_url, headers=headers, timeout=10)
        html = response.text

        # 1. Unpacked Javascript se direct source link nikalna
        unpacked_js = unpack_packer(html)
        m3u8_match = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', unpacked_js)

        if not m3u8_match:
            # 2. Raw HTML me check karna
            m3u8_match = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)

        if m3u8_match:
            direct_m3u8_url = m3u8_match.group(1)
            return jsonify({
                'success': True,
                'download_url': direct_m3u8_url
            })
        else:
            # Fallback agar direct link scrape na ho paye
            return jsonify({
                'success': True,
                'download_url': f"https://vidhidepro.com/d/{file_code}"
            })

    except Exception as e:
        print("Extraction Error:", e)
        return jsonify({
            'success': True,
            'download_url': f"https://vidhidepro.com/d/{file_code}"
        })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
    
