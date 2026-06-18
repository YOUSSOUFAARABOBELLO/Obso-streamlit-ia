import base64, json, os
from io import BytesIO
import pandas as pd
import streamlit as st
from openai import OpenAI
from openai import APIError, RateLimitError, AuthenticationError, BadRequestError

st.set_page_config(page_title="Application d’aide à la gestion d’obsolescence", layout="wide", page_icon="🏭")
st.title("🏭 Application d’aide à la gestion d’obsolescence")
st.caption("Lecture intelligente des plaques signalétiques · IA Vision · Version robuste")

if "rows" not in st.session_state: st.session_state.rows = []
if "analyses" not in st.session_state: st.session_state.analyses = {}
if "raw_responses" not in st.session_state: st.session_state.raw_responses = {}
if "errors" not in st.session_state: st.session_state.errors = {}

def image_to_data_url(uploaded_file):
    b64 = base64.b64encode(uploaded_file.getvalue()).decode("utf-8")
    return f"data:{uploaded_file.type or 'image/jpeg'};base64,{b64}"

def empty_result(commentaire=""):
    return {
        "fabricant":"","reference":"","modele_type":"","numero_serie":"","annee":"",
        "famille_equipement":"","indice_protection":"","tension":"","courant":"",
        "puissance":"","normes":"","texte_lu":"","niveau_confiance":"faible",
        "commentaire":commentaire
    }

def safe_json_loads(text):
    if not text: return None
    try: return json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try: return json.loads(text[start:end+1])
            except Exception: return None
    return None

def analyze_plate_with_ai(uploaded_file):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None, "", "Clé API manquante. Ajoute OPENAI_API_KEY dans les secrets Streamlit."

    client = OpenAI(api_key=api_key)
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    prompt = """
Tu es un assistant spécialisé en maintenance industrielle et gestion d'obsolescence.
Analyse l'image d'une plaque signalétique ou d'un composant industriel.
Repère les zones de texte, lis les informations visibles, corrige uniquement les erreurs évidentes,
puis retourne uniquement un JSON valide.

Structure obligatoire :
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

Ne pas inventer. Si c'est incertain, laisse vide et explique dans commentaire.
"""

    try:
        response = client.responses.create(
            model=model_name,
            input=[{"role":"user","content":[
                {"type":"input_text","text":prompt},
                {"type":"input_image","image_url":image_to_data_url(uploaded_file)}
            ]}],
            max_output_tokens=900,
        )
        raw = response.output_text or ""
        parsed = safe_json_loads(raw)
        if parsed is None:
            res = empty_result("L’IA a répondu, mais la réponse n’était pas un JSON exploitable. Voir la réponse brute.")
            res["texte_lu"] = raw[:1500]
            return res, raw, None
        res = empty_result()
        res.update(parsed)
        return res, raw, None

    except RateLimitError:
        return None, "", "Limite API atteinte ou crédit insuffisant. Vérifie Billing/Usage sur platform.openai.com ou attends quelques minutes."
    except AuthenticationError:
        return None, "", "Erreur d’authentification : clé API incorrecte, absente ou mal copiée dans les Secrets."
    except BadRequestError as e:
        return None, "", "Requête refusée : image trop lourde/non lisible ou format non accepté. Détail : " + str(e)[:300]
    except APIError as e:
        return None, "", "Erreur API temporaire. Réessaie avec une seule image plus nette. Détail : " + str(e)[:300]
    except Exception as e:
        return None, "", f"Erreur inattendue : {type(e).__name__} - {str(e)[:300]}"

def score_obsolescence(criticite, maintenabilite, disponibilite, support, remplacement, annee):
    current_year = pd.Timestamp.today().year
    age, age_score = None, 1
    try:
        if annee:
            age = max(0, current_year - int(str(annee).strip()))
            if age >= 20: age_score = 4
            elif age >= 15: age_score = 3
            elif age >= 10: age_score = 2
    except Exception: pass
    score = int(criticite)*3 + int(maintenabilite)*2 + int(disponibilite)*3 + int(support)*3 + int(remplacement)*2 + age_score*2
    if score >= 38:
        return score, "Risque critique", "Substitution, retrofit ou sécurisation immédiate", age
    if score >= 30:
        return score, "Risque élevé", "Planifier une solution de remplacement et sécuriser les pièces", age
    if score >= 22:
        return score, "Risque moyen", "Surveiller, confirmer le support fabricant et identifier une alternative", age
    return score, "Risque faible", "Suivi périodique", age

