import base64
import json
import os
import re
from io import BytesIO

import pandas as pd
import streamlit as st
from openai import OpenAI
from openai import APIError, AuthenticationError, BadRequestError, RateLimitError

st.set_page_config(page_title='Cycle de vie équipement - Obsolescence', page_icon='🔎', layout='wide')
st.title('🔎 Analyse du cycle de vie d’un équipement')
st.caption('Plaques signalétiques ou informations clés · Cycle de vie constructeur · Obsolescence · Remplacement')
st.markdown('''
Cette application permet d’identifier un équipement de deux façons :
- à partir d’une ou plusieurs photos de plaques signalétiques ;
- à partir de quelques informations clés connues, même sans photo.

L’application recherche ensuite le statut de cycle de vie de l’équipement auprès du constructeur ou d’une source fiable, affiche les résultats et les sources, puis alimente automatiquement le tableau de synthèse.
''')

for name, default in {
    'rows': [], 'plate_results': {}, 'lifecycle_results': {}, 'raw_plate': {}, 'raw_lifecycle': {}
}.items():
    if name not in st.session_state:
        st.session_state[name] = default.copy() if isinstance(default, (dict, list)) else default


def image_to_data_url(uploaded_file):
    b64 = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
    return f"data:{uploaded_file.type or 'image/jpeg'};base64,{b64}"


def clean_json_text(text):
    if not text:
        return ''
    cleaned = text.strip()
    cleaned = re.sub(r'^```json\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^```\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    return cleaned.strip()


def safe_json_loads(text):
    cleaned = clean_json_text(text)
    if not cleaned:
        return None
    try:
        return json.loads(cleaned)
    except Exception:
        start, end = cleaned.find('{'), cleaned.rfind('}')
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end+1])
            except Exception:
                return None
    return None


def get_client():
    api_key = os.getenv('OPENAI_API_KEY', '').strip()
    if not api_key:
        return None, 'Clé API manquante. Ajoute OPENAI_API_KEY dans les secrets Streamlit.'
    return OpenAI(api_key=api_key), None


def empty_plate_result():
    return {k: '' for k in ['fabricant','reference','modele_type','numero_serie','famille_equipement','caracteristiques','texte_lu','niveau_confiance','commentaire']}


def empty_lifecycle_result():
    d = {k: '' for k in ['statut_actuel','conclusion_obsolescence','date_fin_commercialisation','date_fin_support','date_fin_service','remplacement_disponible','reference_remplacement','fabricant_remplacement','ce_que_dit_le_constructeur','fournisseur_ou_source_secondaire','niveau_confiance','commentaire']}
    d['sources'] = []
    return d


def analyze_plate(uploaded_file):
    client, error = get_client()
    if error:
        return None, '', error
    model_name = os.getenv('OPENAI_MODEL', 'gpt-4o-mini').strip() or 'gpt-4o-mini'
    prompt = '''Tu es un assistant spécialisé en lecture de plaques signalétiques d’équipements industriels.
Analyse l’image et identifie l’équipement.
Retourne uniquement un JSON valide avec : fabricant, reference, modele_type, numero_serie, famille_equipement, caracteristiques, texte_lu, niveau_confiance, commentaire.
Ne pas inventer. Si une information est incertaine, laisse vide ou indique l’incertitude dans commentaire.'''
    try:
        response = client.responses.create(model=model_name, input=[{'role':'user','content':[{'type':'input_text','text':prompt},{'type':'input_image','image_url':image_to_data_url(uploaded_file)}]}], max_output_tokens=800)
        raw = response.output_text or ''
        parsed = safe_json_loads(raw)
        if parsed is None:
            fallback = empty_plate_result(); fallback['texte_lu']=raw[:1500]; fallback['commentaire']='Réponse IA non structurée.'
            return fallback, raw, None
        result = empty_plate_result(); result.update(parsed)
        return result, raw, None
    except RateLimitError:
        return None, '', 'Limite API atteinte ou crédit insuffisant.'
    except AuthenticationError:
        return None, '', 'Erreur d’authentification API.'
    except BadRequestError as e:
        return None, '', 'Image ou requête refusée. ' + str(e)[:250]
    except APIError as e:
        return None, '', 'Erreur API temporaire. ' + str(e)[:250]
    except Exception as e:
        return None, '', f'Erreur inattendue : {type(e).__name__} - {str(e)[:250]}'


