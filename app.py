import base64,json,os,re,hashlib
from io import BytesIO
import pandas as pd
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Aide à la décision d'obsolescence",layout="wide")
st.title("Aide à la décision d'obsolescence")
st.caption("Identification de l'équipement → recherche constructeur → cycle de vie → sources")
MODEL=os.getenv("OPENAI_MODEL","gpt-4o-mini"); SEARCH_MODEL=os.getenv("OPENAI_SEARCH_MODEL",MODEL)

def get_client():
    k=os.getenv("OPENAI_API_KEY","").strip()
    return (OpenAI(api_key=k),None) if k else (None,"Clé API manquante : OPENAI_API_KEY")

def parse_json(t):
    if not t:return None
    t=re.sub(r'^```(?:json)?\s*|\s*```$','',t.strip(),flags=re.I)
    try:return json.loads(t)
    except Exception:
        a,b=t.find('{'),t.rfind('}')
        try:return json.loads(t[a:b+1]) if a>=0 and b>a else None
        except Exception:return None

def web_json(prompt):
    c,e=get_client()
    if e:return None,e
    last=''; raw=''
    for tool in ('web_search','web_search_preview'):
        try:
            r=c.responses.create(model=SEARCH_MODEL,tools=[{'type':tool}],input=prompt)
            raw=(r.output_text or '').strip()
            d=parse_json(raw)
            if d:return d,None
            last='La recherche a répondu, mais le format doit être normalisé.'
            break
        except Exception as x:last=str(x)
    if raw:
        try:
            normalizer=("Transforme le contenu ci-dessous en UN SEUL objet JSON valide. "
                        "Ne fais aucune nouvelle recherche et n'ajoute aucune information. "
                        "Conserve exactement les faits, valeurs, URLs et incertitudes. "
                        "Ne mets ni markdown ni commentaire avant/après le JSON.\n\nCONTENU :\n"+raw)
            r2=c.responses.create(model=MODEL,input=normalizer)
            d=parse_json(r2.output_text)
            if d:return d,None
        except Exception as x:last=str(x)
    return None,last or 'Réponse JSON inexploitable.'

def read_plate(f):
    c,e=get_client()
    if e:return None,e
    data=base64.b64encode(f.getvalue()).decode(); mime=f.type or 'image/jpeg'
    p='''Lis cette plaque industrielle. Retourne UNIQUEMENT ce JSON valide : {"fabricant":"","reference":"","modele_type":"","numero_serie":"","famille_equipement":"","caracteristiques":"","texte_lu":"","niveau_confiance":"","commentaire":""}. Ne devine pas les caractères illisibles et reproduis fidèlement référence et modèle/type.'''
    try:
        r=c.responses.create(model=MODEL,input=[{'role':'user','content':[{'type':'input_text','text':p},{'type':'input_image','image_url':f'data:{mime};base64,{data}'}]}])
        return parse_json(r.output_text),None
    except Exception as x:return None,str(x)

