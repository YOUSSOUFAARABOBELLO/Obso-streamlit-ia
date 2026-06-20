# Application cycle de vie / obsolescence - V8

Version simplifiée pour l'utilisateur :
- Bouton global pour lire toutes les plaques importées
- Bouton global pour rechercher le cycle de vie de toutes les plaques lues
- Tableau de synthèse alimenté automatiquement
- Suppression des informations techniques inutiles dans l'interface

Parcours utilisateur :
1. Charger une ou plusieurs photos
2. Cliquer sur Lire toutes les plaques importées
3. Vérifier les informations extraites
4. Cliquer sur Rechercher le cycle de vie de toutes les plaques lues
5. Consulter le tableau de synthèse
6. Exporter en CSV ou Excel

Secrets Streamlit :

```toml
OPENAI_API_KEY = "votre_cle_api"
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_SEARCH_MODEL = "gpt-4o-mini"
```