def lifecycle_search(fabricant, reference, modele_type, famille):
    client, error = get_client()
    if error:
        return None, '', error
    model_name = os.getenv('OPENAI_SEARCH_MODEL', 'gpt-4o-mini').strip() or 'gpt-4o-mini'
    prompt = f'''Tu es un assistant spécialisé en gestion d’obsolescence industrielle.
Recherche le cycle de vie actuel de cet équipement en priorité auprès du constructeur officiel, de son catalogue/support officiel ou d’une datasheet officielle. Utilise un fournisseur reconnu seulement si le constructeur ne donne pas l’information.
Équipement : Fabricant={fabricant}; Référence={reference}; Modèle/type={modele_type}; Famille={famille}.
Retourne uniquement un JSON valide avec : statut_actuel, conclusion_obsolescence, date_fin_commercialisation, date_fin_support, date_fin_service, remplacement_disponible, reference_remplacement, fabricant_remplacement, ce_que_dit_le_constructeur, fournisseur_ou_source_secondaire, niveau_confiance, sources (liste de titre,url,type_source), commentaire.
Ne jamais inventer une date ni une source. Si aucune source constructeur claire n’est trouvée, le dire explicitement.'''
    last_error = None
    for tools in [[{'type':'web_search_preview'}],[{'type':'web_search'}]]:
        try:
            response = client.responses.create(model=model_name, tools=tools, input=prompt, max_output_tokens=1300)
            raw = response.output_text or ''
            parsed = safe_json_loads(raw)
            if parsed is None:
                fallback = empty_lifecycle_result(); fallback['ce_que_dit_le_constructeur']=raw[:1800]; fallback['commentaire']='Réponse non structurée.'
                return fallback, raw, None
            result = empty_lifecycle_result(); result.update(parsed)
            if not isinstance(result.get('sources'), list): result['sources'] = []
            return result, raw, None
        except BadRequestError as e:
            last_error = str(e)[:300]
            continue
        except RateLimitError:
            return None, '', 'Limite API atteinte ou crédit insuffisant pendant la recherche constructeur.'
        except AuthenticationError:
            return None, '', 'Erreur d’authentification API.'
        except APIError as e:
            return None, '', 'Erreur API temporaire. ' + str(e)[:250]
        except Exception as e:
            return None, '', f'Erreur inattendue : {type(e).__name__} - {str(e)[:250]}'
    return None, '', 'La recherche web n’est pas disponible avec ce compte/modèle. ' + str(last_error)


def fill_plate_session(key, result):
    mapping = {'fabricant':'fabricant','reference':'reference','modele_type':'modele_type','numero_serie':'numero_serie','famille_equipement':'famille_equipement','caracteristiques':'caracteristiques'}
    for field, src in mapping.items():
        st.session_state[f'{field}_{key}'] = '' if result.get(src) is None else str(result.get(src,''))


def row_from_results(key, plate, life):
    sources = life.get('sources', [])
    source_urls = ' | '.join([s.get('url','') for s in sources if s.get('url')])
    return {
        '_key': key,
        'Fabricant': plate.get('fabricant',''),
        'Référence': plate.get('reference',''),
        'Modèle/type': plate.get('modele_type',''),
        'N° série': plate.get('numero_serie',''),
        'Famille': plate.get('famille_equipement',''),
        'Caractéristiques plaque': plate.get('caracteristiques',''),
        'Statut actuel': life.get('statut_actuel',''),
        'Conclusion obsolescence': life.get('conclusion_obsolescence',''),
        'Fin commercialisation': life.get('date_fin_commercialisation',''),
        'Fin support': life.get('date_fin_support',''),
        'Fin service': life.get('date_fin_service',''),
        'Remplacement disponible': life.get('remplacement_disponible',''),
        'Référence remplacement': life.get('reference_remplacement',''),
        'Fabricant remplacement': life.get('fabricant_remplacement',''),
        'Ce que dit constructeur': life.get('ce_que_dit_le_constructeur',''),
        'Source secondaire': life.get('fournisseur_ou_source_secondaire',''),
        'Confiance source': life.get('niveau_confiance',''),
        'Sources': source_urls,
    }


