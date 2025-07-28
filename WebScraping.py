import os
import sys
import webbrowser
import csv
import time
import tkinter as tk
from tkinter import simpledialog, messagebox
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import pandas as pd
import getpass
import winsound
from html import escape
import requests

USUARIOS_CSV = 'usuarios.csv'
CENTRAIS_CSV = 'centrais.csv'

if not os.path.exists(USUARIOS_CSV):
    with open(USUARIOS_CSV, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['N° Zona/Usuário', 'Nome', 'Número de série', 'Localização'])

def carregar_centrais():
    """Carrega os dados de centrais a partir do arquivo CSV."""
    centrais = []
    if os.path.exists(CENTRAIS_CSV):
        with open(CENTRAIS_CSV, encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None) 
            for row in reader:
                if len(row) >= 2:
                    numero_serie = row[0].strip()
                    nome = row[1].strip()
                    centrais.append((numero_serie, nome))
            print(f"[LOG] Centrais carregadas: {centrais}")
    else:
        print(f"[ERRO] Arquivo {CENTRAIS_CSV} não encontrado.")
    return centrais

def pedir_parametros():
    root = tk.Tk()
    root.withdraw()
    usuario = simpledialog.askstring("Login", "Usuário:")
    senha = simpledialog.askstring("Login", "Senha:", show='*')
    porta = simpledialog.askstring("Porta", "Porta do site origem da tabela:", initialvalue="8081")
    if not usuario or not senha or not porta:
        messagebox.showerror("Erro", "Todos os campos são obrigatórios!")
        sys.exit(1)
    return usuario, senha, porta

usuario, senha, porta = pedir_parametros()

chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
driver = webdriver.Chrome(options=chrome_options)



try:
    response = requests.post('http://localhost:8090/set_credentials', json={
        'username': usuario,
        'password': senha
    })
    if response.status_code != 200:
        print("Erro ao enviar credenciais para o backend.")
        sys.exit(1)
except Exception as e:
    print(f"Erro ao conectar com o backend: {e}")
    sys.exit(1)

time.sleep(2)

