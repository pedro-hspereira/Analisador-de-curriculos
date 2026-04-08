import os
import json
import re
import unicodedata
import requests
import streamlit as st
from PyPDF2 import PdfReader
import google.generativeai as genai

st.set_page_config(
    page_title="Analisador de Currículos",
    page_icon="🚀",
    layout="wide"
)

# =========================
# ESTILO
# =========================
st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: "Segoe UI", Arial, sans-serif !important;
}

.card-vaga {
    background-color: #111827;
    padding: 18px;
    border-radius: 14px;
    border: 1px solid #374151;
    margin-bottom: 12px;
}

.titulo-vaga {
    font-size: 19px;
    font-weight: 700;
    margin-bottom: 6px;
    color: #ffffff;
}

.empresa-vaga {
    color: #d1d5db;
    margin-bottom: 10px;
    font-size: 15px;
}

.desc-vaga {
    white-space: pre-wrap;
    line-height: 1.55;
    color: #e5e7eb;
    margin-top: 10px;
}

.link-vaga {
    margin-top: 8px;
    margin-bottom: 6px;
}

.link-toggle button {
    background: none !important;
    border: none !important;
    color: #60a5fa !important;
    padding: 0 !important;
    margin-top: 8px !important;
    text-decoration: underline !important;
    cursor: pointer !important;
    box-shadow: none !important;
}

.link-toggle button:hover {
    color: #93c5fd !important;
}
</style>
""", unsafe_allow_html=True)

# =========================
# VARIÁVEIS DE AMBIENTE
# =========================
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")

if not GEMINI_API_KEY or not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
    st.error(
        "Variáveis de ambiente não configuradas. Defina GOOGLE_API_KEY, ADZUNA_APP_ID e ADZUNA_APP_KEY."
    )
    st.stop()

# =========================
# GEMINI
# =========================
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# =========================
# ÁREAS E CONSULTAS
# =========================
AREAS_EXIBICAO = [
    "Desenvolvimento de Software",
    "Segurança da informação",
    "Ciência/Análise de dados",
    "Cloud computing",
    "Gestão de projetos",
    "Suporte técnico",
]

MAPEAMENTO_CONSULTAS = {
    "Desenvolvimento de Software": "software developer",
    "Segurança da informação": "information security",
    "Ciência/Análise de dados": "data analyst",
    "Cloud computing": "cloud engineer",
    "Gestão de projetos": "project manager",
    "Suporte técnico": "technical support",
}

# =========================
# SESSION STATE
# =========================
if "curriculo_texto" not in st.session_state:
    st.session_state.curriculo_texto = ""

if "vagas_ptbr" not in st.session_state:
    st.session_state.vagas_ptbr = []

if "analise_ia" not in st.session_state:
    st.session_state.analise_ia = None

if "ultima_area" not in st.session_state:
    st.session_state.ultima_area = ""

# =========================
# FUNÇÕES DE LIMPEZA
# =========================
def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKC", texto)
    texto = texto.replace("\u00a0", " ")
    return texto.strip()


def remover_tags_html(texto: str) -> str:
    if not texto:
        return ""
    return re.sub(r"<[^>]+>", "", texto)


def limpar_texto_para_exibicao(texto: str) -> str:
    if not texto:
        return ""

    texto = normalizar_texto(texto)
    texto = remover_tags_html(texto)

    texto = texto.replace("```json", "")
    texto = texto.replace("```html", "")
    texto = texto.replace("```", "")
    texto = texto.replace("&nbsp;", " ")
    texto = texto.replace("&lt;", "")
    texto = texto.replace("&gt;", "")
    texto = texto.replace("**", "")

    linhas = []
    for linha in texto.splitlines():
        linha_limpa = linha.strip()

        if not linha_limpa:
            linhas.append("")
            continue

        linha_lower = linha_limpa.lower()
        if "<div" in linha_lower or "</div" in linha_lower:
            continue
        if "<span" in linha_lower or "</span" in linha_lower:
            continue
        if "class=" in linha_lower:
            continue

        linhas.append(linha_limpa)

    texto = "\n".join(linhas)
    texto = re.sub(r"\n{3,}", "\n\n", texto)

    return texto.strip()

# =========================
# FUNÇÕES PRINCIPAIS
# =========================
def extrair_texto_pdf(arquivo):
    try:
        reader = PdfReader(arquivo)
        partes = []

        for page in reader.pages:
            conteudo = page.extract_text()
            if conteudo:
                partes.append(normalizar_texto(conteudo))

        return "\n".join(partes).strip()
    except Exception as e:
        st.error(f"Erro ao ler o PDF: {e}")
        return ""


def buscar_vagas(query="software developer"):
    url = "https://api.adzuna.com/v1/api/jobs/br/search/1"

    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "what": query,
        "results_per_page": 5
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        st.error(f"Erro ao buscar vagas: {e}")
        return []
    except ValueError:
        st.error("Resposta inválida da API de vagas.")
        return []

    vagas = []
    for vaga in data.get("results", []):
        vagas.append({
            "titulo": normalizar_texto(vaga.get("title", "Sem título")),
            "empresa": normalizar_texto(vaga.get("company", {}).get("display_name", "Empresa não informada")),
            "descricao": normalizar_texto(vaga.get("description", "")),
            "link": vaga.get("redirect_url", "")
        })

    return vagas


@st.cache_data(show_spinner=False)
def traduzir_vagas_para_ptbr(vagas):
    if not vagas:
        return []

    payload = []
    for i, vaga in enumerate(vagas, start=1):
        payload.append({
            "id": i,
            "titulo": vaga["titulo"],
            "empresa": vaga["empresa"],
            "descricao": vaga["descricao"][:1200],
            "link": vaga["link"]
        })

    prompt = f"""
