# 🌱 Yarrow-AI-Server v3

Serveur **FastAPI** avec logique horticole avancée pour simuler et piloter la boîte AutoGrow avant même d’avoir le matériel.

- Multi-cultures (cannabis, fraise, tomate, laitue)
- Multi-phases (semis, croissance, floraison)
- Cooldowns anti-surdosage (pH / EC)
- Historique SQLite (télémétrie & actions)
- WebSocket temps réel pour dashboard

---

## 🚀 Installation

Cloner le repo et installer les dépendances :

```bash
git clone https://github.com/<ton-user>/yarrow-ai-server-v3.git
cd yarrow-ai-server-v3
pip install fastapi uvicorn "pydantic<3" websockets requests