try:
    url_base = f'http://localhost:{porta}'
    driver.get(f'{url_base}/login')
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.NAME, 'username'))
    )
    driver.find_element(By.NAME, 'username').send_keys(usuario)
    driver.find_element(By.NAME, 'password').send_keys(senha)
    driver.find_element(By.NAME, 'password').send_keys(Keys.RETURN)
    try:
        WebDriverWait(driver, 20).until(
            EC.url_contains('/home')
        )
    except Exception as e:
        print("Erro ao carregar a página inicial após login:", e)
        driver.quit()
        sys.exit(1)
    driver.get(f'{url_base}/home')
    try:
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "close"))
        ).click()
    except Exception:
        pass
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    if len(iframes) > 0:
        driver.switch_to.frame(iframes[0])
    
    valor_primeira_celula = None
    primeira_execucao = True

    while True:
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, 'table'))
            )
        except Exception as e:
            print("Erro ao carregar a tabela na página:", e)
            driver.quit()
            sys.exit(1)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//table//tbody/tr/td"))
        )
        tentativas = 5
        table = None
        tbody = None
        for tentativa in range(tentativas):
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            found_table = soup.find('table', {'id': 'events_table'}) or soup.find('table')
            
            if found_table:
                found_tbody = found_table.find('tbody')
                if found_tbody and found_tbody.find('tr'):
                    table = found_table
                    tbody = found_tbody
                    break
            
            time.sleep(2)

       
        if table and tbody:
            headers = [th.get_text(strip=True) for th in table.find_all('th')]
            trs = tbody.find_all('tr')
            rows = []
            for tr in trs:
                cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if cells:
                    rows.append(cells)
            
            if not rows:
                print("Tabela encontrada, mas sem linhas de dados. Tentando novamente...")
                time.sleep(15)
                continue

            df = pd.DataFrame(rows, columns=headers)
            print(df)
            highlight_row = False
            dados_nova_linha = None
            if rows:
                try:
                    idx_datahora = headers.index("Data e hora")
                    valor_atual = rows[0][idx_datahora]
                    print(f"Primeira 'Data e hora' atual: {valor_atual}")
                    print(f"Primeira 'Data e hora' anterior: {valor_primeira_celula}")
                    
                    if valor_primeira_celula is None or valor_atual != valor_primeira_celula:
                        valor_primeira_celula = valor_atual
                        
                        if not primeira_execucao:
                            try:
                                idx_evento = headers.index("Evento")
                                evento_numero = rows[0][idx_evento].strip()
                            except (ValueError, IndexError):
                                evento_numero = None
                            
                            eventos_ignorar = {"3361", "1361", "3250", "1250","3253", "3252", "1254", "3254", "1661"}
                            if evento_numero not in eventos_ignorar:
                                print("Alteração detectada! Emitindo bip e preparando pop-up!")
                                for _ in range(5):
                                    winsound.Beep(1000, 800)
                                time.sleep(2)
                                webbrowser.open('http://localhost:8090/')
                                highlight_row = True
                                dados_nova_linha = rows[0]
                            else:
                                print(f"Evento {evento_numero} ignorado para bip/pop-up.")
                except ValueError:
                    print("Coluna 'Data e hora' não encontrada!")

            popup_script = ""
            if highlight_row and dados_nova_linha:
                usuarios_map = {}
                with open(USUARIOS_CSV, encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        numero_csv = row.get("N° Zona/Usuário") or row.get("Nº Zona/Usuário")
                        nome_csv = row.get("Nome")
                        numero_serie_csv = row.get("Número de série")
                        if numero_csv is not None and nome_csv is not None and numero_serie_csv is not None:
                            usuarios_map[(numero_csv.strip(), numero_serie_csv.strip().zfill(2))] = nome_csv.strip()

                try:
                    idx_nome = headers.index("Nome Zona/Usuário")
                    idx_numero = headers.index("Nº Zona/Usuário")
                    idx_numero_serie = headers.index("Número de série")
                except ValueError:
                    idx_nome = idx_numero = idx_numero_serie = -1

                dados_nova_linha_corrigida = list(dados_nova_linha)
                if idx_nome != -1 and idx_numero != -1 and idx_numero_serie != -1:
                    numero = dados_nova_linha[idx_numero].strip()
                    numero_serie = dados_nova_linha[idx_numero_serie].strip().zfill(2)
                    nome_csv = usuarios_map.get((numero, numero_serie))
                    if nome_csv:
                        dados_nova_linha_corrigida[idx_nome] = nome_csv

                dados_str = "\\n".join(f"{escape(h)}: {escape(v)}" for h, v in zip(headers, dados_nova_linha_corrigida))
                popup_script = f'''
<script>
window.addEventListener('load', function() {{
    mostrarNovoDadoPopup("{dados_str.replace(chr(10), '\\n')}");
}});
</script>
'''
            else:
                popup_script = ""

            if not rows:
                print("Nenhum dado encontrado na tabela. Exibindo mensagem padrão no HTML.")
                html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset='utf-8'/>
        <title>Eventos JFL</title>
        <style>
            body {{
                background: #111;
                color: #eee;
                font-family: 'Segoe UI', Arial, sans-serif;
                margin: 0;
                padding: 0;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
            }}
            .mensagem {{
                text-align: center;
                font-size: 1.5em;
                color: #fff;
            }}
        </style>
    </head>
    <body>
        <div class='mensagem'>
            Nenhum dado disponível no momento. Aguarde a próxima atualização.
        </div>
    </body>
    </html>
    """
                with open('tabela_extraida.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                time.sleep(15)
                continue

            usuarios_map = {}
            if os.path.exists(USUARIOS_CSV):
                with open(USUARIOS_CSV, 'r', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        numero_csv = row.get("N° Zona/Usuário") or row.get("Nº Zona/Usuário")
                        nome_csv = row.get("Nome")
                        numero_serie_csv = row.get("Número de série")
                        if numero_csv and nome_csv and numero_serie_csv:
                            usuarios_map[(numero_csv.strip(), numero_serie_csv.strip())] = nome_csv.strip()
            
    
            if "Nome Zona/Usuário" in df.columns and "Nº Zona/Usuário" in df.columns and "Número de série" in df.columns:
                for index, row in df.iterrows():
                    if row["Nome Zona/Usuário"] == "---":
                        numero_usuario = row["Nº Zona/Usuário"].strip()
                        numero_serie = row["Número de série"].strip()
                        nome_substituto = usuarios_map.get((numero_usuario, numero_serie))
                        if nome_substituto:
                            df.at[index, "Nome Zona/Usuário"] = nome_substituto

            colunas_remover = ["IMEI", "Nome da partição/Pgm", "MAC"]
            for col in colunas_remover:
                if col in df.columns:
                    df = df.drop(columns=[col])

            html_table = df.to_html(index=False, classes=['table', 'table-striped'])
            soup_table = BeautifulSoup(html_table, "html.parser")
            
            timestamp_div = soup_table.new_tag('div', style='display:none;')
            timestamp_div['class'] = 'timestamp'
            timestamp_div.string = str(time.time())
            soup_table.insert(0, timestamp_div)
            
            html = str(soup_table)

            if not html.strip():
                print("HTML gerado está vazio. Mantendo o conteúdo anterior do arquivo HTML.")
                time.sleep(5)
                continue

            centrais = carregar_centrais()

            if centrais:
                select_options = "\n".join([f'<option value="{numero_serie}">{nome}</option>' for numero_serie, nome in centrais])
            else:
                select_options = '<option value="">Nenhuma central disponível</option>'
                

            html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"/>
<meta http-equiv="Pragma" content="no-cache"/>
<meta http-equiv="Expires" content="0"/>
<link rel="icon" type="image/x-icon" href="meu_icone.ico"/>
<title>Eventos JFL</title>
<style>
    body {{
        background: #111;
        color: #eee;
        font-family: 'Segoe UI', Arial, sans-serif;
        margin: 0;
        padding: 0;
    }}
    .container {{
        width: 95%;
        max-width: 1400px;
        margin: 30px auto;
        padding: 24px 32px;
        background: #181818;
        border-radius: 16px;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.5);
    }}
    h2 {{
        color: #fff;
        text-align: center;
        margin-bottom: 24px;
        letter-spacing: 1px;
    }}
    .top-bar {{
        display: flex;
        justify-content: flex-end;
        align-items: center;
        margin-bottom: 18px;
        gap: 10px;
    }}
    .btn-cadastrar {{
        background: linear-gradient(90deg, #444 60%, #222 100%);
        color: #fff;
        border: none;
        padding: 10px 22px;
        border-radius: 8px;
        font-size: 1em;
        font-weight: 600;
        cursor: pointer;
        box-shadow: 0 2px 8px #0004;
        transition: background 0.2s, transform 0.2s;
        margin-bottom: 0;
    }}
    .btn-cadastrar:hover {{
        background: linear-gradient(90deg, #666 60%, #333 100%);
        transform: scale(1.04);
    }}
    .popup-bg {{
        display: none;
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: #000a;
        z-index: 1000;
        justify-content: center;
        align-items: center;
        animation: fadeIn 0.3s ease;
    }}
    @keyframes fadeIn {{
        from {{
            opacity: 0;
        }}
        to {{
            opacity: 1;
        }}
    }}
    .popup {{
        background: #222;
        border-radius: 12px;
        box-shadow: 0 4px 24px #000c;
        padding: 32px 28px 24px 28px;
        min-width: 320px;
        width: 480px;
        max-width: 95%;
        color: #eee;
        display: flex;
        flex-direction: column;
        gap: 16px;
        position: relative;
        animation: popupIn 0.2s;
    }}
    @keyframes popupIn {{
        from {{ transform: scale(0.9); opacity: 0; }}
        to {{ transform: scale(1); opacity: 1; }}
    }}
    #popup-list-bg .popup,
    #popup-edit-centrais-bg .popup {{
        width: 90vw;
        max-width: 800px;
    }}

    #novo-dado-popup-bg .popup {{
        width: 90vw;
        max-width: 650px;
    }}

    .popup label {{
        font-size: 1em;
        margin-bottom: 4px;
    }}
    .popup input {{
        padding: 8px 10px;
        border-radius: 6px;
        border: 1px solid #444;
        background: #181818;
        color: #eee;
        font-size: 1em;
        margin-bottom: 10px;
        width: 100%;
        box-sizing: border-box;
    }}
    .popup select {{
        padding: 8px 10px;
        border-radius: 6px;
        border: 1px solid #444;
        background: #181818;
        color: #eee;
        font-size: 1em;
        margin-bottom: 10px;
        width: 100%;
        box-sizing: border-box;
    }}
    .popup .popup-actions {{
        display: flex;
        justify-content: flex-end;
        gap: 12px;
        margin-top: 8px;
    }}
    .popup button {{
        padding: 8px 18px;
        border-radius: 6px;
        border: none;
        font-size: 1em;
        font-weight: 600;
        cursor: pointer;
        transition: background 0.2s;
    }}
    .popup .btn-confirm {{
        background: #2ecc40;
        color: #fff;
    }}
    .popup .btn-confirm:hover {{
        background: #27ae38;
    }}
    .popup .btn-cancel {{
        background: #e74c3c;
        color: #fff;
    }}
    .popup .btn-cancel:hover {{
        background: #c0392b;
    }}
    .popup .popup-error {{
        color: #ff5;
        font-size: 0.98em;
        margin-bottom: 0;
        min-height: 18px;
    }}
    table.dataframe {{
        border-collapse: collapse;
        width: 100%;
        background: #222;
        color: #eee;
        font-size: 1.08em;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 2px 12px #0006;
    }}
    table.dataframe th, table.dataframe td {{
        border: 1px solid #444;
        padding: 10px 12px;
        text-align: left;
        transition: background 0.2s;
    }}
    table.dataframe th {{
        background: linear-gradient(90deg, #333 70%, #222 100%);
        font-weight: 600;
        letter-spacing: 0.5px;
        text-shadow: 0 1px 2px #000a;
    }}
    table.dataframe tr:nth-child(even) {{
        background: #222;
    }}
    table.dataframe tr:nth-child(odd) {{
        background: #444;
    }}
    table.dataframe tr:hover td {{
        background: #505050;
        color: #fff;
        box-shadow: 0 2px 8px #0006;
    }}
    .table-responsive {{
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        border-radius: 12px;
    }}
    table.dataframe td {{
        vertical-align: middle;
    }}

    .usuarios-table {{
        border-collapse: collapse;
        width: 100%;
        min-width: 350px;
        background: #222;
        color: #eee;
        font-size: 1em;
        border-radius: 8px;
        overflow: hidden;
        margin-bottom: 10px;
        table-layout: auto;
    }}
    .usuarios-table th, .usuarios-table td {{
        border: 1px solid #444;
        padding: 10px 12px;
        text-align: center; 
        vertical-align: middle;
    }}
    .usuarios-table th {{
        background: linear-gradient(90deg, #333 70%, #222 100%);
        font-weight: 600;
        letter-spacing: 0.5px;
        text-shadow: 0 1px 2px #000a;
    }}
    .usuarios-table tr:nth-child(even) {{
        background: #222;
    }}
    .usuarios-table tr:nth-child(odd) {{
        background: #333;
    }}
    .usuarios-table tr:hover td {{
        background: #505050;
        color: #fff;
        box-shadow: 0 2px 8px #0006;
    }}
    .action-buttons {{
        display: flex;
        gap: 1px;
        justify-content: center;
    }}
    .action-buttons button {{
        flex: 1;
        min-width: 80px;
    }}
    #usuarios-tabela {{
        max-height: 400px;
        overflow-y: auto;
        overflow-x: auto;
        width: 100%;
        display: block;
    }}

    .highlight-row {{
        animation: highlight 1.5s ease-in-out;
    }}
    @keyframes highlight {{
        0% {{
            background-color: #ff0;
        }}
        100% {{
            background-color: inherit;
        }}
    }}


    @media (max-width: 768px) {{
        .container {{
            width: 100%;
            margin: 0;
            padding: 16px;
            border-radius: 0;
        }}
        .top-bar {{
            flex-direction: column;
            align-items: stretch;
        }}
        .btn-cadastrar {{
            width: 100%;
            text-align: center;
        }}
        h2 {{
            font-size: 1.5em;
        }}
    }}
</style>
<script>
function reloadWithTransition() {{
    document.body.classList.add('loading');
    setTimeout(() => {{
        window.location.reload();
    }}, 300);
}}


setInterval(async () => {{
    if (document.querySelector('.popup-bg[style*="display: flex"]')) {{
        console.log("Pop-up aberta, atualização pausada.");
        return;
    }}
    try {{
        const response = await fetch(window.location.href);
        const newHtml = await response.text();
        const parser = new DOMParser();
        const newDoc = parser.parseFromString(newHtml, 'text/html');
        
        const currentTimestamp = document.querySelector('.timestamp')?.textContent;
        const newTimestamp = newDoc.querySelector('.timestamp')?.textContent;
        
        if (currentTimestamp !== newTimestamp) {{
            reloadWithTransition();
        }}
    }} catch (error) {{
        console.error('Erro ao verificar atualizações:', error);
    }}
}}, 15000);




function excluirCentral(numero_serie, btn) {{
    if (!confirm('Tem certeza que deseja excluir esta central?')) return;
    fetch('excluir_central', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ numero_serie: numero_serie }})
    }}).then(resp => resp.json()).then(data => {{
        if (data.sucesso) {{
            if (btn) {{
                let tr = btn.closest('tr');
                if (tr) tr.remove();
            }}
            carregarEditCentrais();
        }} else {{
            alert(data.erro || 'Erro ao excluir central.');
        }}
    }}).catch(() => {{
        alert('Erro de comunicação com o backend.');
    }});
}}



window.onload = function() {{
    fetch('usuarios.csv').then(r => r.text()).then(csv => {{
        localStorage.setItem('usuarios_csv', csv);
    }});
}};

function openPopup() {{
    document.getElementById('popup-bg').style.display = 'flex';
    document.getElementById('popup-error').innerText = '';
    document.getElementById('numero').value = '';
    document.getElementById('nome').value = '';
    document.getElementById('numero_serie').value = '';
}}

function closePopup() {{
    document.getElementById('popup-bg').style.display = 'none';
}}

function getUsuariosExistentes() {{
    let pares = [];
    try {{
        let csv = localStorage.getItem('usuarios_csv');
        if (csv) {{
            let linhas = csv.split('\\n');
            for (let i = 1; i < linhas.length; i++) {{
                let partes = linhas[i].split(',');
                if (partes[0] && partes[2]) pares.push(partes[0].trim() + '|' + partes[2].trim());
            }}
        }}
    }} catch(e){{}}
    return pares;
}}
function validarCadastro() {{
    let numero = document.getElementById('numero').value.trim();
    let nome = document.getElementById('nome').value.trim();
    let numero_serie = document.getElementById('numero_serie').value.trim();
    let erro = '';
    if (!/^\\d{{3}}$/.test(numero)) {{
        erro = 'O número deve ter exatamente 3 dígitos.';
    }} else if (!nome) {{
        erro = 'Informe o nome do usuário.';
    }} else if (!numero_serie) {{
        erro = 'Informe o número de série.';
    }} else {{
        let pares = getUsuariosExistentes();
        if (pares.includes(numero + '|' + numero_serie)) {{
            erro = 'Já existe este número com este número de série!';
        }}
    }}
    document.getElementById('popup-error').innerText = erro;
    return !erro;
}}
function confirmarCadastro() {{
    if (!validarCadastro()) return;
    let numero = document.getElementById('numero').value.trim();
    let nome = document.getElementById('nome').value.trim();
    let numero_serie = document.getElementById('numero_serie').value.trim();
    fetch('cadastrar_usuario', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ numero: numero, nome: nome, numero_serie: numero_serie }})
    }}).then(resp => resp.json()).then(data => {{
        if (data.sucesso) {{
            closePopup();
            alert('Usuário cadastrado com sucesso! Atualize a página para ver na tabela.');
        }} else {{
            document.getElementById('popup-error').innerText = data.erro || 'Erro ao cadastrar.';
        }}
    }}).catch(() => {{
        document.getElementById('popup-error').innerText = 'Erro de comunicação com o backend.';
    }});
}}

function carregarUsuariosTabela() {{
    fetch('usuarios.csv').then(r => r.text()).then(csv => {{
        let linhas = csv.trim().split('\\n');
        if (linhas.length < 2) {{
            document.getElementById('usuarios-tabela').innerHTML = '<em>Nenhum usuário cadastrado.</em>';
            return;
        }}
        let html = '<table class="usuarios-table"><thead><tr>';
        let headers = linhas[0].split(',');
        for (let h of headers) html += `<th>${{h}}</th>`;
        html += '<th>Ações</th></tr></thead><tbody>';
        for (let i = 1; i < linhas.length; i++) {{
            let cols = linhas[i].split(',');
            let numero = cols[0] ? cols[0] : '';
            let nome = cols[1] ? cols[1] : '';
            let numero_serie = cols[2] ? cols[2] : '';
            html += '<tr>';
            for (let c of cols) html += `<td>${{c}}</td>`;
            html += `<td>
                <div class="action-buttons">
                    <button class="btn-cancel apagar-btn" data-numero="${{numero}}" data-numero_serie="${{numero_serie}}">Apagar</button>
                    <button class="btn-confirm editar-btn" data-numero="${{numero}}" data-numero_serie="${{numero_serie}}" data-nome="${{nome}}">Editar</button>
                </div>
            </td>`;
            html += '</tr>';
        }}
        html += '</tbody></table>';
        document.getElementById('usuarios-tabela').innerHTML = html;
    }}).catch(() => {{
        document.getElementById('usuarios-tabela').innerHTML = '<em>Erro ao carregar usuários.</em>';
    }});
}}

document.addEventListener('DOMContentLoaded', function() {{
    let tabela = document.getElementById('usuarios-tabela');
    if (tabela) {{
        tabela.onclick = function(e) {{
            if (e.target && e.target.classList.contains('apagar-btn')) {{
                let numero = e.target.getAttribute('data-numero');
                let numero_serie = e.target.getAttribute('data-numero_serie');
                apagarUsuario(numero, numero_serie, e.target);
            }}
            if (e.target && e.target.classList.contains('editar-btn')) {{
                let numero = e.target.getAttribute('data-numero');
                let numero_serie = e.target.getAttribute('data-numero_serie');
                let nomeAtual = e.target.getAttribute('data-nome');
                editarUsuario(numero, numero_serie, nomeAtual, e.target);
            }}
            if (e.target && e.target.classList.contains('excluir-central-btn')) {{
                let numero_serie = e.target.getAttribute('data-numero_serie');
                excluirCentral(numero_serie, e.target);
            }}
        }};
    }}
    let fecharBtn = document.querySelector('#popup-list-bg .btn-cancel');
    if (fecharBtn) {{
        fecharBtn.onclick = function() {{
            location.reload();
        }};
    }}
}});

function editarUsuario(numero, numero_serie, nomeAtual, btn) {{
    let novoNome = prompt("Editar nome do usuário:", nomeAtual);
    if (novoNome === null) return;
    novoNome = novoNome.trim();
    if (!novoNome) {{
        alert("O nome não pode ser vazio.");
        return;
    }}
    fetch('editar_usuario', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ numero: numero, numero_serie: numero_serie, nome: novoNome }})
    }}).then(resp => resp.json()).then(data => {{
        if (data.sucesso) {{
            let tr = btn.closest('tr');
            if (tr) {{
                let tds = tr.querySelectorAll('td');
                if (tds.length >= 2) tds[1].innerText = novoNome;
                btn.setAttribute('data-nome', novoNome);
            }}
        }} else {{
            alert(data.erro || 'Erro ao editar usuário.');
        }}
    }}).catch(() => {{
        alert('Erro de comunicação com o backend.');
    }});
}}

function openListPopup() {{
    document.getElementById('popup-list-bg').style.display = 'flex';
    carregarUsuariosTabela();
    setTimeout(() => {{
        let tabela = document.getElementById('usuarios-tabela');
        if (tabela) {{
            tabela.onclick = function(e) {{
                if (e.target && e.target.classList.contains('apagar-btn')) {{
                    let numero = e.target.getAttribute('data-numero');
                    let numero_serie = e.target.getAttribute('data-numero_serie');
                    apagarUsuario(numero, numero_serie, e.target);
                }}
                if (e.target && e.target.classList.contains('editar-btn')) {{
                    let numero = e.target.getAttribute('data-numero');
                    let numero_serie = e.target.getAttribute('data-numero_serie');
                    let nomeAtual = e.target.getAttribute('data-nome');
                    editarUsuario(numero, numero_serie, nomeAtual, e.target);
                }}
            }};
        }}
    }}, 100);
}}

function apagarUsuario(numero, numero_serie, btn) {{
    if (!confirm('Tem certeza que deseja apagar este usuário?')) return;
    fetch('apagar_usuario', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ numero: numero, numero_serie: numero_serie }})
    }}).then(resp => resp.json()).then(data => {{
        if (data.sucesso) {{
            let tr = btn.closest('tr');
            if (tr) tr.remove();
        }} else {{
            alert(data.erro || 'Erro ao apagar usuário.');
        }}
    }}).catch(() => {{
        alert('Erro de comunicação com o backend.');
    }});
}}


function mostrarNovoDadoPopup(dados) {{
    const popupBg = document.getElementById('novo-dado-popup-bg');
    const popupDados = document.getElementById('novo-dado-popup-dados');
    
    if (popupBg && popupDados) {{
        popupBg.style.display = 'flex';
        popupDados.innerText = dados;
    }}
}}
function fecharNovoDadoPopup() {{
    document.getElementById('novo-dado-popup-bg').style.display = 'none';
}}

document.addEventListener('DOMContentLoaded', function() {{
    document.body.style.opacity = 0;
    document.body.style.transition = 'opacity 0.5s ease';
    setTimeout(() => {{
        document.body.style.opacity = 1;
    }}, 100);
}});

function destacarNovaLinha(rowElement) {{
    rowElement.classList.add('highlight-row');
    setTimeout(() => {{
        rowElement.classList.remove('highlight-row');
    }}, 1500);
}}


function openEditCentraisPopup() {{
    document.getElementById('popup-edit-centrais-bg').style.display = 'flex';
    carregarEditCentrais();
}}
function closeEditCentraisPopup() {{
    document.getElementById('popup-edit-centrais-bg').style.display = 'none';
}}
function carregarEditCentrais() {{
    fetch('centrais.csv').then(r => r.text()).then(csv => {{
        let linhas = csv.trim().split('\\n');
        if (linhas.length < 2) {{
            document.getElementById('edit-centrais-content').innerHTML = '<em>Nenhuma central cadastrada.</em>';
            return;
        }}
        let html = '<table class="usuarios-table"><thead><tr>';
        let headers = linhas[0].split(',');
        for (let h of headers) html += `<th>${{h}}</th>`;
        html += '<th>Ações</th></tr></thead><tbody>';
        for (let i = 1; i < linhas.length; i++) {{
            let cols = linhas[i].split(',');
            let numero_serie = cols[0] ? cols[0] : '';
            let nome = cols[1] ? cols[1] : '';
            html += '<tr>';
            for (let c of cols) html += `<td>${{c}}</td>`;
            html += `<td>
                <div class="action-buttons">
                    <button class="btn-confirm editar-central-btn" data-numero_serie="${{numero_serie}}" data-nome="${{nome}}">Editar</button>
                    <button class="btn-cancel excluir-central-btn" data-numero_serie="${{numero_serie}}">Excluir</button>
                </div>
            </td>`;
            html += '</tr>';
        }}
        html += '</tbody></table>';
        document.getElementById('edit-centrais-content').innerHTML = html;
        let tabela = document.getElementById('edit-centrais-content');
        if (tabela) {{
            tabela.onclick = function(e) {{
                if (e.target && e.target.classList.contains('editar-central-btn')) {{
                    let numero_serie = e.target.getAttribute('data-numero_serie');
                    let nome = e.target.getAttribute('data-nome');
                    abrirEditarCentralPopup(numero_serie, nome);
                }}
                if (e.target && e.target.classList.contains('excluir-central-btn')) {{
                    let numero_serie = e.target.getAttribute('data-numero_serie');
                    excluirCentral(numero_serie, e.target);
                }}
            }};
        }}
    }}).catch(() => {{
        document.getElementById('edit-centrais-content').innerHTML = '<em>Erro ao carregar centrais.</em>';
    }});
}}

document.getElementById('popup-edit-centrais-bg').addEventListener('open', function() {{
    carregarEditCentrais();
}});



var centralEditando = null;

function abrirEditarCentralPopup(numero_serie, nome) {{
    centralEditando = numero_serie;
    document.getElementById('editar-numero-serie').value = numero_serie;
    document.getElementById('editar-nome-central').value = nome;
    document.getElementById('popup-editar-central-erro').innerText = '';
    document.getElementById('popup-editar-central-bg').style.display = 'flex';
}}
function fecharEditarCentralPopup() {{
    document.getElementById('popup-editar-central-bg').style.display = 'none';
}}
function confirmarEditarCentral() {{
    var numero_serie_novo = document.getElementById('editar-numero-serie').value.trim();
    var nome_novo = document.getElementById('editar-nome-central').value.trim();
    if (!numero_serie_novo || !nome_novo) {{
        document.getElementById('popup-editar-central-erro').innerText = 'Preencha todos os campos.';
        return;
    }}
    fetch('editar_central', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
            numero_serie_antigo: centralEditando,
            numero_serie_novo: numero_serie_novo,
            nome_novo: nome_novo
        }})
    }}).then(resp => resp.json()).then(data => {{
        if (data.sucesso) {{
            fecharEditarCentralPopup();
            carregarEditCentrais();
        }} else {{
            document.getElementById('popup-editar-central-erro').innerText = data.erro || 'Erro ao editar central.';
        }}
    }}).catch(() => {{
        document.getElementById('popup-editar-central-erro').innerText = 'Erro de comunicação com o backend.';
    }});
}}


function abrirNovaCentralPopup() {{
    document.getElementById('popup-nova-central-bg').style.display = 'flex';
    document.getElementById('popup-nova-central-erro').innerText = '';
    document.getElementById('nova-central-numero-serie').value = '';
    document.getElementById('nova-central-nome').value = '';
    popupNovaCentralAberta = true;
}}
function fecharNovaCentralPopup() {{
    document.getElementById('popup-nova-central-bg').style.display = 'none';
    popupNovaCentralAberta = false;
}}
function confirmarNovaCentral() {{
    var numero_serie = document.getElementById('nova-central-numero-serie').value.trim();
    var nome = document.getElementById('nova-central-nome').value.trim();
    if (!numero_serie || !nome) {{
        document.getElementById('popup-nova-central-erro').innerText = 'Preencha todos os campos.';
        return;
    }}
    if (!/^\\d+$/.test(numero_serie)) {{
        document.getElementById('popup-nova-central-erro').innerText = 'O número de série deve conter apenas números.';
        return;
    }}
    fetch('adicionar_central', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ numero_serie: numero_serie, nome: nome }})
    }}).then(resp => resp.json()).then(data => {{
        if (data.sucesso) {{
            fecharNovaCentralPopup();
            carregarEditCentrais();
        }} else {{
            document.getElementById('popup-nova-central-erro').innerText = data.erro || 'Erro ao adicionar central.';
        }}
    }}).catch(() => {{
        document.getElementById('popup-nova-central-erro').innerText = 'Erro de comunicação com o backend.';
    }});
}}

</script>
</head>
<body>
<div class="container">
    <div class="top-bar" style="justify-content: space-between;">
        <button class="btn-cadastrar" onclick="openPopup()">Cadastrar Usuário</button>
        <button class="btn-cadastrar" style="margin-left:10px" onclick="openListPopup()">Listar Usuários</button>
        <button class="btn-cadastrar" style="margin-left:10px" onclick="openEditCentraisPopup()">Editar Centrais</button>
    </div>
    <h2>Eventos JFL</h2>
    <div class="popup-bg" id="popup-bg">
        <div class="popup">
            <label for="numero">Número do usuário (3 dígitos):</label>
            <input type="text" id="numero" maxlength="3" pattern="\\d{3}" autocomplete="off" inputmode="numeric" oninput="this.value=this.value.replace(/[^0-9]/g,'')" />
            <label for="nome">Nome da loja:</label>
            <input type="text" id="nome" maxlength="50" autocomplete="off"/>
            <label for="numero_serie">Localização da Central:</label>
            <select id="numero_serie" autocomplete="off">
                {select_options}
            </select>
            <div class="popup-error" id="popup-error"></div>
            <div class="popup-actions">
                <button class="btn-confirm" onclick="confirmarCadastro()">Confirmar</button>
                <button class="btn-cancel" onclick="closePopup()">Cancelar</button>
            </div>
        </div>
    </div>
    <div class="popup-bg" id="popup-list-bg">
        <div class="popup">
            <h3 style="margin-top:0;">Usuários Cadastrados</h3>
            <div id="usuarios-tabela" style="max-height:400px;overflow-y:auto;overflow-x:auto;width:100%;"></div>
            <div class="popup-actions">
                <button class="btn-cancel" onclick="closeListPopup()">Fechar</button>
            </div>
        </div>
    </div>
    <div class="popup-bg" id="popup-edit-centrais-bg" style="display:none;">
        <div class="popup">
            <h3 style="margin-top:0;">Editar Centrais</h3>
            <button class="btn-confirm" style="margin-bottom:12px;" onclick="abrirNovaCentralPopup()">Adicionar Nova Central</button>
            <div id="edit-centrais-content" style="max-height:400px;overflow-y:auto;overflow-x:auto;width:100%;"></div>
            <div class="popup-actions">
                <button class="btn-cancel" onclick="closeEditCentraisPopup()">Fechar</button>
            </div>
        </div>
    </div>
    <div class="popup-bg" id="novo-dado-popup-bg" style="display:none;">
        <div class="popup">
            <h3 style="margin-top:0;">Novo Evento Detectado</h3>
            <pre id="novo-dado-popup-dados" style="background:#181818;padding:12px 8px;border-radius:6px;color:#fff;font-size:1.08em;"></pre>
            <div class="popup-actions">
                <button class="btn-confirm" onclick="fecharNovoDadoPopup()">OK</button>
            </div>
        </div>
    </div>
    <div class="popup-bg" id="popup-editar-central-bg" style="display:none;">
        <div class="popup">
            <h3 style="margin-top:0;">Editar Central</h3>
            <label for="editar-numero-serie">Número de Série:</label>
            <input type="text" id="editar-numero-serie" maxlength="20" autocomplete="off"/>
            <label for="editar-nome-central">Nome:</label>
            <input type="text" id="editar-nome-central" maxlength="50" autocomplete="off"/>
            <div class="popup-error" id="popup-editar-central-erro"></div>
            <div class="popup-actions">
                <button class="btn-confirm" onclick="confirmarEditarCentral()">Salvar</button>
                <button class="btn-cancel" onclick="fecharEditarCentralPopup()">Cancelar</button>
            </div>
        </div>
    </div>
    <div class="popup-bg" id="popup-nova-central-bg" style="display:none;">
        <div class="popup">
            <h3 style="margin-top:0;">Adicionar Nova Central</h3>
            <label for="nova-central-numero-serie">Número de Série:</label>
            <input type="text" id="nova-central-numero-serie" maxlength="20" autocomplete="off"
                   oninput="this.value=this.value.replace(/[^0-9]/g,'')" />
            <label for="nova-central-nome">Nome:</label>
            <input type="text" id="nova-central-nome" maxlength="50" autocomplete="off"/>
            <div class="popup-error" id="popup-nova-central-erro"></div>
            <div class="popup-actions">
                <button class="btn-confirm" onclick="confirmarNovaCentral()">Adicionar</button>
                <button class="btn-cancel" onclick="fecharNovaCentralPopup()">Cancelar</button>
            </div>
        </div>
    </div>
    <div class="table-responsive">
        {html}
    </div>
</div>
{popup_script}
</body>
</html>"""

            if len(html.strip()) > 100 and all(tag in html for tag in ['<!DOCTYPE html>', '<html', '<head', '<body']):
                try:
                    with open('tabela_extraida.html', 'w', encoding='utf-8') as f:
                        f.write(html)
                    print("HTML atualizado com sucesso!")
                    
                    try:
                        with open('tabela_extraida.backup.html', 'w', encoding='utf-8') as f:
                            f.write(html)
                    except Exception as backup_error:
                        print(f"Aviso: Não foi possível criar backup do HTML: {str(backup_error)}")

                except Exception as e:
                    print(f"Erro ao salvar HTML: {str(e)}")
                    try:
                        if os.path.exists('tabela_extraida.backup.html'):
                            with open('tabela_extraida.backup.html', 'r', encoding='utf-8') as f_backup:
                                backup_content = f_backup.read()
                            with open('tabela_extraida.html', 'w', encoding='utf-8') as f:
                                f.write(backup_content)
                            print("HTML restaurado do backup com sucesso!")
                    except Exception as restore_error:
                        print(f"Erro ao restaurar do backup: {str(restore_error)}")
                    continue
            else:
                print("HTML gerado é inválido ou vazio. Mantendo versão anterior.")
                time.sleep(15)
                continue

            if primeira_execucao:
                webbrowser.open('http://localhost:8090/')
                primeira_execucao = False
            
            print("Atualizado. Próxima atualização em 15 segundos...")
            time.sleep(15)
        else:
            print("Tabela não encontrada ou sem dados após múltiplas tentativas.")
            time.sleep(15)

finally:
    driver.quit()