def upsert_row(row):
    for i, existing in enumerate(st.session_state.rows):
        if existing.get('_key') == row.get('_key'):
            st.session_state.rows[i] = row
            return
    st.session_state.rows.append(row)


def make_excel_download(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Cycle_de_vie')
    output.seek(0)
    return output

st.markdown('## 1. Choisir le mode d’entrée')
mode = st.radio('Comment veux-tu identifier l’équipement ?', ['À partir de plaques signalétiques','À partir d’informations clés'], horizontal=True)

if mode == 'À partir de plaques signalétiques':
    uploaded_files = st.file_uploader('Charger une ou plusieurs photos de plaques signalétiques', type=['jpg','jpeg','png','webp'], accept_multiple_files=True)
    if uploaded_files:
        if st.button('🚀 Analyser toutes les plaques', type='primary'):
            progress = st.progress(0)
            for i, f in enumerate(uploaded_files):
                key = f'{i}_{f.name}'.replace(' ','_').replace('.','_')
                plate, raw, err = analyze_plate(f)
                st.session_state.raw_plate[key] = raw
                if err:
                    st.warning(f'{f.name} : {err}'); progress.progress((i+1)/len(uploaded_files)); continue
                st.session_state.plate_results[key] = plate
                fill_plate_session(key, plate)
                if not any([plate.get('fabricant'), plate.get('reference'), plate.get('modele_type')]):
                    st.warning(f'{f.name} : informations insuffisantes.'); progress.progress((i+1)/len(uploaded_files)); continue
                life, raw2, err2 = lifecycle_search(plate.get('fabricant',''), plate.get('reference',''), plate.get('modele_type',''), plate.get('famille_equipement',''))
                st.session_state.raw_lifecycle[key] = raw2
                if err2:
                    st.warning(f'{f.name} : {err2}'); progress.progress((i+1)/len(uploaded_files)); continue
                st.session_state.lifecycle_results[key] = life
                upsert_row(row_from_results(key, plate, life))
                progress.progress((i+1)/len(uploaded_files))
            st.success('Analyse terminée : lecture, recherche cycle de vie, sources et tableau mis à jour.')
            st.rerun()

        st.divider()
        for idx, f in enumerate(uploaded_files):
            key = f'{idx}_{f.name}'.replace(' ','_').replace('.','_')
            st.subheader(f'Équipement : {f.name}')
            col_img, col_info = st.columns([1,1.25])
            with col_img:
                st.image(f, caption=f.name, use_container_width=True)
                if st.button('Lire cette plaque', key=f'read_{key}'):
                    plate, raw, err = analyze_plate(f)
                    st.session_state.raw_plate[key] = raw
                    if err: st.error(err)
                    else:
                        st.session_state.plate_results[key] = plate
                        fill_plate_session(key, plate)
                        st.success('Lecture terminée. Vérifie les informations.')
                        st.rerun()
            with col_info:
                fabricant = st.text_input('Fabricant', key=f'fabricant_{key}')
                reference = st.text_input('Référence', key=f'reference_{key}')
                modele = st.text_input('Modèle / type', key=f'modele_type_{key}')
                serie = st.text_input('Numéro de série', key=f'numero_serie_{key}')
                famille = st.text_input('Famille équipement', key=f'famille_equipement_{key}')
                carac = st.text_area('Caractéristiques lues sur la plaque', height=80, key=f'caracteristiques_{key}')
                if st.button('🔎 Rechercher le cycle de vie et ajouter au tableau', key=f'life_add_{key}', type='primary'):
                    if not any([fabricant, reference, modele]):
                        st.error('Renseigne au moins le fabricant, la référence ou le modèle/type.')
                    else:
                        life, raw, err = lifecycle_search(fabricant, reference, modele, famille)
                        st.session_state.raw_lifecycle[key] = raw
                        if err: st.error(err)
                        else:
                            plate = {'fabricant':fabricant,'reference':reference,'modele_type':modele,'numero_serie':serie,'famille_equipement':famille,'caracteristiques':carac}
                            st.session_state.lifecycle_results[key] = life
                            upsert_row(row_from_results(key, plate, life))
                            st.success('Recherche terminée et résultat ajouté au tableau.')
                            st.rerun()
                life = st.session_state.lifecycle_results.get(key)
                if life:
                    st.markdown('### Résultat cycle de vie')
                    st.write('**Statut actuel :**', life.get('statut_actuel','') or 'Non renseigné')
                    st.write('**Conclusion :**', life.get('conclusion_obsolescence','') or 'Non renseignée')
                    st.write('**Remplacement :**', life.get('reference_remplacement','') or 'Non identifié')
                    sources = life.get('sources', [])
                    if sources:
                        st.markdown('### Sources')
                        for s in sources[:6]:
                            title, url, typ = s.get('titre','Source'), s.get('url',''), s.get('type_source','')
                            st.markdown(f'- [{title}]({url}) — {typ}' if url else f'- {title} — {typ}')
            st.divider()
else:
    st.markdown('### Saisie manuelle d’informations clés')
    st.caption('Tu n’as pas besoin de tout connaître. Renseigne seulement les informations disponibles.')
    c1, c2 = st.columns(2)
    with c1:
        fabricant = st.text_input('Fabricant / constructeur', key='manual_fabricant')
        reference = st.text_input('Référence', key='manual_reference')
    with c2:
        modele = st.text_input('Modèle / type', key='manual_modele')
        serie = st.text_input('Numéro de série (facultatif)', key='manual_serie')
    famille = st.text_input('Famille / désignation connue (facultatif)', key='manual_famille', placeholder='Ex. variateur, moteur, automate, capteur...')
    if st.button('🔎 Rechercher le cycle de vie et ajouter au tableau', type='primary', key='manual_search'):
        if not any([fabricant, reference, modele]):
            st.error('Renseigne au moins le fabricant, la référence ou le modèle/type.')
        else:
            life, raw, err = lifecycle_search(fabricant, reference, modele, famille)
            if err: st.error(err)
            else:
                key = 'manual_' + '_'.join([x.strip().replace(' ','_')[:30] for x in [fabricant, reference, modele, serie] if x.strip()])
                plate = {'fabricant':fabricant,'reference':reference,'modele_type':modele,'numero_serie':serie,'famille_equipement':famille,'caracteristiques':''}
                upsert_row(row_from_results(key, plate, life))
                st.session_state['manual_last_result'] = life
                st.success('Recherche terminée et résultat ajouté au tableau.')
                st.rerun()
    life = st.session_state.get('manual_last_result')
    if life:
        st.markdown('### Résultat cycle de vie')
        st.write('**Statut actuel :**', life.get('statut_actuel','') or 'Non renseigné')
        st.write('**Conclusion :**', life.get('conclusion_obsolescence','') or 'Non renseignée')
        st.write('**Remplacement :**', life.get('reference_remplacement','') or 'Non identifié')
        sources = life.get('sources', [])
        if sources:
            st.markdown('### Sources')
            for s in sources[:6]:
                title, url, typ = s.get('titre','Source'), s.get('url',''), s.get('type_source','')
                st.markdown(f'- [{title}]({url}) — {typ}' if url else f'- {title} — {typ}')

st.divider()
st.subheader('Tableau de synthèse cycle de vie / obsolescence')
if st.session_state.rows:
    df = pd.DataFrame(st.session_state.rows)
    df_display = df.drop(columns=['_key']) if '_key' in df.columns else df.copy()
    edited_df = st.data_editor(df_display, use_container_width=True, num_rows='dynamic', key='synthesis_editor')
    st.download_button('Télécharger CSV', data=edited_df.to_csv(index=False, sep=';').encode('utf-8-sig'), file_name='cycle_vie_obsolescence.csv', mime='text/csv')
    st.download_button('Télécharger Excel', data=make_excel_download(edited_df), file_name='cycle_vie_obsolescence.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    if st.button('Vider le tableau'):
        st.session_state.rows = []
        st.rerun()
else:
    st.info('Le tableau sera alimenté automatiquement après une recherche de cycle de vie.')
