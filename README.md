# Application cycle de vie / obsolescence - V5

Cahier des charges :
- Charger une photo de plaque
- Lire les informations de l'équipement
- Rechercher les informations constructeur ou fournisseur fiable
- Dire si l'équipement est obsolète, non obsolète, remplacé ou en fin de vie programmée
- Donner les dates de fin de commercialisation / support / service si disponibles
- Donner le remplacement proposé si disponible
- Afficher les sources
- Exporter le tableau

Secrets Streamlit :

```toml
OPENAI_API_KEY = "votre_cle_api"
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_SEARCH_MODEL = "gpt-4o-mini"
```