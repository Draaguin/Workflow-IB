from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_dance.contrib.google import make_google_blueprint, google
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload
import os
import io
import datetime

# Configuração da aplicação Flask
app = Flask(__name__)
app.secret_key = '6a4b9ff81331bc9512bf4276ee6a856704c33c07c13d16cc8fc12541ca62efc8'

# Configuração do Flask-Dance para Google OAuth
google_bp = make_google_blueprint(client_id="564667358550-75m5bua0i4c4ubgedcks7av1nv7sj0k3.apps.googleusercontent.com",
                                  client_secret="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",
                                  redirect_to="google_login")
app.register_blueprint(google_bp, url_prefix="/login")

# Configuração do Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = "google.login"

class User(UserMixin):
    pass

@login_manager.user_loader
def load_user(user_id):
    user = User()
    user.id = user_id
    return user

@app.route("/")
@login_required
def index():
    return render_template("index.html", email=current_user.id)

@app.route("/login/google/authorized")
def google_login():
    if not google.authorized:
        return redirect(url_for("google.login"))
    resp = google.get("/oauth2/v2/userinfo")
    assert resp.ok, resp.text
    user_info = resp.json()
    user = User()
    user.id = user_info["email"]
    login_user(user)
    return redirect(url_for("index"))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

# Configuração do Google Sheets API
def get_sheets_service():
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    else:
        raise Exception("token.json não encontrado, execute a autenticação OAuth primeiro")
    
    service = build('sheets', 'v4', credentials=creds)
    return service

def upload_file_to_drive(anexo):
    # Configura as credenciais para o Google Drive
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    creds = service_account.Credentials.from_service_account_file('credentials.json', scopes=SCOPES)

    drive_service = build('drive', 'v3', credentials=creds)

    file_metadata = {
        'name': anexo.filename,
        'mimeType': anexo.mimetype
    }

    media = MediaFileUpload(anexo, mimetype=anexo.mimetype, resumable=True)
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

    # Cria um link compartilhável
    file_id = file.get('id')
    permission = {
        'type': 'anyone',
        'role': 'writer',
    }
    drive_service.permissions().create(fileId=file_id, body=permission).execute()

    link = f"https://drive.google.com/file/d/{file_id}/view"
    return link

@app.route("/form", methods=["GET", "POST"])
@login_required
def form():
    if 'google_token' not in session:
        return redirect(url_for('google.login'))

    # Obtém o e-mail do usuário autenticado
    user_info = google.get('userinfo')
    email = user_info.json()['email']

    if request.method == "POST":
        solicitante = email  # Usa o e-mail do usuário como solicitante
        data_solicitacao = request.form['data_solicitacao']
        descricao_ib = request.form['descricao_ib']
        numero_ib = request.form['numero_ib']
        anexo = request.files['anexo']

        # Salva o arquivo no Google Drive e obtém o link
        link_arquivo = upload_file_to_drive(anexo)

        # Adiciona a requisição na planilha do Google Sheets
        adicionar_requisicao(
            sheet_id='19kBxmQAhANDkVjgv8YvLnXmeXTXCsUtlRlM9nHhiXR4',
            solicitante=solicitante,
            data_solicitacao=data_solicitacao,
            descricao_ib=descricao_ib,
            numero_ib=numero_ib,
            status='Pendente',
            link_arquivo=link_arquivo
        )

        flash("Requisição submetida com sucesso!")
        return redirect(url_for("index"))

    return render_template('form.html', email=email)

@app.route("/aprovar/<int:linha>", methods=["GET", "POST"])
@login_required
def aprovar(linha):
    if request.method == "POST":
        status = request.form['status']
        observacoes = request.form['observacoes']
        data_aprovacao = request.form['data_aprovacao']

        atualizar_requisicao(
            sheet_id='19kBxmQAhANDkVjgv8YvLnXmeXTXCsUtlRlM9nHhiXR4',
            linha=linha,
            status=status,
            data_aprovacao=data_aprovacao,
            aprovador=current_user.id,
            observacoes=observacoes
        )

        flash("Requisição atualizada com sucesso!")
        return redirect(url_for("index"))

    # Aqui você pode carregar os dados atuais para exibir na página de aprovação
    return render_template("approval.html", linha=linha)

def adicionar_requisicao(sheet_id, solicitante, data_solicitacao, descricao_ib, numero_ib, status, link_arquivo):
    service = get_sheets_service()
    sheet = service.spreadsheets()

    nova_linha = [
        solicitante,
        data_solicitacao,
        descricao_ib,
        numero_ib,
        status,
        '',  # Data da Aprovação
        '',  # Aprovador
        '',  # Observações
        link_arquivo
    ]

    request = sheet.values().append(
        spreadsheetId=sheet_id,
        range="Sheet1!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [nova_linha]}
    ).execute()

def atualizar_requisicao(sheet_id, linha, status, data_aprovacao, aprovador, observacoes):
    service = get_sheets_service()
    sheet = service.spreadsheets()

    sheet.values().update(
        spreadsheetId=sheet_id,
        range=f"Sheet1!E{linha}:H{linha}",
        valueInputOption="RAW",
        body={"values": [[status, data_aprovacao, aprovador, observacoes]]}
    ).execute()

if __name__ == "__main__":
    port = int(os.getenv('PORT'), '5000')
    app.run(debug=True, host='0.0.0.0', port = port)