Traduza as vagas abaixo para português do Brasil.

Regras:
- Traduza o título da vaga para pt-BR
- Traduza a descrição para pt-BR
- Mantenha o nome da empresa como está
- Não invente informações
- Responda somente em JSON válido
- Não use markdown
- Não use bloco de código
- Não use HTML

Formato de saída:
[
  {{
    "id": 1,
    "titulo": "titulo em pt-BR",
    "empresa": "nome da empresa",
    "descricao": "descricao em pt-BR",
    "link": "url"
  }}
]

Vagas:
{json.dumps(payload, ensure_ascii=False)}
"""

    try:
        resposta = model.generate_content(prompt)
        texto = limpar_texto_para_exibicao(resposta.text)
        traduzidas = json.loads(texto)

        vagas_traduzidas = []
        for item in traduzidas:
            vagas_traduzidas.append({
                "titulo": limpar_texto_para_exibicao(item.get("titulo", "")),
                "empresa": limpar_texto_para_exibicao(item.get("empresa", "")),
                "descricao": limpar_texto_para_exibicao(item.get("descricao", "")),
                "link": item.get("link", "")
            })

        if vagas_traduzidas:
            return vagas_traduzidas

        return vagas

    except Exception:
        return vagas


def analisar_com_vagas(curriculo, vagas, area_escolhida):
    resumo_vagas = []
    for vaga in vagas:
        resumo_vagas.append({
            "titulo": vaga["titulo"],
            "empresa": vaga["empresa"],
            "descricao": vaga["descricao"][:500]
        })

    prompt = f"""
Você é um recrutador experiente, com escrita natural, humana e agradável de ler.

Analise o currículo do candidato em relação às vagas reais fornecidas e à área desejada.

Área desejada:
{area_escolhida}

Currículo:
{curriculo}

Vagas disponíveis:
{json.dumps(resumo_vagas, ensure_ascii=False)}

Responda SOMENTE em JSON válido.
Não use markdown.
Não use bloco de código.
Não escreva nada fora do JSON.
Não use HTML.
Não use tags.
Não use listas numeradas.

Formato:
{{
  "area_ideal": "texto curto explicando a área ideal",
  "o_que_falta_melhorar": "texto curto, humano e construtivo"
}}