def make_excel_download(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Suivi_obsolescence")
    output.seek(0)
    return output

with st.sidebar:
    st.header("⚙️ Paramètres")
    st.write("Modèle utilisé :", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    st.warning("Clique une seule fois sur Analyser : chaque clic consomme du crédit API.")

st.markdown("""
**Processus :** importer une photo → analyser avec IA → vérifier/corriger → calculer le risque → ajouter au tableau → exporter.
""")

uploaded_files = st.file_uploader(
    "Importer une ou plusieurs photos de plaques signalétiques",
    type=["jpg","jpeg","png","webp"],
    accept_multiple_files=True
)

if uploaded_files:
    st.subheader("1. Photos importées")
    for idx, uploaded_file in enumerate(uploaded_files):
        key = f"{idx}_{uploaded_file.name}"
        with st.expander(f"📷 {uploaded_file.name}", expanded=(idx == 0)):
            col_img, col_data = st.columns([1, 1.25])
            with col_img:
                st.image(uploaded_file, caption=uploaded_file.name, use_container_width=True)
                st.warning("Clique une seule fois : chaque analyse consomme du crédit API.", icon="⚠️")
                if st.button("Analyser cette plaque avec IA", key=f"analyze_{key}"):
                    st.session_state.errors.pop(key, None)
                    with st.spinner("Analyse IA en cours..."):
                        result, raw_text, error = analyze_plate_with_ai(uploaded_file)
                    st.session_state.raw_responses[key] = raw_text
                    if error:
                        st.session_state.errors[key] = error
                        st.error(error)
                    elif result:
                        st.session_state.analyses[key] = result
                        st.success("Analyse terminée. Vérifie les champs proposés.")
                if key in st.session_state.errors:
                    st.error(st.session_state.errors[key])
                if st.session_state.raw_responses.get(key):
                    with st.expander("Voir la réponse brute IA"):
                        st.text_area("Réponse brute", value=st.session_state.raw_responses.get(key, ""), height=220, key=f"raw_{key}")

            result = st.session_state.analyses.get(key, empty_result())
            with col_data:
                st.markdown("### 2. Fiche équipement préremplie")
                systeme = st.text_input("Système / banc", key=f"systeme_{key}")
                equipement = st.text_input("Nom équipement", value=result.get("famille_equipement",""), key=f"equipement_{key}")
                fabricant = st.text_input("Fabricant", value=result.get("fabricant",""), key=f"fabricant_{key}")
                reference = st.text_input("Référence", value=result.get("reference",""), key=f"reference_{key}")
                modele_type = st.text_input("Modèle / type", value=result.get("modele_type",""), key=f"modele_{key}")
                numero_serie = st.text_input("Numéro de série", value=result.get("numero_serie",""), key=f"serie_{key}")
                annee = st.text_input("Année", value=result.get("annee",""), key=f"annee_{key}")
                famille = st.text_input("Famille équipement", value=result.get("famille_equipement",""), key=f"famille_{key}")

                with st.expander("Informations techniques détectées"):
                    ip = st.text_input("Indice de protection", value=result.get("indice_protection",""), key=f"ip_{key}")
                    tension = st.text_input("Tension", value=result.get("tension",""), key=f"tension_{key}")
                    courant = st.text_input("Courant", value=result.get("courant",""), key=f"courant_{key}")
                    puissance = st.text_input("Puissance", value=result.get("puissance",""), key=f"puissance_{key}")
                    normes = st.text_input("Normes", value=result.get("normes",""), key=f"normes_{key}")
                    texte_lu = st.text_area("Texte lu par l’IA", value=result.get("texte_lu",""), height=120, key=f"texte_{key}")
                    confiance = st.text_input("Niveau de confiance", value=result.get("niveau_confiance",""), key=f"confiance_{key}")
                    commentaire = st.text_area("Commentaire IA", value=result.get("commentaire",""), height=80, key=f"commentaire_{key}")

                st.markdown("### 3. Critères d’obsolescence")
                c1, c2 = st.columns(2)
                with c1:
                    criticite = st.selectbox("Criticité", [1,2,3,4], format_func=lambda x:{1:"1 - Faible",2:"2 - Moyenne",3:"3 - Élevée",4:"4 - Critique"}[x], key=f"criticite_{key}")
                    maintenabilite = st.selectbox("Maintenabilité", [1,2,3,4], format_func=lambda x:{1:"1 - Bonne",2:"2 - Moyenne",3:"3 - Difficile",4:"4 - Très difficile"}[x], key=f"maint_{key}")
                    disponibilite = st.selectbox("Disponibilité pièce", [1,2,3,4], format_func=lambda x:{1:"1 - Disponible",2:"2 - Disponible sous délai",3:"3 - Rare",4:"4 - Indisponible"}[x], key=f"dispo_{key}")
                with c2:
                    support = st.selectbox("Support fabricant", [1,2,3,4], format_func=lambda x:{1:"1 - Support confirmé",2:"2 - Support partiel",3:"3 - Fin de support suspectée",4:"4 - Fin de support confirmée"}[x], key=f"support_{key}")
                    remplacement = st.selectbox("Solution de remplacement", [1,2,3,4], format_func=lambda x:{1:"1 - Solution disponible",2:"2 - Solution à confirmer",3:"3 - Solution complexe",4:"4 - Aucune solution identifiée"}[x], key=f"remplacement_{key}")

                score, statut, action, age = score_obsolescence(criticite, maintenabilite, disponibilite, support, remplacement, annee)
                st.markdown("### 4. Résultat")
                st.write(f"**Score :** {score}")
                st.write(f"**Statut :** {statut}")
                st.write(f"**Action recommandée :** {action}")

                if st.button("Ajouter au tableau de suivi", key=f"add_{key}"):
                    st.session_state.rows.append({
                        "Système": systeme, "Équipement": equipement, "Fabricant": fabricant, "Référence": reference,
                        "Modèle / type": modele_type, "Numéro de série": numero_serie, "Année": annee, "Famille": famille,
                        "IP": ip, "Tension": tension, "Courant": courant, "Puissance": puissance, "Normes": normes,
                        "Confiance IA": confiance, "Âge estimé": age, "Score": score, "Statut": statut, "Action recommandée": action
                    })
                    st.success("Équipement ajouté au tableau de suivi.")

                if fabricant or reference:
                    query = f"{fabricant} {reference} obsolescence datasheet replacement end of life"
                    st.link_button("Rechercher le fabricant / documentation", f"https://www.google.com/search?q={query.replace(' ', '+')}")

st.subheader("5. Tableau de suivi obsolescence")
if st.session_state.rows:
    df = pd.DataFrame(st.session_state.rows)
    edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")
    st.download_button("Télécharger CSV", data=edited_df.to_csv(index=False, sep=";").encode("utf-8-sig"), file_name="suivi_obsolescence.csv", mime="text/csv")
    st.download_button("Télécharger Excel", data=make_excel_download(edited_df), file_name="suivi_obsolescence.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
else:
    st.info("Aucun équipement ajouté pour le moment.")