def identify(info):
    p=f"""Tu dois IDENTIFIER précisément un équipement industriel, sans conclure sur son obsolescence.
Données : {json.dumps(info,ensure_ascii=False)}

OBJECTIF :
- déterminer si les données correspondent bien à un équipement précis ;
- séparer l'identification de l'équipement de son statut de cycle de vie.

RECHERCHE :
1) fabricant + référence/modèle EXACT ;
2) référence exacte seule si nécessaire ;
3) documents/catalogues du constructeur ;
4) site du constructeur actuel ou historique ;
5) distributeur officiellement reconnu/agréé si cette relation peut être prouvée ;
6) distributeur industriel spécialisé ou archive seulement en complément.

RÈGLES :
- IMPORTANT : l'identification et le cycle de vie sont deux choses différentes.
- Tu ne dois JAMAIS dégrader le niveau d'identification parce que le statut de cycle de vie, l'EOL, l'EOS, le support ou la disponibilité ne sont pas connus.
- Si les données saisies/lues montrent clairement une marque/fabricant et une référence précise, et qu'elles sont cohérentes avec une source ou avec la plaque elle-même, l'équipement peut être considéré comme identifié.
- Une page correspondant exactement au fabricant + à la référence + au type d'équipement peut confirmer l'identification, même si le cycle de vie reste inconnu.
- Si la plaque elle-même fournit clairement le fabricant/marque et la référence, conserve ces éléments dans l'identification, même si aucune source web externe n'est trouvée.
- Dans ce cas, le niveau peut être "confirme" si la lecture est claire et cohérente, ou "probable" si une ambiguïté subsiste.
- "confirme" = fabricant/marque + référence/modèle suffisamment précis et cohérents pour désigner l'équipement.
- "probable" = équipement identifiable mais une ambiguïté mineure subsiste sur la désignation ou la variante.
- "insuffisant" = on ne sait réellement pas quel équipement est concerné.
- Exemple : "Parker / SSD Parvex / GX4R090R0700" lu clairement sur la plaque = équipement identifié, même si aucun EOL ou statut constructeur n'est trouvé.
- Si un distributeur est présenté comme agréé/officiel, exige une preuve explicite de cette relation. Sinon classe-le simplement "distributeur".
- N'invente rien et ne corrige pas silencieusement une référence.

Retourne UNIQUEMENT ce JSON :
{{
 "fabricant_identifie":"",
 "marque_actuelle_ou_groupe":"",
 "designation_identifiee":"",
 "famille_identifiee":"",
 "reference_confirmee":"",
 "modele_type_confirme":"",
 "niveau_identification":"confirme|probable|insuffisant",
 "resume_identification":"",
 "sources_identification":[
   {{
     "titre":"",
     "url":"",
     "type":"constructeur|document constructeur|distributeur agréé|distributeur|archive|autre",
     "preuve_agrement":""
   }}
 ]
}}"""
    result, err = web_json(p)
    if result:
        # Garde-fou : l'absence d'information de cycle de vie ne doit jamais
        # transformer un équipement clairement lu sur sa plaque en "non identifié".
        fab_in = (info.get("fabricant") or "").strip()
        ref_in = (info.get("reference") or "").strip()
        mod_in = (info.get("modele_type") or "").strip()
        fam_in = (info.get("famille_equipement") or "").strip()

        if fab_in and (ref_in or mod_in):
            if not result.get("fabricant_identifie"):
                result["fabricant_identifie"] = fab_in
            if not result.get("reference_confirmee") and ref_in:
                result["reference_confirmee"] = ref_in
            if not result.get("modele_type_confirme") and mod_in:
                result["modele_type_confirme"] = mod_in
            if not result.get("famille_identifiee") and fam_in:
                result["famille_identifiee"] = fam_in

            current_level = (result.get("niveau_identification") or "").lower()
            if current_level == "insuffisant":
                result["niveau_identification"] = "confirme"
                base = (
                    f"L'équipement est identifié à partir des informations clairement lisibles sur la plaque : "
                    f"fabricant/marque {fab_in}"
                )
                if ref_in:
                    base += f", référence {ref_in}"
                if fam_in:
                    base += f", désignation/famille {fam_in}"
                base += ". L'absence éventuelle d'information sur l'EOL, l'EOS ou le support concerne uniquement le cycle de vie, pas l'identification."
                result["resume_identification"] = base

        return result, err
    return result, err

