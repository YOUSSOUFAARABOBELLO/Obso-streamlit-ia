import base64
import json
import os
import re
from io import BytesIO

import pandas as pd
import streamlit as st
from openai import OpenAI
from openai import APIError, AuthenticationError, BadRequestError, RateLimitError


st.set_page_config(
    page_title="Cycle de vie équipement - Obsolescence",
    page_icon="🔎",
    layout="wide",
)

st.title("🔎 Analyse du cycle de vie d’un équipement")
st.caption("Lecture de plaques · Cycle de vie constructeur · Obsolescence · Remplacement")

st.markdown(
    """
Cette application permet de charger une photo de plaque signalétique, d’identifier automatiquement
l’équipement, puis de rechercher son statut de cycle de vie auprès du constructeur ou d’une source fiable.

**Objectif :** savoir si l’équipement est encore actif, obsolète, remplacé ou en fin de vie programmée,
avec les sources et la proposition de remplacement si elle existe.
"""
)

if "rows" not in st.session_state:
    st.session_state.rows = []

if "plate_results" not in st.session_state:
    st.session_state.plate_results = {}

if "lifecycle_results" not in st.session_state:
    st.session_state.lifecycle_results = {}

if "raw_plate" not in st.session_state:
    st.session_state.raw_plate = {}

if "raw_lifecycle" not in st.session_state:
    st.session_state.raw_lifecycle = {}


def image_to_data_url(uploaded_file):
    b64 = base64.b64encode(uploaded_file.getvalue()).decode("utf-8")
    return f"data:{uploaded_file.type or 'image/jpeg'};base64,{b64}"


def clean_json_text(text):
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def safe_json_loads(text):
    cleaned = clean_json_text(text)
    if not cleaned:
        return None
    try:
        return json.loads(cleaned)
    except Exception:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except Exception:
                return None
    return None


def get_client():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None, "Clé API manquante. Ajoute OPENAI_API_KEY dans les secrets Streamlit."
    return OpenAI(api_key=api_key), None


def empty_plate_result():
    return {
        "fabricant": "",
        "reference": "",
        "modele_type": "",
        "numero_serie": "",
        "famille_equipement": "",
        "caracteristiques": "",
        "texte_lu": "",
        "niveau_confiance": "",
        "commentaire": "",
    }


def empty_lifecycle_result():
    return {
        "statut_actuel": "",
        "conclusion_obsolescence": "",
        "date_fin_commercialisation": "",
        "date_fin_support": "",
        "date_fin_service": "",
        "remplacement_disponible": "",
        "reference_remplacement": "",
        "fabricant_remplacement": "",
        "ce_que_dit_le_constructeur": "",
        "fournisseur_ou_source_secondaire": "",
        "niveau_confiance": "",
        "sources": [],
        "commentaire": "",
    }


def analyze_plate(uploaded_file):
    client, error = get_client()
    if error:
        return None, "", error

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    prompt = """
Tu es un assistant spécialisé en lecture de plaques signalétiques d’équipements industriels.
Analyse l’image et identifie l’équipement.

Retourne uniquement un JSON valide, sans texte autour, avec cette structure :
{
  "fabricant": "",
  "reference": "",
  "modele_type": "",
  "numero_serie": "",
  "famille_equipement": "",
  "caracteristiques": "",
  "texte_lu": "",
  "niveau_confiance": "faible | moyen | eleve",
  "commentaire": ""
}

Règles :
- Ne pas inventer.
- Si une information est incertaine, laisse vide ou indique l’incertitude dans commentaire.
- Le champ caracteristiques peut contenir tension, courant, IP, normes, puissance, etc.
- La famille peut être : variateur, servomoteur, moteur, automate, capteur, codeur, interrupteur de sécurité, réducteur, couple-mètre, pompe, autre.
"""

    try:
        response = client.responses.create(
            model=model_name,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": image_to_data_url(uploaded_file)},
                    ],
                }
            ],
            max_output_tokens=800,
        )
        raw = response.output_text or ""
        parsed = safe_json_loads(raw)

        if parsed is None:
            fallback = empty_plate_result()
            fallback["texte_lu"] = raw[:1500]
            fallback["commentaire"] = "Réponse IA non structurée. Voir réponse brute."
            return fallback, raw, None

        result = empty_plate_result()
        result.update(parsed)
        return result, raw, None

    except RateLimitError:
        return None, "", "Limite API atteinte ou crédit insuffisant."
    except AuthenticationError:
        return None, "", "Erreur d’authentification : clé API incorrecte ou mal copiée."
    except BadRequestError as e:
        return None, "", "Image ou requête refusée. Détail : " + str(e)[:250]
    except APIError as e:
        return None, "", "Erreur API temporaire. Détail : " + str(e)[:250]
    except Exception as e:
        return None, "", f"Erreur inattendue : {type(e).__name__} - {str(e)[:250]}"


