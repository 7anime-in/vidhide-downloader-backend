from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import re

app = Flask(__name__)
CORS(app)

def unpack_packer(packed_js):
    try:
        pattern = r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)"
        match = re.search(pattern, packed_js, re.DOTALL)
        if not match: return ""
        payload, radix_str, count_str, symtab_str = match.groups()
        radix, symtab = int(radix_str), symtab_str.split('|')
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        def decode_word(word):
            try:
                val = 0
                for char in word: val = val * radix + alphabet.index(char)
                if val < len(symtab) and symtab[val]: return symtab[val]
            except: pass
            return word
        return re.sub(r'\b\w+\b', lambda m: decode_word(m.group(0)), payload)
    except: return ""

@app.route('/')
def home():
    return "0-Ads Vidhide Downloader Backend Active"

# 1. Direct M3U8 Stream Link Extractor
@app.route('/get-download-link', methods=['GET'])
def get_download_link():
    file_code = request.args.get('code')
    if not file_code:
        return jsonify({'success': False, 'message': 'Code required'}), 400

    try:
        embed_url = f"https://vidhidepro.com/embed/{file_code}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': 'https://vidhidepro.com/'
        }
        res = requests.get(embed_url, headers=headers, timeout=10)
        unpacked_js = unpack_packer(res.text)
        m3u8_match = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', unpacked_js) or re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', res.text)

        if m3u8_match:
            raw_m3u8 = m3u8_match.group(1)
            # Proxy URL return karenge taaki 403 Forbidden Bypass ho jaye
            proxy_url = f"{request.host_url}proxy-stream?url={requests.utils.quote(raw_m3u8)}"
            return jsonify({'success': True, 'download_url': proxy_url, 'is_direct': True})
        else:
            return jsonify({'success': False, 'message': 'Stream not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 2. 403 Forbidden Bypass Proxy Endpoint
@app.route('/proxy-stream')
def proxy_stream():
    target_url = request.args.get('url')
    if not target_url:
        return "URL missing", 400

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Referer': 'https://vidhidepro.com/'
    }
    
    req = requests.get(target_url, headers=headers, stream=True)
    
    # Modify M3U8 content to route segment files through our proxy as well
    if '.m3u8' in target_url:
        m3u8_content = req.text
        base_url = target_url.rsplit('/', 1)[0] + '/'
        
        def replace_link(match):
            link = match.group(0)
            if not link.startswith('http'):
                link = base_url + link
            return f"{request.host_url}proxy-stream?url={requests.utils.quote(link)}"
        
        # Replace relative links with proxied links
        modified_m3u8 = re.sub(r'(https?://[^\s\n]+|\b[^\s\n]+\.ts\b)', replace_link, m3u8_content)
        return Response(modified_m3u8, content_type='application/vnd.apple.mpegurl')

    return Response(req.iter_content(chunk_size=1024*1024), content_type=req.headers.get('content-type', 'video/mp2t'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
    