def lifecycle(info,ident):
    p=f"""Analyse le CYCLE DE VIE et la DISPONIBILITÉ COMMERCIALE de cet équipement industriel.

Données initiales : {json.dumps(info,ensure_ascii=False)}
Identification : {json.dumps(ident,ensure_ascii=False)}

Tu dois traiter CE CAS précis à partir des informations réellement trouvées. Ne réutilise pas une conclusion générique.

ORDRE DE RECHERCHE :
1) constructeur actuel ;
2) constructeur historique ;
3) documentation officielle : catalogue actuel, EOL, EOS, fin de commercialisation, fin de support, migration, remplacement ;
4) distributeur officiellement reconnu/agréé si cette relation est prouvée ;
5) distributeur industriel spécialisé fiable ;
6) archives/autres sources seulement en complément.

DISTINGUE TOUJOURS :
A. statut du cycle de vie chez le constructeur ;
B. disponibilité commerciale observée aujourd'hui.

RÈGLES IMPORTANTES :
- Un produit proposé à la vente ou "en stock" chez un distributeur prouve une disponibilité commerciale observée, PAS qu'il est encore fabriqué.
- Un ancien stock peut continuer à être vendu après une fin de production.
- Une difficulté à trouver la référence ne signifie pas qu'elle est obsolète.
- Une page générale du constructeur ne prouve pas le statut d'une référence.
- "Actif" exige une preuve claire que la référence/gamme est actuellement commercialisée ou supportée par le constructeur.
- "Obsolète" exige une preuve claire de fin de vie/arrêt ou une information officielle équivalente.
- "Fin de vie annoncée" exige une annonce/document explicite.
- Si aucune preuve suffisante n'existe, utilise "Non déterminé", mais explique exactement ce qui EST connu.
- Si la référence est trouvée en vente, indique "Disponible à la vente" ou "En stock" selon la preuve.
- Ne dis "distributeur agréé" que si l'agrément/partenariat est explicitement prouvé.
- Un remplacement officiel n'est indiqué que s'il est documenté.
- N'invente aucune date, référence, URL, relation commerciale ou statut.

Le COMMENTAIRE D'ANALYSE doit être court mais utile :
- rappeler les faits trouvés pour cet équipement ;
- expliquer ce que ces faits permettent ou ne permettent pas de conclure ;
- ne pas répéter mécaniquement "informations insuffisantes".

L'ACTION RECOMMANDÉE doit découler du cas :
- par exemple contacter le constructeur pour confirmer maintien en production/EOL/EOS,
- vérifier une référence de remplacement,
- confirmer un stock,
- ou aucune action immédiate si le statut actif est clairement établi.

Retourne UNIQUEMENT ce JSON :
{{
 "statut_cycle_vie":"Actif|Obsolète|Fin de vie annoncée|Non déterminé",
 "disponibilite_commerciale":"Disponible à la vente|En stock|Indisponible|Non déterminée",
 "source_disponibilite":"",
 "conclusion_obsolescence":"",
 "date_fin_commercialisation":"",
 "date_fin_support":"",
 "date_fin_service":"",
 "remplacement_disponible":"Oui|Non|Non déterminé",
 "reference_remplacement":"",
 "fabricant_remplacement":"",
 "information_constructeur":"",
 "preuve_cycle_vie":"",
 "commentaire_analyse":"",
 "action_recommandee":"",
 "niveau_confiance":"Élevé|Moyen|Faible",
 "sources":[
   {{
     "titre":"",
     "url":"",
     "type":"constructeur|document constructeur|distributeur agréé|distributeur|archive|autre",
     "preuve_agrement":"",
     "information_apportee":""
   }}
 ]
}}"""
    return web_json(p)

def srcs(v):
    if not v:return []
    if isinstance(v,str):
        return [{'titre':v,'url':'','type':'','preuve_agrement':'','information_apportee':''}]
    out=[]
    for x in v:
        if not isinstance(x,dict):continue
        out.append({
            'titre':str(x.get('titre') or x.get('title') or 'Source'),
            'url':str(x.get('url') or x.get('lien') or ''),
            'type':str(x.get('type') or ''),
            'preuve_agrement':str(x.get('preuve_agrement') or ''),
            'information_apportee':str(x.get('information_apportee') or '')
        })
    return out

