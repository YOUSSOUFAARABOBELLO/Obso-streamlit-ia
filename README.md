# Application cycle de vie / obsolescence - V7

Nouveauté :
- Ajout d'un bouton global : Lire toutes les plaques importées avec IA
- Possibilité de sélectionner plusieurs images une seule fois
- L'application analyse chaque image automatiquement
- Les boutons individuels sont conservés pour relancer une seule plaque si besoin

Parcours :
1. Charger une ou plusieurs photos
2. Cliquer sur Lire toutes les plaques importées avec IA
3. Vérifier les informations extraites
4. Rechercher le statut constructeur pour chaque équipement
5. Exporter le tableau CSV ou Excel

Secrets Streamlit :

```toml
OPENAI_API_KEY = "votre_cle_api"
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_SEARCH_MODEL = "gpt-4o-mini"
```
