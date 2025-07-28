from flask import Flask, request, jsonify, send_from_directory
import csv
import os
import time
from collections import defaultdict
from functools import wraps

app = Flask(__name__)

rate_limit_data = defaultdict(list)

RATE_LIMIT = 100  
RATE_LIMIT_WINDOW = 300  

def is_rate_limited(ip):
    now = time.time()
    requests = rate_limit_data[ip]
    rate_limit_data[ip] = [req for req in requests if now - req < RATE_LIMIT_WINDOW]
    if len(rate_limit_data[ip]) >= RATE_LIMIT:
        return True
    rate_limit_data[ip].append(now)
    return False

def escape_csv_formula(value):
    if value == "---":
        return value
    if isinstance(value, str) and value.startswith(('=', '+', '-', '@')):
        return f"'{value}"
    return value

def carregar_centrais():
    centrais = {}
    if os.path.exists('centrais.csv'):
        with open('centrais.csv', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None) 
            for row in reader:
                if len(row) >= 2:
                    numero_serie = row[0].strip()
                    nome = row[1].strip()
                    centrais[numero_serie] = nome
    return centrais

@app.route('/cadastrar_usuario', methods=['POST'])
def cadastrar_usuario():
    ip = request.remote_addr
    if is_rate_limited(ip):
        return jsonify({'sucesso': False, 'erro': 'Muitas requisições. Tente novamente mais tarde.'}), 429

    data = request.get_json()
    numero = str(data.get('numero'))
    nome = data.get('nome')
    numero_serie = str(data.get('numero_serie'))
    if not numero or not nome or not numero_serie:
        return jsonify({'sucesso': False, 'erro': 'Dados incompletos'}), 400

    if os.path.exists('usuarios.csv'):
        with open('usuarios.csv', 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if row and len(row) >= 3 and row[0] == numero and row[2] == numero_serie:
                    return jsonify({'sucesso': False, 'erro': 'Já existe este número com este número de série!'}), 400

    arquivo_existe = os.path.exists('usuarios.csv')
    escrever_cabecalho = not arquivo_existe or os.path.getsize('usuarios.csv') == 0

    centrais = carregar_centrais()
    nome_local = centrais.get(numero_serie, "Desconhecido")

    with open('usuarios.csv', 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if escrever_cabecalho:
            writer.writerow(['N° Zona/Usuário', 'Nome', 'Número de série', 'Localização'])
        writer.writerow([
            escape_csv_formula(numero),
            escape_csv_formula(nome),
            escape_csv_formula(numero_serie),
            escape_csv_formula(nome_local),
        ])

    usuarios = []
    with open('usuarios.csv', 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)
        for row in reader:
            if row:
                usuarios.append(row)
    
    usuarios.sort(key=lambda x: (int(x[0]), x[2]))

    with open('usuarios.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(usuarios)

    return jsonify({'sucesso': True})

@app.route('/apagar_usuario', methods=['POST'])
def apagar_usuario():
    ip = request.remote_addr
    if is_rate_limited(ip):
        return jsonify({'sucesso': False, 'erro': 'Muitas requisições. Tente novamente mais tarde.'}), 429

    data = request.get_json()
    numero = data.get('numero', '').strip()
    numero_serie = data.get('numero_serie', '').strip()
    if not numero or not numero_serie:
        return jsonify({'sucesso': False, 'erro': 'Dados incompletos'}), 400

    if not os.path.exists('usuarios.csv'):
        return jsonify({'sucesso': False, 'erro': 'Arquivo de usuários não encontrado.'}), 404
        
    usuarios = []
    removido = False
    with open('usuarios.csv', 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader, None)
        for row in reader:
            if row and len(row) >= 3 and row[0].strip() == numero and row[2].strip() == numero_serie:
                removido = True
            else:
                usuarios.append(row)

    if not removido:
        return jsonify({'sucesso': False, 'erro': 'Usuário não encontrado.'}), 404

    with open('usuarios.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if headers:
            writer.writerow(headers)
        writer.writerows(usuarios)

    return jsonify({'sucesso': True})


@app.route('/editar_usuario', methods=['POST'])
def editar_usuario():
    data = request.get_json()
    numero = data.get('numero', '').strip()
    numero_serie = data.get('numero_serie', '').strip()
    novo_nome = data.get('nome', '').strip()
    if not numero or not numero_serie or not novo_nome:
        return jsonify({'sucesso': False, 'erro': 'Dados incompletos'}), 400

    if not os.path.exists('usuarios.csv'):
        return jsonify({'sucesso': False, 'erro': 'Arquivo de usuários não encontrado.'}), 404

    centrais = carregar_centrais()
    usuarios = []
    editado = False
    with open('usuarios.csv', 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader, None)
        for row in reader:
            if row and len(row) >= 3 and row[0].strip() == numero and row[2].strip() == numero_serie:
                row[1] = novo_nome
                if len(row) < 4:
                    row.append("") 
                row[3] = centrais.get(numero_serie, "Desconhecido")
                editado = True
            usuarios.append(row)

    if not editado:
        return jsonify({'sucesso': False, 'erro': 'Usuário não encontrado.'}), 404

    with open('usuarios.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if headers:
            writer.writerow(headers)
        writer.writerows(usuarios)
        
    return jsonify({'sucesso': True})

@app.route('/usuarios.csv')
def serve_csv():
    ip = request.remote_addr
    if is_rate_limited(ip):
        return "Muitas requisições.", 429
    return send_from_directory('.', 'usuarios.csv')

GLOBAL_USERNAME = None
GLOBAL_PASSWORD = None

def requires_auth_if_external(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.remote_addr == '127.0.0.1':
            return f(*args, **kwargs)
        
        auth = request.authorization
        if not GLOBAL_USERNAME or not auth or auth.username != GLOBAL_USERNAME or auth.password != GLOBAL_PASSWORD:
            return 'Autenticação necessária', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'}
        return f(*args, **kwargs)
    return decorated_function

@app.route('/centrais.csv')
@requires_auth_if_external
def serve_centrais_csv():
    ip = request.remote_addr
    if is_rate_limited(ip):
        return "Muitas requisições.", 429
    return send_from_directory('.', 'centrais.csv')

@app.route('/meu_icone.ico')
def serve_icon():
    return send_from_directory('.', 'meu_icone.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/tabela_extraida.html')
@requires_auth_if_external
def serve_html():
    ip = request.remote_addr
    if is_rate_limited(ip):
        return "Muitas requisições.", 429
    
    if not os.path.exists('tabela_extraida.html'):
        return get_default_html()

    response = send_from_directory('.', 'tabela_extraida.html')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/set_credentials', methods=['POST'])
def set_credentials():
    if request.remote_addr != '127.0.0.1':
        return jsonify({'sucesso': False, 'erro': 'Acesso não autorizado'}), 403
    
    global GLOBAL_USERNAME, GLOBAL_PASSWORD
    data = request.get_json()
    GLOBAL_USERNAME = data.get('username')
    GLOBAL_PASSWORD = data.get('password')
    return jsonify({'sucesso': True})

@app.route('/adicionar_central', methods=['POST'])
@requires_auth_if_external
def adicionar_central():
    ip = request.remote_addr
    if is_rate_limited(ip):
        return jsonify({'sucesso': False, 'erro': 'Muitas requisições. Tente novamente mais tarde.'}), 429

    data = request.get_json()
    numero_serie = str(data.get('numero_serie', '')).strip()
    nome = str(data.get('nome', '')).strip()
    if not numero_serie or not nome:
        return jsonify({'sucesso': False, 'erro': 'Dados incompletos'}), 400

    linhas = []
    headers = ['numero_de_serie', 'nome']
    if os.path.exists('centrais.csv'):
        with open('centrais.csv', 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader, headers)
            for row in reader:
                if row and row[0].strip() == numero_serie:
                    return jsonify({'sucesso': False, 'erro': 'Já existe uma central com este número de série!'}), 400
                linhas.append(row)
    
    linhas.append([numero_serie, nome])
    linhas.sort(key=lambda x: x[0])

    with open('centrais.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(linhas)

    return jsonify({'sucesso': True})

@app.route('/editar_central', methods=['POST'])
@requires_auth_if_external
def editar_central():
    data = request.get_json()
    numero_serie_antigo = data.get('numero_serie_antigo', '').strip()
    numero_serie_novo = data.get('numero_serie_novo', '').strip()
    nome_novo = data.get('nome_novo', '').strip()
    if not numero_serie_antigo or not numero_serie_novo or not nome_novo:
        return jsonify({'sucesso': False, 'erro': 'Dados incompletos'}), 400

    if not os.path.exists('centrais.csv'):
        return jsonify({'sucesso': False, 'erro': 'Arquivo de centrais não encontrado.'}), 404

    linhas = []
    editado = False
    with open('centrais.csv', 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader, None)
        for row in reader:
            if row and row[0].strip() == numero_serie_antigo:
                linhas.append([numero_serie_novo, nome_novo])
                editado = True
            else:
                linhas.append(row)

    if not editado:
        return jsonify({'sucesso': False, 'erro': 'Central não encontrada.'}), 404

    with open('centrais.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if headers:
            writer.writerow(headers)
        writer.writerows(linhas)

    if os.path.exists('usuarios.csv'):
        usuarios = []
        with open('usuarios.csv', 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers_usuarios = next(reader, None)
            for row in reader:
                if len(row) >= 4 and row[2].strip() == numero_serie_antigo:
                    row[2] = numero_serie_novo
                    row[3] = nome_novo
                usuarios.append(row)
        with open('usuarios.csv', 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            if headers_usuarios:
                writer.writerow(headers_usuarios)
            writer.writerows(usuarios)
    
    return jsonify({'sucesso': True})

@app.route('/excluir_central', methods=['POST'])
@requires_auth_if_external
def excluir_central():
    ip = request.remote_addr
    if is_rate_limited(ip):
        return jsonify({'sucesso': False, 'erro': 'Muitas requisições. Tente novamente mais tarde.'}), 429

    data = request.get_json()
    numero_serie = str(data.get('numero_serie', '')).strip()
    if not numero_serie:
        return jsonify({'sucesso': False, 'erro': 'Número de série não informado.'}), 400

    if not os.path.exists('centrais.csv'):
        return jsonify({'sucesso': False, 'erro': 'Arquivo de centrais não encontrado.'}), 404

    linhas = []
    removido = False
    with open('centrais.csv', 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader, None)
        for row in reader:
            if row and row[0].strip() == numero_serie:
                removido = True
            else:
                linhas.append(row)

    if not removido:
        return jsonify({'sucesso': False, 'erro': 'Central não encontrada.'}), 404

    with open('centrais.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if headers:
            writer.writerow(headers)
        writer.writerows(linhas)

    if os.path.exists('usuarios.csv'):
        usuarios = []
        with open('usuarios.csv', 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers_usuarios = next(reader, None)
            for row in reader:
                if len(row) >= 3 and row[2].strip() == numero_serie:
                    continue 
                usuarios.append(row)
        with open('usuarios.csv', 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            if headers_usuarios:
                writer.writerow(headers_usuarios)
            writer.writerows(usuarios)

    return jsonify({'sucesso': True})


def validate_html_content(html_content):
    if not html_content or len(html_content.strip()) < 100:
        return False
    required_elements = ['<!DOCTYPE html>', '<html', '<head', '<body']
    return all(element in html_content for element in required_elements)

def get_default_html():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset='utf-8'/>
        <title>Eventos JFL</title>
        <style>
            body {
                background: #111; color: #eee; font-family: 'Segoe UI', Arial, sans-serif;
                margin: 0; padding: 20px; display: flex; justify-content: center;
                align-items: center; min-height: 100vh; text-align: center;
            }
            .message { background: #222; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.3); }
            .loading {
                display: inline-block; width: 20px; height: 20px;
                border: 3px solid #ffffff3d; border-radius: 50%;
                border-top-color: #fff; animation: spin 1s ease-in-out infinite;
                margin-right: 10px; vertical-align: middle;
            }
            @keyframes spin { to { transform: rotate(360deg); } }
        </style>
        <script>
            setTimeout(() => window.location.reload(), 5000);
        </script>
    </head>
    <body>
        <div class="message">
            <div class="loading"></div>
            Aguardando dados... A página será atualizada automaticamente.
        </div>
    </body>
    </html>
    """

@app.route('/')
@requires_auth_if_external
def index():
    try:
        if os.path.exists('tabela_extraida.html'):
            with open('tabela_extraida.html', 'r', encoding='utf-8') as f:
                content = f.read()
            
            if validate_html_content(content):
                return content
        
        return get_default_html()

    except Exception as e:
        print(f"Erro ao servir HTML da rota principal: {str(e)}")
        return get_default_html()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8090, debug=False)
