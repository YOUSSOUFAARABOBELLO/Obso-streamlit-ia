# Application d’aide à la gestion d’obsolescence

Prototype en ligne pour analyser des plaques signalétiques avec IA Vision.

## Fonctions

- Import d'une ou plusieurs photos
- Analyse IA de la plaque
- Préremplissage automatique de la fiche équipement
- Vérification / correction manuelle
- Calcul du score d'obsolescence
- Tableau de suivi
- Export CSV et Excel

## Installation locale

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Déploiement en ligne avec Streamlit Cloud

1. Créer un compte GitHub.
2. Créer un nouveau dépôt.
3. Ajouter les fichiers :
   - app.py
   - requirements.txt
   - README.md
4. Aller sur Streamlit Cloud.
5. Créer une nouvelle application à partir du dépôt GitHub.
6. Ajouter la clé API dans les secrets :

```toml
OPENAI_API_KEY = "votre_cle_api"
OPENAI_MODEL = "gpt-4.1-mini"
```

7. Déployer l’application.

## Remarque

La décision finale doit rester validée par l'utilisateur. L'IA sert à lire, interpréter et préremplir les données.