def show(ident,life):
    st.subheader("Identification de l'équipement")
    a,b,c=st.columns(3)
    a.markdown('**Fabricant identifié :** '+(ident.get('fabricant_identifie') or 'Non déterminé'))
    b.markdown('**Désignation :** '+(ident.get('designation_identifiee') or 'Non déterminée'))
    c.markdown("**Niveau d'identification :** "+(ident.get('niveau_identification') or 'insuffisant'))
    if ident.get('marque_actuelle_ou_groupe'):
        st.markdown('**Marque actuelle / groupe :** '+ident['marque_actuelle_ou_groupe'])
    if ident.get('reference_confirmee'):
        st.markdown('**Référence confirmée :** '+ident['reference_confirmee'])
    if ident.get('modele_type_confirme'):
        st.markdown('**Modèle / type confirmé :** '+ident['modele_type_confirme'])
    if ident.get('resume_identification'):
        st.info(ident['resume_identification'])

    st.subheader('Analyse du cycle de vie')
    a,b=st.columns(2)
    a.markdown('**Statut du cycle de vie : '+(life.get('statut_cycle_vie') or 'Non déterminé')+'**')
    b.markdown('**Disponibilité commerciale : '+(life.get('disponibilite_commerciale') or 'Non déterminée')+'**')

    if life.get('source_disponibilite'):
        st.markdown('**Disponibilité constatée via :** '+life['source_disponibilite'])
    if life.get('date_fin_commercialisation'):
        st.markdown('**Fin de commercialisation :** '+life['date_fin_commercialisation'])
    else:
        st.markdown('**Fin de commercialisation :** Non trouvée')
    if life.get('date_fin_support'):
        st.markdown('**Fin de support :** '+life['date_fin_support'])
    else:
        st.markdown('**Fin de support :** Non trouvée')

    st.markdown('**Remplacement officiel :** '+(life.get('remplacement_disponible') or 'Non déterminé'))
    if life.get('reference_remplacement'):
        st.markdown('**Référence de remplacement :** '+life['reference_remplacement'])

    if life.get('preuve_cycle_vie'):
        st.markdown('**Éléments établissant le cycle de vie :** '+life['preuve_cycle_vie'])
    if life.get('information_constructeur'):
        st.markdown('**Information constructeur :** '+life['information_constructeur'])
    if life.get('conclusion_obsolescence'):
        st.markdown('**Conclusion :** '+life['conclusion_obsolescence'])

    st.markdown('**Niveau de confiance :** '+(life.get('niveau_confiance') or 'Faible'))

    st.subheader("Commentaire d'analyse")
    commentaire=life.get('commentaire_analyse') or (
        "Les informations disponibles ne permettent pas encore de caractériser précisément "
        "le cycle de vie de cette référence."
    )
    st.info(commentaire)

    st.subheader('Action recommandée')
    st.success(life.get('action_recommandee') or
               "Compléter la recherche ou contacter le constructeur afin de lever les incertitudes restantes.")

    st.subheader('Sources')
    seen=set(); n=0
    all_sources=srcs(ident.get('sources_identification'))+srcs(life.get('sources'))
    for s in all_sources:
        k=(s['titre'],s['url'])
        if k in seen:continue
        seen.add(k);n+=1
        suffix=f" — {s['type']}" if s['type'] else ''
        line=f"[{s['titre']}]({s['url']}){suffix}" if s['url'].startswith('http') else f"{s['titre']}{suffix}"
        st.markdown(f"- {line}")
        if s.get('information_apportee'):
            st.caption("Information apportée : "+s['information_apportee'])
        if s.get('preuve_agrement'):
            st.caption("Preuve du statut de distributeur agréé : "+s['preuve_agrement'])
    if not n:
        st.warning("Aucune source exploitable n'a été retournée.")

def make_row(i,ident,life):
    return {
        'Fabricant saisi/lu':i.get('fabricant',''),
        'Référence saisie/lue':i.get('reference',''),
        'Modèle / type':i.get('modele_type',''),
        'Désignation identifiée':ident.get('designation_identifiee',''),
        'Fabricant / groupe identifié':ident.get('fabricant_identifie','') or ident.get('marque_actuelle_ou_groupe',''),
        'Niveau identification':ident.get('niveau_identification',''),
        'Statut cycle de vie':life.get('statut_cycle_vie',''),
        'Disponibilité commerciale':life.get('disponibilite_commerciale',''),
        'Conclusion':life.get('conclusion_obsolescence',''),
        'Fin commercialisation':life.get('date_fin_commercialisation',''),
        'Fin support':life.get('date_fin_support',''),
        'Remplacement officiel':life.get('remplacement_disponible',''),
        'Référence remplacement':life.get('reference_remplacement',''),
        "Commentaire d'analyse":life.get('commentaire_analyse',''),
        'Action recommandée':life.get('action_recommandee',''),
        'Niveau confiance':life.get('niveau_confiance',''),
        'Sources':' | '.join(s['url'] or s['titre'] for s in srcs(life.get('sources')))
    }

