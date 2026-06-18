import base64
import json
import os
from io import BytesIO

import pandas as pd
import streamlit as st
from openai import OpenAI


st.set_page_config(
    page_title="Application d’aide à la gestion d’obsolescence",
    layout="wide",
    page_icon="🏭",
)

st.title("🏭 Application d’aide à la gestion d’obsolescence")
st.caption("Lecture intelligente des plaques signalétiques · IA Vision · Prototype en ligne")

st.markdown(
    """
Cette application permet d’importer une ou plusieurs photos de plaques signalétiques, 
d’extraire automatiquement les informations utiles avec une IA Vision, puis de préremplir 
une fiche équipement à vérifier avant l’analyse d’obsolescence.
"""
)

if "rows" not in st.session_state:
    st.session_state.rows = []

if "analyses" not in st.session_state:
    st.session_state.analyses = {}


def image_to_data_url(uploaded_file):
    mime = uploaded_file.type or "image/jpeg"
    b64 = base64.b64encode(uploaded_file.getvalue()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def safe_json_loads(text):
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise ValueError("La réponse IA n'est pas un JSON valide.")


def analyze_plate_with_ai(uploaded_file):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error(
            "Clé API manquante. Ajoute OPENAI_API_KEY dans les secrets de l’application en ligne."
        )
        return None

    client = OpenAI(api_key=api_key)
    image_url = image_to_data_url(uploaded_file)

    prompt = """
Tu es un assistant spécialisé en maintenance industrielle et gestion d'obsolescence.
Analyse l'image d'une plaque signalétique ou d'un composant industriel.

Objectifs :
1. Identifier les zones contenant du texte.
2. Lire les informations techniques visibles.
3. Corriger les erreurs probables de lecture.
4. Structurer les informations dans un JSON strict.

Retourne uniquement un JSON valide avec les champs suivants :
{
  "fabricant": "",
  "reference": "",
  "modele_type": "",
  "numero_serie": "",
  "annee": "",
  "famille_equipement": "",
  "indice_protection": "",
  "tension": "",
  "courant": "",
  "puissance": "",
  "normes": "",
  "texte_lu": "",
  "niveau_confiance": "faible | moyen | eleve",
  "commentaire": ""
}

Règles :
- Ne pas inventer une information non visible.
- Si une information est incertaine, indique-le dans le commentaire.
- Pour la famille, propose une catégorie utile en maintenance : moteur, servomoteur, variateur, automate, capteur, codeur, interrupteur de sécurité, réducteur, pompe, couple-mètre, PC supervision, baie de contrôle, autre.
- Si la plaque est difficile à lire, extrais quand même ce qui semble fiable.
"""

    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_url},
                ],
            }
        ],
    )

    text = response.output_text
    return safe_json_loads(text)


def score_obsolescence(criticite, maintenabilite, disponibilite, support, remplacement, annee):
    current_year = pd.Timestamp.today().year

    age_score = 1
    age = None
    try:
        if annee:
            age = max(0, current_year - int(str(annee).strip()))
            if age >= 20:
                age_score = 4
            elif age >= 15:
                age_score = 3
            elif age >= 10:
                age_score = 2
    except Exception:
        age_score = 1

    score = (
        int(criticite) * 3
        + int(maintenabilite) * 2
        + int(disponibilite) * 3
        + int(support) * 3
        + int(remplacement) * 2
        + age_score * 2
    )

    if score >= 38:
        statut = "Risque critique"
        action = "Substitution, retrofit ou sécurisation immédiate"
    elif score >= 30:
        statut = "Risque élevé"
        action = "Planifier une solution de remplacement et sécuriser les pièces"
    elif score >= 22:
        statut = "Risque moyen"
        action = "Surveiller, confirmer le support fabricant et identifier une alternative"
    else:
        statut = "Risque faible"
        action = "Suivi périodique"

    return score, statut, action, age


