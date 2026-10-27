# 🚗 AutoHunter — Bot d'Audit & de Veille Auto d'Occasion

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()
[![Platform](https://img.shields.io/badge/Platforms-Leboncoin%20%7C%20La%20Centrale-orange.svg)]()

> **Détecteur intelligent de pépites automobiles d'occasion (< 5 000 €).**  
> Scrape en continu Leboncoin et La Centrale, audite chaque annonce selon une grille à 4 axes (décote financière, base de données de fiabilité mécanique, analyse sémantique des signaux d'alerte, transparence de l'historique/CT), et envoie des alertes instantanées sur smartphone via **Discord Webhook**.

---

## ⚡ Démarrage Rapide (Quick Start)

### 1. Installation des dépendances
```bash
git clone https://github.com/NewGamer62/autohunter.git
cd autohunter
pip install -r requirements.txt
# Optionnel : pour le contournement du bot-shield Leboncoin (DataDome)
playwright install chromium
```

### 2. Configuration (`config/config.yaml`)
Renseigne l'URL de ton webhook Discord pour recevoir les alertes sur mobile :
```yaml
notifier:
  discord_webhook_url: "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
```

### 3. Lancement
* **Exécution unique (scan immédiat) :**
  ```bash
  python src/main.py --once
  ```
* **Lancer le démon de surveillance continue (avec jitter anti-détection 8-15 min) :**
  ```bash
  python src/main.py --daemon
  ```
* **Consulter le top des pépites enregistrées en base SQLite :**
  ```bash
  python src/main.py --top 10
  ```
* **Auditer rapidement le texte d'une annonce trouvée manuellement :**
  ```bash
  python src/main.py --audit-text "Clio 2 1.2 16v, 110000 km, CT ok, factures disponibles"
  ```

---

## 🧠 Le Moteur d'Audit 4D (Notation sur 100 points)

Chaque annonce est disséquée sur 4 dimensions complémentaires :

```
┌─────────────────────────────────────────────────────────────┐
│                      SCORE GLOBAL / 100                     │
├──────────────┬──────────────┬───────────────┬───────────────┤
│ 1. PRIX      │ 2. MOTEUR    │ 3. TEXTE      │ 4. HISTORIQUE │
│    /30 pts   │    /30 pts   │    /20 pts    │    /20 pts    │
└──────────────┴──────────────┴───────────────┴───────────────┘
```

1. **Décote Financière (/30) :** Calcule le positionnement prix dans le budget cible (1 500 € – 3 500 € = zone de rentabilité max). Détecte et élimine les arnaques au virement (< 700 €).
2. **Fiabilité Moteur & Boîte (/30) :** 
   * **Moteurs d'Or (+26 à +30 pts) :** Toyota VVT-i (1KR-FE, 2SZ-FE), Honda i-VTEC / i-DSI, Renault D4F/K4J/K4M, PSA TU atmosphériques, Alfa 1.4 FIRE, VAG 1.6 MPI 102 ch, Volvo/Ford Duratec.
   * **Blacklist Immédiate (Élimination 0 pt) :** 1.2 PureTech (courroie dans l'huile), 1.4/1.6 VTi & THP (chaîne/huile), 1.2 TCe H5Ft, VAG 1.4 TSI EA111 (chaîne en verre), VAG 1.6 FSI, VAG 1.9 TDI BXE (rupture bielles), Alfa 1.4 MultiAir, Alfa Twin Spark, boîtes robotisées simple embrayage (Sensodrive, 2-Tronic, Quickshift).
3. **Analyse Sémantique NLP (/20) :**
   * **Élimination directe :** `"sans CT"`, `"pour pièces"`, `"dans l'état"`, `"joint de culasse"`, `"procédure VE/VGE"`.
   * **Bonus/Malus :** Détection de `"première main"`, `"factures à l'appui"`, `"distribution faite"`, `"CT vierge"`.
4. **Historique & Transparence (/20) :** Validité du contrôle technique, présence de factures/carnet et cohérence du kilométrage.

**Seuil d'alerte Discord : $\ge$ 80/100.**

---

## 🛠️ Stack Technique

* **Langage :** Python 3.11+
* **Extraction :** Playwright Stealth (Chromium headless anti-DataDome) + BeautifulSoup4 / LXML
* **Base de données :** SQLite locale embarquée (`data/autohunter.db`) avec indexation et dédoublonnage automatique
* **Notifications :** Discord Webhook (Rich Embeds avec photo, badges de score, points forts et points de vigilance)
* **Tests :** Pytest (100% de passage sur les règles d'audit et les détections de moteurs)

---

## 🧪 Lancer la Suite de Tests

```bash
pytest tests/ -v
```

---

## 📄 Licence
Distribué sous licence MIT. Développé par [NewGamer62](https://github.com/NewGamer62).