def add_row(r):
    key=tuple(str(r[x]).strip().lower() for x in ('Fabricant saisi/lu','Référence saisie/lue','Modèle / type'))
    for n,o in enumerate(st.session_state.rows):
        old=tuple(str(o[x]).strip().lower() for x in ('Fabricant saisi/lu','Référence saisie/lue','Modèle / type'))
        if key==old and any(key):st.session_state.rows[n]=r;return
    st.session_state.rows.append(r)

def analyse(i):
    ident,e=identify(i)
    if e or not ident:st.error('Erreur identification : '+str(e));return None,None
    life,e=lifecycle(i,ident)
    if e or not life:st.error('Erreur cycle de vie : '+str(e));return ident,None
    add_row(make_row(i,ident,life));return ident,life


def plate_uid(uploaded):
    """Identifiant stable lié au contenu de l'image, pas à sa position dans la liste."""
    return hashlib.sha1(uploaded.getvalue()).hexdigest()[:12]

def load_plate_into_widgets(uid, plate):
    """Force les champs Streamlit à prendre les nouvelles valeurs OCR."""
    st.session_state[f'fab_{uid}'] = plate.get('fabricant', '')
    st.session_state[f'ref_{uid}'] = plate.get('reference', '')
    st.session_state[f'mod_{uid}'] = plate.get('modele_type', '')
    st.session_state[f'ser_{uid}'] = plate.get('numero_serie', '')
    st.session_state[f'fam_{uid}'] = plate.get('famille_equipement', '')

if 'rows' not in st.session_state:st.session_state.rows=[]
mode=st.radio("Mode d'entrée",['À partir de plaques signalétiques',"À partir d'informations clés"],horizontal=True)

if mode=="À partir d'informations clés":
    st.header("Saisie manuelle d'informations clés");st.caption("L'application identifie d'abord l'équipement, puis recherche son cycle de vie.")
    c1,c2=st.columns(2); fab=c1.text_input('Fabricant / constructeur'); mod=c2.text_input('Modèle / type'); ref=c1.text_input('Référence'); ser=c2.text_input('Numéro de série (facultatif)'); fam=st.text_input('Famille / désignation connue (facultatif)')
    info={'fabricant':fab,'reference':ref,'modele_type':mod,'numero_serie':ser,'famille_equipement':fam}
    if st.button('🔎 Identifier, rechercher le cycle de vie et ajouter au tableau',type='primary'):
        if not any((fab.strip(),ref.strip(),mod.strip())):st.warning('Renseigne au minimum le fabricant, la référence ou le modèle/type.')
        else:
            with st.spinner("Identification puis recherche du cycle de vie..."):
                ident,life=analyse(info)
                if ident:st.session_state.mi=ident
                if life:st.session_state.ml=life
    if st.session_state.get('mi') and st.session_state.get('ml'):show(st.session_state.mi,st.session_state.ml)