def make_excel_download(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Suivi_obsolescence")
    output.seek(0)
    return output


with st.sidebar:
    st.header("⚙️ Paramètres")
    st.info(
        "Pour la version en ligne, il faut ajouter la clé OPENAI_API_KEY dans les secrets de l’application."
    )
    st.markdown(
        """
**Processus :**
1. Importer les photos  
2. Analyser avec IA  
3. Vérifier/corriger  
4. Calculer le risque  
5. Exporter  
"""
    )

uploaded_files = st.file_uploader(
    "Importer une ou plusieurs photos de plaques signalétiques",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
)

if uploaded_files:
    st.subheader("1. Photos importées")

    for idx, uploaded_file in enumerate(uploaded_files):
        key = f"{idx}_{uploaded_file.name}"

        with st.expander(f"📷 {uploaded_file.name}", expanded=(idx == 0)):
            col_img, col_data = st.columns([1, 1.25])

            with col_img:
                st.image(uploaded_file, caption=uploaded_file.name, use_container_width=True)

                if st.button("Analyser cette plaque avec IA", key=f"analyze_{key}"):
                    with st.spinner("Analyse IA en cours..."):
                        result = analyze_plate_with_ai(uploaded_file)
                    if result:
                        st.session_state.analyses[key] = result
                        st.success("Analyse terminée. Vérifie les champs proposés.")

            result = st.session_state.analyses.get(key, {})

            with col_data:
                st.markdown("### 2. Fiche équipement préremplie")

                systeme = st.text_input("Système / banc", value="", key=f"systeme_{key}")
                equipement = st.text_input(
                    "Nom équipement",
                    value=result.get("famille_equipement", ""),
                    key=f"equipement_{key}",
                )

                fabricant = st.text_input(
                    "Fabricant",
                    value=result.get("fabricant", ""),
                    key=f"fabricant_{key}",
                )
                reference = st.text_input(
                    "Référence",
                    value=result.get("reference", ""),
                    key=f"reference_{key}",
                )
                modele_type = st.text_input(
                    "Modèle / type",
                    value=result.get("modele_type", ""),
                    key=f"modele_{key}",
                )
                numero_serie = st.text_input(
                    "Numéro de série",
                    value=result.get("numero_serie", ""),
                    key=f"serie_{key}",
                )
                annee = st.text_input(
                    "Année",
                    value=result.get("annee", ""),
                    key=f"annee_{key}",
                )
                famille = st.text_input(
                    "Famille équipement",
                    value=result.get("famille_equipement", ""),
                    key=f"famille_{key}",
                )

                with st.expander("Informations techniques détectées"):
                    st.text_input(
                        "Indice de protection",
                        value=result.get("indice_protection", ""),
                        key=f"ip_{key}",
                    )
                    st.text_input(
                        "Tension",
                        value=result.get("tension", ""),
                        key=f"tension_{key}",
                    )
                    st.text_input(
                        "Courant",
                        value=result.get("courant", ""),
                        key=f"courant_{key}",
                    )
                    st.text_input(
                        "Puissance",
                        value=result.get("puissance", ""),
                        key=f"puissance_{key}",
                    )
                    st.text_input(
                        "Normes",
                        value=result.get("normes", ""),
                        key=f"normes_{key}",
                    )
                    st.text_area(
                        "Texte lu par l’IA",
                        value=result.get("texte_lu", ""),
                        height=120,
                        key=f"texte_{key}",
                    )
                    st.text_input(
                        "Niveau de confiance",
                        value=result.get("niveau_confiance", ""),
                        key=f"confiance_{key}",
                    )
                    st.text_area(
                        "Commentaire IA",
                        value=result.get("commentaire", ""),
                        height=80,
                        key=f"commentaire_{key}",
                    )

                st.markdown("### 3. Critères d’obsolescence")

                c1, c2 = st.columns(2)
                with c1:
                    criticite = st.selectbox(
                        "Criticité",
                        options=[1, 2, 3, 4],
                        format_func=lambda x: {
                            1: "1 - Faible",
                            2: "2 - Moyenne",
                            3: "3 - Élevée",
                            4: "4 - Critique",
                        }[x],
                        key=f"criticite_{key}",
                    )
                    maintenabilite = st.selectbox(
                        "Maintenabilité",
                        options=[1, 2, 3, 4],
                        format_func=lambda x: {
                            1: "1 - Bonne",
                            2: "2 - Moyenne",
                            3: "3 - Difficile",
                            4: "4 - Très difficile",
                        }[x],
                        key=f"maint_{key}",
                    )
                    disponibilite = st.selectbox(
                        "Disponibilité pièce",
                        options=[1, 2, 3, 4],
                        format_func=lambda x: {
                            1: "1 - Disponible",
                            2: "2 - Disponible sous délai",
                            3: "3 - Rare",
                            4: "4 - Indisponible",
                        }[x],
                        key=f"dispo_{key}",
                    )

                with c2:
                    support = st.selectbox(
                        "Support fabricant",
                        options=[1, 2, 3, 4],
                        format_func=lambda x: {
                            1: "1 - Support confirmé",
                            2: "2 - Support partiel",
                            3: "3 - Fin de support suspectée",
                            4: "4 - Fin de support confirmée",
                        }[x],
                        key=f"support_{key}",
                    )
                    remplacement = st.selectbox(
                        "Solution de remplacement",
                        options=[1, 2, 3, 4],
                        format_func=lambda x: {
                            1: "1 - Solution disponible",
                            2: "2 - Solution à confirmer",
                            3: "3 - Solution complexe",
                            4: "4 - Aucune solution identifiée",
                        }[x],
                        key=f"remplacement_{key}",
                    )

                score, statut, action, age = score_obsolescence(
                    criticite,
                    maintenabilite,
                    disponibilite,
                    support,
                    remplacement,
                    annee,
                )

                st.markdown("### 4. Résultat")
                st.write(f"**Score :** {score}")
                st.write(f"**Statut :** {statut}")
                st.write(f"**Action recommandée :** {action}")

                if st.button("Ajouter au tableau de suivi", key=f"add_{key}"):
                    st.session_state.rows.append(
                        {
                            "Système": systeme,
                            "Équipement": equipement,
                            "Fabricant": fabricant,
                            "Référence": reference,
                            "Modèle / type": modele_type,
                            "Numéro de série": numero_serie,
                            "Année": annee,
                            "Famille": famille,
                            "Âge estimé": age,
                            "Score": score,
                            "Statut": statut,
                            "Action recommandée": action,
                        }
                    )
                    st.success("Équipement ajouté au tableau de suivi.")

                if fabricant or reference:
                    query = f"{fabricant} {reference} obsolescence datasheet replacement end of life"
                    st.link_button(
                        "Rechercher le fabricant / documentation",
                        f"https://www.google.com/search?q={query.replace(' ', '+')}",
                    )

st.subheader("5. Tableau de suivi obsolescence")

if st.session_state.rows:
    df = pd.DataFrame(st.session_state.rows)
    edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")

    csv = edited_df.to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        "Télécharger CSV",
        data=csv,
        file_name="suivi_obsolescence.csv",
        mime="text/csv",
    )

    excel_file = make_excel_download(edited_df)
    st.download_button(
        "Télécharger Excel",
        data=excel_file,
        file_name="suivi_obsolescence.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Aucun équipement ajouté pour le moment.")