# Application d’aide à la gestion d’obsolescence - V3

Version corrigée :
- Préremplissage forcé des champs après analyse IA
- Parsing JSON corrigé même si l'IA retourne ```json
- Ajout du critère "Statut obsolescence fabricant"
- Score expliqué dans la barre latérale
- Export CSV et Excel

Secrets Streamlit :

```toml
OPENAI_API_KEY = "votre_cle_api"
OPENAI_MODEL = "gpt-4o-mini"
```