else:
    st.header('Analyse à partir de plaques signalétiques')
    files = st.file_uploader(
        'Importer une ou plusieurs photos de plaques',
        type=['png','jpg','jpeg','webp'],
        accept_multiple_files=True
    )

    if files and st.button('🚀 Analyser toutes les plaques', type='primary'):
        bar = st.progress(0)
        for n, f in enumerate(files):
            uid = plate_uid(f)
            plate, e = read_plate(f)
            if e or not plate:
                st.error(f'{f.name} — {e}')
            else:
                # Stocke le nouveau résultat OCR ET remplace explicitement
                # les valeurs affichées dans les champs.
                st.session_state[f'p_{uid}'] = plate
                load_plate_into_widgets(uid, plate)

                ident, life = analyse(plate)
                if ident:
                    st.session_state[f'i_{uid}'] = ident
                if life:
                    st.session_state[f'l_{uid}'] = life

            bar.progress((n + 1) / len(files))

    if files:
        for n, f in enumerate(files):
            uid = plate_uid(f)

            st.divider()
            st.subheader(f'Équipement {n + 1} — {f.name}')
            left, right = st.columns([1, 1.35])

            with left:
                st.image(f, use_container_width=True)

                if st.button('Lire / relire cette plaque', key=f'read_{uid}'):
                    p, e = read_plate(f)
                    if e or not p:
                        st.error(e)
                    else:
                        # IMPORTANT :
                        # une nouvelle lecture doit écraser les anciennes valeurs
                        # conservées par st.text_input dans session_state.
                        st.session_state[f'p_{uid}'] = p
                        load_plate_into_widgets(uid, p)

                p = st.session_state.get(f'p_{uid}')

                if p:
                    st.markdown('#### Informations extraites de la plaque — vérifie et corrige si nécessaire')

                    # Les champs utilisent un identifiant basé sur l'image.
                    # Ainsi une autre photo ne récupère plus les valeurs de la photo précédente.
                    fabricant = st.text_input(
                        'Fabricant',
                        key=f'fab_{uid}'
                    )
                    reference = st.text_input(
                        'Référence',
                        key=f'ref_{uid}'
                    )
                    modele = st.text_input(
                        'Modèle / type',
                        key=f'mod_{uid}'
                    )
                    serie = st.text_input(
                        'Numéro de série',
                        key=f'ser_{uid}'
                    )
                    famille = st.text_input(
                        'Famille / désignation',
                        key=f'fam_{uid}'
                    )

                    # Synchronise les corrections manuelles avec l'objet utilisé pour l'analyse.
                    p = dict(p)
                    p['fabricant'] = fabricant
                    p['reference'] = reference
                    p['modele_type'] = modele
                    p['numero_serie'] = serie
                    p['famille_equipement'] = famille
                    st.session_state[f'p_{uid}'] = p

            with right:
                p = st.session_state.get(f'p_{uid}')

                if p and st.button(
                    '🔎 Identifier, rechercher le cycle de vie et ajouter au tableau',
                    key=f'go_{uid}',
                    type='primary'
                ):
                    current = dict(p)
                    current['fabricant'] = st.session_state.get(f'fab_{uid}', current.get('fabricant',''))
                    current['reference'] = st.session_state.get(f'ref_{uid}', current.get('reference',''))
                    current['modele_type'] = st.session_state.get(f'mod_{uid}', current.get('modele_type',''))
                    current['numero_serie'] = st.session_state.get(f'ser_{uid}', current.get('numero_serie',''))
                    current['famille_equipement'] = st.session_state.get(f'fam_{uid}', current.get('famille_equipement',''))
                    st.session_state[f'p_{uid}'] = current
                    with st.spinner('Identification puis recherche du cycle de vie...'):
                        ident, life = analyse(current)
                        if ident:
                            st.session_state[f'i_{uid}'] = ident
                        if life:
                            st.session_state[f'l_{uid}'] = life

                if (
                    st.session_state.get(f'i_{uid}')
                    and st.session_state.get(f'l_{uid}')
                ):
                    show(
                        st.session_state[f'i_{uid}'],
                        st.session_state[f'l_{uid}']
                    )

st.divider();st.header('Tableau de synthèse')
if st.session_state.rows:
    df=pd.DataFrame(st.session_state.rows);st.dataframe(df,use_container_width=True,hide_index=True)
    st.download_button('Télécharger CSV',df.to_csv(index=False).encode('utf-8-sig'),'synthese_obsolescence.csv','text/csv')
    buf=BytesIO()
    with pd.ExcelWriter(buf,engine='openpyxl') as w:df.to_excel(w,index=False,sheet_name='Synthèse')
    st.download_button('Télécharger Excel',buf.getvalue(),'synthese_obsolescence.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    if st.button('Vider le tableau'):st.session_state.rows=[];st.rerun()
else:st.info('Le tableau se remplira automatiquement après chaque analyse.')
