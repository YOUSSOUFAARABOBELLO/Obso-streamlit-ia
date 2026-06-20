# Application cycle de vie / obsolescence - V6

Version simplifiée de l'interface :
- Suppression du bloc latéral Paramètres / Cahier des charges
- Interface centrée sur le parcours utilisateur :
  1. Charger la photo
  2. Lire la plaque avec l'IA
  3. Vérifier fabricant / référence / modèle
  4. Rechercher le statut constructeur
  5. Afficher obsolescence, dates, remplacement et sources
  6. Exporter en CSV ou Excel

Secrets Streamlit :

```toml
OPENAI_API_KEY = "votre_cle_api"
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_SEARCH_MODEL = "gpt-4o-mini"
```
