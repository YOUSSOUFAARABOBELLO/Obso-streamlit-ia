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
    last=''
    for tool in ('web_search','web_search_preview'):
        try:
            r=c.responses.create(model=SEARCH_MODEL,tools=[{'type':tool}],input=prompt)
            d=parse_json(r.output_text)
            if d:return d,None
            last='Réponse JSON inexploitable.'
        except Exception as x:last=str(x)
    return None,last

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
    p=f'''Tu dois d'abord IDENTIFIER précisément un équipement industriel, sans conclure encore sur son obsolescence.\nDonnées : {json.dumps(info,ensure_ascii=False)}\nRecherche obligatoirement : (1) référence/modèle EXACT + fabricant, (2) référence et modèle séparément si nécessaire, (3) gamme/famille, (4) historique fabricant, acquisition/changement de marque/groupe, (5) constructeur actuel si ancienne marque reprise. Priorité aux documents constructeur officiels; distributeurs/archives seulement en complément. Une page générale du fabricant ne confirme pas la référence exacte. Ne corrige pas silencieusement une référence et n'invente rien.\nRetourne UNIQUEMENT : {{"fabricant_identifie":"","marque_actuelle_ou_groupe":"","designation_identifiee":"","famille_identifiee":"","reference_confirmee":"","modele_type_confirme":"","niveau_identification":"confirme|probable|insuffisant","resume_identification":"","sources_identification":[{{"titre":"","url":"","type":"constructeur|document constructeur|distributeur|archive|autre"}}]}}\nconfirme = source reliant clairement la référence/modèle à l'équipement; probable = gamme/famille seulement; insuffisant = non fiable.'''
    return web_json(p)

def lifecycle(info,ident):
    p=f'''Analyse le CYCLE DE VIE de cet équipement.\nDonnées initiales : {json.dumps(info,ensure_ascii=False)}\nIdentification : {json.dumps(ident,ensure_ascii=False)}\nOrdre : constructeur actuel, constructeur historique, documents officiels EOL/EOS/arrêt/migration/catalogue/remplacement, puis sources secondaires fiables. Règles : difficulté à trouver != obsolète; page constructeur existante != actif; une source générale sur la marque ne prouve pas le statut; Actif ou Obsolète exige une preuve explicite; sinon statut_actuel = "À vérifier". Un remplacement n'est indiqué que s'il est documenté. N'invente aucune date, référence ou URL.\nRetourne UNIQUEMENT : {{"statut_actuel":"Actif|Obsolète|Fin de vie annoncée|À vérifier","conclusion_obsolescence":"","date_fin_commercialisation":"","date_fin_support":"","date_fin_service":"","remplacement_disponible":"Oui|Non|À vérifier","reference_remplacement":"","fabricant_remplacement":"","ce_que_dit_le_constructeur":"","preuve_statut":"","niveau_confiance":"Élevé|Moyen|Faible","sources":[{{"titre":"","url":"","type":"constructeur|document constructeur|distributeur|archive|autre"}}],"commentaire":""}}'''
    return web_json(p)

def srcs(v):
    if not v:return []
    if isinstance(v,str):return [{'titre':v,'url':'','type':''}]
    return [{'titre':str(x.get('titre') or x.get('title') or 'Source'),'url':str(x.get('url') or x.get('lien') or ''),'type':str(x.get('type') or '')} for x in v if isinstance(x,dict)]

def show(ident,life):
    st.subheader("Identification de l'équipement")
    a,b,c=st.columns(3)
    a.markdown('**Fabricant identifié :** '+(ident.get('fabricant_identifie') or 'À vérifier'))
    b.markdown('**Désignation :** '+(ident.get('designation_identifiee') or 'À vérifier'))
    c.markdown("**Niveau d'identification :** "+(ident.get('niveau_identification') or 'insuffisant'))
    if ident.get('marque_actuelle_ou_groupe'):st.markdown('**Marque actuelle / groupe :** '+ident['marque_actuelle_ou_groupe'])
    if ident.get('reference_confirmee'):st.markdown('**Référence confirmée :** '+ident['reference_confirmee'])
    if ident.get('resume_identification'):st.info(ident['resume_identification'])
    st.subheader('Résultat cycle de vie')
    st.markdown('**Statut actuel : '+(life.get('statut_actuel') or 'À vérifier')+'**')
    st.markdown('**Conclusion :** '+(life.get('conclusion_obsolescence') or "Le statut n'est pas confirmé."))
    st.markdown('**Remplacement :** '+(life.get('remplacement_disponible') or 'À vérifier'))
    if life.get('reference_remplacement'):st.markdown('**Référence de remplacement :** '+life['reference_remplacement'])
    if life.get('date_fin_commercialisation'):st.markdown('**Fin de commercialisation :** '+life['date_fin_commercialisation'])
    if life.get('date_fin_support'):st.markdown('**Fin de support :** '+life['date_fin_support'])
    if life.get('preuve_statut'):st.markdown('**Élément de preuve :** '+life['preuve_statut'])
    if life.get('ce_que_dit_le_constructeur'):st.markdown('**Information constructeur :** '+life['ce_que_dit_le_constructeur'])
    st.markdown('**Niveau de confiance :** '+(life.get('niveau_confiance') or 'Faible'))
    st.subheader('Sources')
    seen=set(); n=0
    for s in srcs(ident.get('sources_identification'))+srcs(life.get('sources')):
        k=(s['titre'],s['url'])
        if k in seen:continue
        seen.add(k);n+=1; suffix=f" — {s['type']}" if s['type'] else ''
        st.markdown(f"- [{s['titre']}]({s['url']}){suffix}" if s['url'].startswith('http') else f"- {s['titre']}{suffix}")
    if not n:st.warning("Aucune source exploitable n'a été retournée.")

def make_row(i,ident,life):
    return {'Fabricant saisi/lu':i.get('fabricant',''),'Référence saisie/lue':i.get('reference',''),'Modèle / type':i.get('modele_type',''),'Désignation identifiée':ident.get('designation_identifiee',''),'Fabricant / groupe identifié':ident.get('fabricant_identifie','') or ident.get('marque_actuelle_ou_groupe',''),'Niveau identification':ident.get('niveau_identification',''),'Statut actuel':life.get('statut_actuel',''),'Conclusion':life.get('conclusion_obsolescence',''),'Fin commercialisation':life.get('date_fin_commercialisation',''),'Fin support':life.get('date_fin_support',''),'Remplacement':life.get('remplacement_disponible',''),'Référence remplacement':life.get('reference_remplacement',''),'Niveau confiance':life.get('niveau_confiance',''),'Sources':' | '.join(s['url'] or s['titre'] for s in srcs(life.get('sources')))}

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

                if st.button('Lire cette plaque', key=f'read_{uid}'):
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
                    st.markdown('#### Informations lues — corrige si nécessaire')

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
                    with st.spinner('Identification puis recherche du cycle de vie...'):
                        ident, life = analyse(p)
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