def lifecycle_search(fabricant, reference, modele_type, famille):
    client, error = get_client()
    if error:
        return None, "", error

    model_name = os.getenv("OPENAI_SEARCH_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    prompt = f"""
Tu es un assistant spécialisé en gestion d’obsolescence industrielle.

Tu dois rechercher le cycle de vie actuel de cet équipement en priorité auprès :
1. du constructeur officiel ;
2. du catalogue ou support officiel du constructeur ;
3. d’une fiche datasheet officielle ;
4. d’un fournisseur/distributeur reconnu seulement si le constructeur ne donne pas l’information.

Équipement :
- Fabricant : {fabricant}
- Référence : {reference}
- Modèle/type : {modele_type}
- Famille : {famille}

Questions à traiter :
- Quel est le statut actuel de l’équipement ?
- Est-il obsolète, discontinué, remplacé, encore actif, ou en fin de vie programmée ?
- Si le constructeur donne une date de fin de commercialisation, fin de support, fin de service ou last buy, la reporter.
- Si un remplacement est proposé, donner la référence du remplacement.
- Donner les sources utilisées avec URL.
- Si aucune source constructeur claire n’est trouvée, le dire explicitement.

Retourne uniquement un JSON valide :
{{
  "statut_actuel": "actif | non obsolète | obsolète confirmé | obsolète suspecté | remplacé | fin de vie programmée | non trouvé",
  "conclusion_obsolescence": "",
  "date_fin_commercialisation": "",
  "date_fin_support": "",
  "date_fin_service": "",
  "remplacement_disponible": "oui | non | à vérifier",
  "reference_remplacement": "",
  "fabricant_remplacement": "",
  "ce_que_dit_le_constructeur": "",
  "fournisseur_ou_source_secondaire": "",
  "niveau_confiance": "faible | moyen | eleve",
  "sources": [
    {{"titre": "", "url": "", "type_source": "constructeur | datasheet | catalogue | support | fournisseur | autre"}}
  ],
  "commentaire": ""
}}

Règles :
- Ne jamais inventer une date.
- Ne jamais inventer une source.
- Si la source est un fournisseur et non le constructeur, préciser que ce n’est pas une confirmation constructeur.
- Si l’équipement est obsolète mais qu’un remplacement n’est pas trouvé, dire : remplacement non identifié.
- La conclusion doit être directement exploitable dans un tableau d’analyse d’obsolescence.
"""

    # Certains comptes acceptent web_search_preview, d’autres web_search. On tente les deux.
    tools_options = [
        [{"type": "web_search_preview"}],
        [{"type": "web_search"}],
    ]

    last_error = None
    for tools in tools_options:
        try:
            response = client.responses.create(
                model=model_name,
                tools=tools,
                input=prompt,
                max_output_tokens=1300,
            )
            raw = response.output_text or ""
            parsed = safe_json_loads(raw)

            if parsed is None:
                fallback = empty_lifecycle_result()
                fallback["ce_que_dit_le_constructeur"] = raw[:1800]
                fallback["commentaire"] = "Réponse non structurée. Voir réponse brute."
                return fallback, raw, None

            result = empty_lifecycle_result()
            result.update(parsed)
            if not isinstance(result.get("sources"), list):
                result["sources"] = []
            return result, raw, None

        except BadRequestError as e:
            last_error = str(e)[:300]
            continue
        except RateLimitError:
            return None, "", "Limite API atteinte ou crédit insuffisant pendant la recherche constructeur."
        except AuthenticationError:
            return None, "", "Erreur d’authentification API."
        except APIError as e:
            return None, "", "Erreur API temporaire. Détail : " + str(e)[:250]
        except Exception as e:
            return None, "", f"Erreur inattendue : {type(e).__name__} - {str(e)[:250]}"

    return None, "", "La recherche web n’est pas disponible avec ce compte/modèle. Détail : " + str(last_error)


def fill_plate_session(key, result):
    for field, value in {
        "fabricant": result.get("fabricant", ""),
        "reference": result.get("reference", ""),
        "modele_type": result.get("modele_type", ""),
        "numero_serie": result.get("numero_serie", ""),
        "famille_equipement": result.get("famille_equipement", ""),
        "caracteristiques": result.get("caracteristiques", ""),
        "texte_lu": result.get("texte_lu", ""),
        "confiance_plaque": result.get("niveau_confiance", ""),
        "commentaire_plaque": result.get("commentaire", ""),
    }.items():
        st.session_state[f"{field}_{key}"] = "" if value is None else str(value)


def fill_lifecycle_session(key, result):
    for field, value in {
        "statut_actuel": result.get("statut_actuel", ""),
        "conclusion_obsolescence": result.get("conclusion_obsolescence", ""),
        "date_fin_commercialisation": result.get("date_fin_commercialisation", ""),
        "date_fin_support": result.get("date_fin_support", ""),
        "date_fin_service": result.get("date_fin_service", ""),
        "remplacement_disponible": result.get("remplacement_disponible", ""),
        "reference_remplacement": result.get("reference_remplacement", ""),
        "fabricant_remplacement": result.get("fabricant_remplacement", ""),
        "ce_que_dit_le_constructeur": result.get("ce_que_dit_le_constructeur", ""),
        "source_secondaire": result.get("fournisseur_ou_source_secondaire", ""),
        "confiance_source": result.get("niveau_confiance", ""),
        "commentaire_source": result.get("commentaire", ""),
    }.items():
        st.session_state[f"{field}_{key}"] = "" if value is None else str(value)


def make_excel_download(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Cycle_de_vie")
    output.seek(0)
    return output


uploaded_files = st.file_uploader(
    "Charger une ou plusieurs photos de plaques signalétiques",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
)

if uploaded_files:
    st.markdown("### Actions")
    lire_tout = st.button("Lire toutes les plaques importées", type="primary")

    if lire_tout:
        progress = st.progress(0)
        total = len(uploaded_files)

        for i, file_to_read in enumerate(uploaded_files):
            key_all = f"{i}_{file_to_read.name}".replace(" ", "_").replace(".", "_")

            # Si l'image a déjà été lue, on ne relance pas automatiquement
            # pour éviter de consommer inutilement du crédit API.
            if key_all in st.session_state.plate_results:
                progress.progress((i + 1) / total)
                continue

            with st.spinner(f"Lecture de la plaque {i + 1}/{total} : {file_to_read.name}"):
                result, raw, error = analyze_plate(file_to_read)

            st.session_state.raw_plate[key_all] = raw

            if error:
                st.warning(f"Erreur sur {file_to_read.name} : {error}")
            elif result:
                st.session_state.plate_results[key_all] = result
                fill_plate_session(key_all, result)

            progress.progress((i + 1) / total)

        st.success("Lecture terminée. Vérifie les informations extraites.")
        st.rerun()

    rechercher_tout = st.button("Rechercher le cycle de vie de toutes les plaques lues", type="secondary")

    if rechercher_tout:
        if len(st.session_state.plate_results) == 0:
            st.warning("Aucune plaque lue pour le moment. Lance d’abord la lecture des plaques.")
        else:
            progress_life = st.progress(0)
            items = list(st.session_state.plate_results.items())

            for j, (key_life, plate_data) in enumerate(items):
                if key_life in st.session_state.lifecycle_results:
                    progress_life.progress((j + 1) / len(items))
                    continue

                fabricant_life = plate_data.get("fabricant", "")
                reference_life = plate_data.get("reference", "")
                modele_life = plate_data.get("modele_type", "")
                famille_life = plate_data.get("famille_equipement", "")

                if not fabricant_life and not reference_life:
                    progress_life.progress((j + 1) / len(items))
                    continue

                with st.spinner(f"Recherche cycle de vie {j + 1}/{len(items)}"):
                    result, raw, error = lifecycle_search(
                        fabricant_life,
                        reference_life,
                        modele_life,
                        famille_life,
                    )

                st.session_state.raw_lifecycle[key_life] = raw

                if error:
                    st.warning(f"Recherche non aboutie pour {fabricant_life} {reference_life}.")
                elif result:
                    st.session_state.lifecycle_results[key_life] = result
                    fill_lifecycle_session(key_life, result)

                    existing_keys = [r.get("_key", "") for r in st.session_state.rows]
                    if key_life not in existing_keys:
                        sources = result.get("sources", [])
                        source_urls = " | ".join([s.get("url", "") for s in sources if s.get("url")])
                        st.session_state.rows.append(
                            {
                                "_key": key_life,
                                "Fabricant": fabricant_life,
                                "Référence": reference_life,
                                "Modèle/type": modele_life,
                                "N° série": plate_data.get("numero_serie", ""),
                                "Famille": famille_life,
                                "Caractéristiques plaque": plate_data.get("caracteristiques", ""),
                                "Statut actuel": result.get("statut_actuel", ""),
                                "Conclusion obsolescence": result.get("conclusion_obsolescence", ""),
                                "Fin commercialisation": result.get("date_fin_commercialisation", ""),
                                "Fin support": result.get("date_fin_support", ""),
                                "Fin service": result.get("date_fin_service", ""),
                                "Remplacement disponible": result.get("remplacement_disponible", ""),
                                "Référence remplacement": result.get("reference_remplacement", ""),
                                "Fabricant remplacement": result.get("fabricant_remplacement", ""),
                                "Ce que dit constructeur": result.get("ce_que_dit_le_constructeur", ""),
                                "Source secondaire": result.get("fournisseur_ou_source_secondaire", ""),
                                "Confiance lecture": plate_data.get("niveau_confiance", ""),
                                "Confiance source": result.get("niveau_confiance", ""),
                                "Sources": source_urls,
                            }
                        )

                progress_life.progress((j + 1) / len(items))

            st.success("Recherche terminée. Le tableau de synthèse a été mis à jour.")
            st.rerun()

    st.divider()

    for idx, uploaded_file in enumerate(uploaded_files):
        key = f"{idx}_{uploaded_file.name}".replace(" ", "_").replace(".", "_")

        st.divider()
        st.subheader(f"Équipement : {uploaded_file.name}")

        col_img, col_infos = st.columns([1, 1.3])

        with col_img:
            st.image(uploaded_file, caption=uploaded_file.name, use_container_width=True)

            if st.button("1. Lire la plaque avec IA", key=f"read_{key}"):
                with st.spinner("Lecture de la plaque en cours..."):
                    result, raw, error = analyze_plate(uploaded_file)

                st.session_state.raw_plate[key] = raw

                if error:
                    st.error(error)
                elif result:
                    st.session_state.plate_results[key] = result
                    fill_plate_session(key, result)
                    st.success("Lecture terminée. Vérifie les informations extraites.")
                    st.rerun()

            if st.session_state.raw_plate.get(key):
                with st.expander("Voir la réponse brute de lecture plaque"):
                    st.text_area(
                        "Réponse brute lecture",
                        value=st.session_state.raw_plate.get(key, ""),
                        height=180,
                        key=f"raw_plate_{key}",
                    )

        with col_infos:
            st.markdown("### 1. Informations extraites de la plaque")

            fabricant = st.text_input("Fabricant", key=f"fabricant_{key}")
            reference = st.text_input("Référence", key=f"reference_{key}")
            modele_type = st.text_input("Modèle / type", key=f"modele_type_{key}")
            numero_serie = st.text_input("Numéro de série", key=f"numero_serie_{key}")
            famille = st.text_input("Famille équipement", key=f"famille_equipement_{key}")
            caracteristiques = st.text_area("Caractéristiques lues sur la plaque", height=80, key=f"caracteristiques_{key}")
            confiance_plaque = st.text_input("Niveau de confiance lecture", key=f"confiance_plaque_{key}")
            commentaire_plaque = st.text_area("Commentaire sur la lecture", height=60, key=f"commentaire_plaque_{key}")

            st.markdown("### 2. Recherche cycle de vie constructeur")

            st.info("Vérifie le fabricant et la référence avant de lancer la recherche.")

            if st.button("2. Rechercher le statut constructeur / cycle de vie", key=f"life_{key}"):
                if not fabricant and not reference:
                    st.error("Renseigne au moins le fabricant ou la référence.")
                else:
                    with st.spinner("Recherche constructeur en cours..."):
                        result, raw, error = lifecycle_search(fabricant, reference, modele_type, famille)

                    st.session_state.raw_lifecycle[key] = raw

                    if error:
                        st.error(error)
                    elif result:
                        st.session_state.lifecycle_results[key] = result
                        fill_lifecycle_session(key, result)
                        st.success("Recherche cycle de vie terminée. Vérifie les sources.")
                        st.rerun()

            if st.session_state.raw_lifecycle.get(key):
                with st.expander("Voir la réponse brute recherche constructeur"):
                    st.text_area(
                        "Réponse brute recherche",
                        value=st.session_state.raw_lifecycle.get(key, ""),
                        height=180,
                        key=f"raw_life_{key}",
                    )

            st.markdown("### 3. Résultat cycle de vie")

            statut_actuel = st.text_input("Statut actuel de l’équipement", key=f"statut_actuel_{key}")
            conclusion = st.text_area("Conclusion obsolescence", height=80, key=f"conclusion_obsolescence_{key}")

            c1, c2, c3 = st.columns(3)
            with c1:
                date_fin_com = st.text_input("Fin commercialisation", key=f"date_fin_commercialisation_{key}")
            with c2:
                date_fin_support = st.text_input("Fin support", key=f"date_fin_support_{key}")
            with c3:
                date_fin_service = st.text_input("Fin service", key=f"date_fin_service_{key}")

            remplacement_dispo = st.text_input("Remplacement disponible ?", key=f"remplacement_disponible_{key}")
            ref_remplacement = st.text_input("Référence remplacement", key=f"reference_remplacement_{key}")
            fabricant_remplacement = st.text_input("Fabricant remplacement", key=f"fabricant_remplacement_{key}")

            ce_que_dit = st.text_area(
                "Ce que dit le constructeur / source fiable",
                height=100,
                key=f"ce_que_dit_le_constructeur_{key}",
            )

            source_secondaire = st.text_area(
                "Source secondaire / fournisseur principal si constructeur introuvable",
                height=70,
                key=f"source_secondaire_{key}",
            )

            confiance_source = st.text_input("Niveau de confiance source", key=f"confiance_source_{key}")
            commentaire_source = st.text_area("Commentaire source", height=60, key=f"commentaire_source_{key}")

            lifecycle = st.session_state.lifecycle_results.get(key, empty_lifecycle_result())
            sources = lifecycle.get("sources", [])

            if sources:
                st.markdown("### 4. Sources")
                for s in sources[:6]:
                    title = s.get("titre", "Source")
                    url = s.get("url", "")
                    typ = s.get("type_source", "")
                    if url:
                        st.markdown(f"- [{title}]({url}) — {typ}")
                    else:
                        st.markdown(f"- {title} — {typ}")
            else:
                st.caption("Aucune source trouvée pour le moment.")

            if st.button("Ajouter au tableau de synthèse", key=f"add_{key}"):
                source_urls = " | ".join([s.get("url", "") for s in sources if s.get("url")])
                st.session_state.rows.append(
                    {
                        "_key": key,
                        "Fabricant": fabricant,
                        "Référence": reference,
                        "Modèle/type": modele_type,
                        "N° série": numero_serie,
                        "Famille": famille,
                        "Caractéristiques plaque": caracteristiques,
                        "Statut actuel": statut_actuel,
                        "Conclusion obsolescence": conclusion,
                        "Fin commercialisation": date_fin_com,
                        "Fin support": date_fin_support,
                        "Fin service": date_fin_service,
                        "Remplacement disponible": remplacement_dispo,
                        "Référence remplacement": ref_remplacement,
                        "Fabricant remplacement": fabricant_remplacement,
                        "Ce que dit constructeur": ce_que_dit,
                        "Source secondaire": source_secondaire,
                        "Confiance lecture": confiance_plaque,
                        "Confiance source": confiance_source,
                        "Sources": source_urls,
                    }
                )
                st.success("Ligne ajoutée au tableau.")

st.divider()
st.subheader("Tableau de synthèse cycle de vie / obsolescence")

if st.session_state.rows:
    df = pd.DataFrame(st.session_state.rows)

    if "_key" in df.columns:
        df_display = df.drop(columns=["_key"])
    else:
        df_display = df.copy()

    edited_df = st.data_editor(df_display, use_container_width=True, num_rows="dynamic")

    st.download_button(
        "Télécharger CSV",
        data=edited_df.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name="cycle_vie_obsolescence.csv",
        mime="text/csv",
    )

    st.download_button(
        "Télécharger Excel",
        data=make_excel_download(edited_df),
        file_name="cycle_vie_obsolescence.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Le tableau sera alimenté après la recherche du cycle de vie.")