Regras:
- Tudo em português do Brasil
- Tom humano, natural e não robótico
- Não invente vagas
- Não liste as vagas aqui
- Seja objetivo
"""

    try:
        resposta = model.generate_content(prompt)
        texto = limpar_texto_para_exibicao(resposta.text)
        dados = json.loads(texto)

        return {
            "area_ideal": limpar_texto_para_exibicao(dados.get("area_ideal", "")),
            "o_que_falta_melhorar": limpar_texto_para_exibicao(dados.get("o_que_falta_melhorar", ""))
        }

    except Exception as e:
        return {
            "area_ideal": "",
            "o_que_falta_melhorar": f"Erro ao analisar com Gemini: {e}"
        }


def mostrar_analise_formatada(analise):
    st.subheader("Área ideal")
    st.write(analise.get("area_ideal", "") or "Não disponível.")

    st.subheader("O que falta melhorar")
    st.write(analise.get("o_que_falta_melhorar", "") or "Não disponível.")


def mostrar_vaga(vaga, indice):
    titulo = vaga["titulo"]
    empresa = vaga["empresa"]
    descricao = vaga["descricao"]
    link = vaga["link"]

    chave_expandida = f"vaga_expandida_{indice}"
    if chave_expandida not in st.session_state:
        st.session_state[chave_expandida] = False

    expandida = st.session_state[chave_expandida]

    if expandida:
        descricao_exibida = descricao
    else:
        descricao_exibida = descricao[:280].strip()
        if len(descricao) > 280:
            descricao_exibida += "... "

    st.markdown(f"""
    <div class="card-vaga">
        <div class="titulo-vaga">{titulo}</div>
        <div class="empresa-vaga">{empresa}</div>
    """, unsafe_allow_html=True)

    if link:
        st.markdown(
            f'<div class="link-vaga"><a href="{link}" target="_blank">Abrir vaga</a></div>',
            unsafe_allow_html=True
        )

    st.markdown(f'<div class="desc-vaga">{descricao_exibida}</div>', unsafe_allow_html=True)

    if len(descricao) > 280:
        st.markdown('<div class="link-toggle">', unsafe_allow_html=True)
        if not expandida:
            if st.button("Ler mais", key=f"btn_ler_mais_{indice}"):
                st.session_state[chave_expandida] = True
                st.rerun()
        else:
            if st.button("Mostrar menos", key=f"btn_mostrar_menos_{indice}"):
                st.session_state[chave_expandida] = False
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("---")

# =========================
# INTERFACE
# =========================
st.title("🚀Envie seu currículo em PDF e descubra vagas de tecnologia que combinam com você!")

arquivo = st.file_uploader("Envie seu currículo (PDF)", type=["pdf"])

area_exibida = st.selectbox("Área desejada", AREAS_EXIBICAO)
consulta_api = MAPEAMENTO_CONSULTAS[area_exibida]

if arquivo is not None:
    texto_extraido = extrair_texto_pdf(arquivo)
    st.session_state.curriculo_texto = texto_extraido

if st.button("🔍 Buscar vagas e analisar"):
    if not st.session_state.curriculo_texto.strip():
        st.error(
            "Não foi possível extrair texto do PDF. Verifique se o arquivo está protegido ou se contém texto selecionável."
        )
    else:
        st.session_state.ultima_area = area_exibida

        with st.spinner("Buscando vagas..."):
            vagas = buscar_vagas(consulta_api)

        if not vagas:
            st.session_state.vagas_ptbr = []
            st.session_state.analise_ia = None
            st.warning("Nenhuma vaga encontrada para a área selecionada.")
        else:
            with st.spinner("Traduzindo vagas para pt-BR..."):
                vagas_ptbr = traduzir_vagas_para_ptbr(vagas)

            with st.spinner("Analisando currículo com IA..."):
                analise = analisar_com_vagas(
                    st.session_state.curriculo_texto,
                    vagas_ptbr,
                    area_exibida
                )

            st.session_state.vagas_ptbr = vagas_ptbr
            st.session_state.analise_ia = analise

if st.session_state.analise_ia:
    st.subheader("🧠 Análise da IA")
    mostrar_analise_formatada(st.session_state.analise_ia)

if st.session_state.vagas_ptbr:
    st.subheader("💼 Vagas encontradas")
    for i, vaga in enumerate(st.session_state.vagas_ptbr, start=1):
        mostrar_vaga(vaga, i)
